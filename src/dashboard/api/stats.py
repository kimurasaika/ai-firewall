"""Dashboard stats endpoint — redaction counts, error rates, session counts."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/stats", tags=["stats"])


class StatsResponse(BaseModel):
    total_redactions_24h: int
    total_sessions_24h: int
    deanon_miss_count_24h: int
    top_entity_types: dict[str, int]
    period_hours: int = 24


@router.get("", response_model=StatsResponse)
async def get_stats(db_session: object = Depends(lambda: None)) -> StatsResponse:
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    # Queries against TimescaleDB audit_log hypertable
    total_redactions = 0
    total_sessions = 0
    deanon_misses = 0
    entity_counts: dict[str, int] = {}

    try:
        if db_session is not None:
            result = await db_session.execute(  # type: ignore[attr-defined]
                sa.text("""
                    SELECT
                        COUNT(*) FILTER (WHERE event_type = 'redact') AS redactions,
                        COUNT(DISTINCT session_id) FILTER (WHERE event_type = 'redact') AS sessions,
                        COUNT(*) FILTER (WHERE event_type = 'deanon_miss') AS misses
                    FROM audit_log
                    WHERE created_at >= :since
                """),
                {"since": since},
            )
            row = result.fetchone()
            if row:
                total_redactions, total_sessions, deanon_misses = row

            entity_result = await db_session.execute(  # type: ignore[attr-defined]
                sa.text("""
                    SELECT entity_type, COUNT(*) AS cnt
                    FROM audit_log
                    WHERE event_type = 'redact' AND created_at >= :since
                    GROUP BY entity_type
                    ORDER BY cnt DESC
                    LIMIT 10
                """),
                {"since": since},
            )
            for row in entity_result:
                if row[0]:
                    entity_counts[row[0]] = int(row[1])
    except Exception as exc:
        logger.error("Stats query failed: %s", exc)

    return StatsResponse(
        total_redactions_24h=int(total_redactions),
        total_sessions_24h=int(total_sessions),
        deanon_miss_count_24h=int(deanon_misses),
        top_entity_types=entity_counts,
    )
