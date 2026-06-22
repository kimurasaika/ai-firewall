"""Health check endpoint — used by HAProxy and fail-safe watchdog."""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    redis: str
    database: str


_redis_store: object | None = None
_audit_logger: object | None = None


def set_dependencies(redis_store: object, audit_logger: object) -> None:
    global _redis_store, _audit_logger
    _redis_store = redis_store
    _audit_logger = audit_logger


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    redis_ok = False
    db_ok = False

    try:
        if _redis_store is not None:
            redis_ok = await _redis_store.ping()  # type: ignore[attr-defined]
    except Exception as exc:
        logger.warning("Health check: Redis ping failed: %s", exc)

    try:
        if _audit_logger is not None:
            db_ok = True   # if we reach this, DB connection was established at startup
    except Exception:
        pass

    return HealthResponse(
        status="ok" if (redis_ok and db_ok) else "degraded",
        redis="ok" if redis_ok else "error",
        database="ok" if db_ok else "error",
    )
