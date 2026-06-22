"""Audit log read-only endpoint for the admin dashboard."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/audit", tags=["audit"])


class AuditEntry(BaseModel):
    id: str
    created_at: str
    session_id: str
    event_type: str
    entity_type: str | None
    token: str | None           # token only — no original PII ever returned
    content_type: str | None
    source_ip: str | None
    row_hash: str


class AuditListResponse(BaseModel):
    entries: list[AuditEntry]
    total: int
    page: int
    page_size: int


@router.get("", response_model=AuditListResponse)
async def list_audit_log(
    hours: int = Query(default=24, ge=1, le=24 * 90),
    event_type: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db_session: object = Query(default=None),  # injected by dependency override
) -> AuditListResponse:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    offset = (page - 1) * page_size

    filters = ["created_at >= :since"]
    params: dict[str, Any] = {"since": since, "limit": page_size, "offset": offset}

    if event_type:
        filters.append("event_type = :event_type")
        params["event_type"] = event_type
    if session_id:
        filters.append("session_id = :session_id")
        params["session_id"] = session_id

    where = " AND ".join(filters)
    entries: list[AuditEntry] = []
    total = 0

    try:
        if db_session is not None:
            count_result = await db_session.execute(  # type: ignore[attr-defined]
                sa.text(f"SELECT COUNT(*) FROM audit_log WHERE {where}"), params
            )
            total = int(count_result.scalar() or 0)

            result = await db_session.execute(  # type: ignore[attr-defined]
                sa.text(
                    f"SELECT id, created_at, session_id, event_type, entity_type, "
                    f"token, content_type, source_ip, row_hash "
                    f"FROM audit_log WHERE {where} "
                    f"ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                ),
                params,
            )
            for row in result:
                entries.append(AuditEntry(
                    id=str(row[0]),
                    created_at=str(row[1]),
                    session_id=row[2],
                    event_type=row[3],
                    entity_type=row[4],
                    token=row[5],
                    content_type=row[6],
                    source_ip=row[7],
                    row_hash=row[8],
                ))
    except Exception as exc:
        logger.error("Audit log query failed: %s", exc)

    return AuditListResponse(entries=entries, total=total, page=page, page_size=page_size)


@router.get("/verify-chain")
async def verify_chain(db_session: object = Query(default=None)) -> dict[str, Any]:
    """Verify hash chain integrity for the most recent 1000 rows."""
    from src.audit.logger import AuditLogger
    logger_instance = AuditLogger()
    valid = await logger_instance.verify_chain(limit=1000)
    return {"chain_valid": valid}
