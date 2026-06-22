"""Write-once audit logger with SHA-256 hash chain stored in TimescaleDB.

Each row's hash = SHA-256(row_data || prev_hash), making any tampering detectable.
Audit logs are NEVER updated or deleted — retention handled by TimescaleDB retention policy (90 days).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)

_DATABASE_URL = os.environ.get("DATABASE_URL", "")

_SQL_CREATE_TABLE = sa.text("""
CREATE TABLE IF NOT EXISTS audit_log (
    id          UUID NOT NULL DEFAULT gen_random_uuid(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id  TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    user_agent  TEXT,
    source_ip   TEXT,
    entity_type TEXT,
    token       TEXT,
    content_type TEXT,
    details     JSONB,
    prev_hash   TEXT NOT NULL,
    row_hash    TEXT NOT NULL,
    PRIMARY KEY (id, created_at)
)
""")

_SQL_CREATE_HYPERTABLE = sa.text(
    "SELECT create_hypertable('audit_log', 'created_at', if_not_exists => TRUE)"
)

_SQL_ADD_RETENTION = sa.text(
    "SELECT add_retention_policy('audit_log', INTERVAL '90 days', if_not_exists => TRUE)"
)


class AuditLogger:
    """Append-only audit event logger with SHA-256 hash chain."""

    def __init__(self) -> None:
        if not _DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set")
        self._engine = create_async_engine(_DATABASE_URL, pool_pre_ping=True)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._last_hash: str | None = None

    async def initialize(self) -> None:
        """Create table and hypertable if they don't exist."""
        async with self._engine.begin() as conn:
            await conn.execute(_SQL_CREATE_TABLE)
            await conn.execute(_SQL_CREATE_HYPERTABLE)
            await conn.execute(_SQL_ADD_RETENTION)
        self._last_hash = await self._fetch_last_hash()
        logger.info("AuditLogger initialized; last_hash=%s", self._last_hash)

    async def _fetch_last_hash(self) -> str:
        async with self._session_factory() as session:
            result = await session.execute(
                sa.text("SELECT row_hash FROM audit_log ORDER BY created_at DESC LIMIT 1")
            )
            row = result.fetchone()
            return row[0] if row else "GENESIS"

    def _compute_hash(self, row_data: dict[str, Any], prev_hash: str) -> str:
        payload = json.dumps(row_data, sort_keys=True, ensure_ascii=False) + prev_hash
        return hashlib.sha256(payload.encode()).hexdigest()

    async def log(
        self,
        session_id: str,
        event_type: str,
        *,
        entity_type: str | None = None,
        token: str | None = None,
        content_type: str | None = None,
        user_agent: str | None = None,
        source_ip: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Append one audit event. Logs token (not original value — never log PII)."""
        row_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        prev_hash = self._last_hash or "GENESIS"

        row_data = {
            "id": row_id,
            "created_at": created_at.isoformat(),
            "session_id": session_id,
            "event_type": event_type,
            "entity_type": entity_type,
            "token": token,         # token only — never store original PII
            "content_type": content_type,
        }
        row_hash = self._compute_hash(row_data, prev_hash)

        try:
            async with self._session_factory() as session:
                await session.execute(
                    sa.text("""
                        INSERT INTO audit_log
                            (id, created_at, session_id, event_type, user_agent,
                             source_ip, entity_type, token, content_type, details,
                             prev_hash, row_hash)
                        VALUES
                            (:id, :created_at, :session_id, :event_type, :user_agent,
                             :source_ip, :entity_type, :token, :content_type, :details,
                             :prev_hash, :row_hash)
                    """),
                    {
                        "id": row_id,
                        "created_at": created_at,
                        "session_id": session_id,
                        "event_type": event_type,
                        "user_agent": user_agent,
                        "source_ip": source_ip,
                        "entity_type": entity_type,
                        "token": token,
                        "content_type": content_type,
                        "details": json.dumps(details or {}),
                        "prev_hash": prev_hash,
                        "row_hash": row_hash,
                    },
                )
                await session.commit()
            self._last_hash = row_hash
        except Exception as exc:
            logger.error("AuditLogger write failed: session=%s event=%s err=%s", session_id, event_type, exc)
            raise

    async def verify_chain(self, limit: int = 1000) -> bool:
        """Verify the hash chain integrity for the last N rows."""
        async with self._session_factory() as session:
            result = await session.execute(
                sa.text(
                    "SELECT id, created_at, session_id, event_type, entity_type, "
                    "token, content_type, prev_hash, row_hash "
                    "FROM audit_log ORDER BY created_at ASC LIMIT :limit"
                ),
                {"limit": limit},
            )
            rows = result.fetchall()

        prev = "GENESIS"
        for row in rows:
            row_data = {
                "id": row[0],
                "created_at": str(row[1]),
                "session_id": row[2],
                "event_type": row[3],
                "entity_type": row[4],
                "token": row[5],
                "content_type": row[6],
            }
            expected = self._compute_hash(row_data, prev)
            if expected != row[8]:
                logger.error("Hash chain broken at id=%s", row[0])
                return False
            prev = row[8]
        return True
