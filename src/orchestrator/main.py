"""DLP Orchestrator — FastAPI service with mTLS, rate limiting, and observability."""
from __future__ import annotations

import logging
import os
import signal

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel

from src.audit.logger import AuditLogger
from src.mapping_store.redis_store import RedisStore
from src.observability.log_shipper import configure_logging
from src.observability.metrics import requests_total, start_metrics_server
from src.observability.tracer import setup_tracer
from src.orchestrator.health import router as health_router
from src.orchestrator.health import set_dependencies as set_health_deps
from src.orchestrator.rate_limiter import RateLimiter
from src.orchestrator.router import Router
from src.security.mtls import build_server_ssl_context

configure_logging("orchestrator", os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

setup_tracer("orchestrator")

app = FastAPI(title="DLP Orchestrator", version="1.0.0")
FastAPIInstrumentor.instrument_app(app)
app.include_router(health_router)

_redis_store: RedisStore | None = None
_audit_logger: AuditLogger | None = None
_router: Router | None = None
_rate_limiter: RateLimiter | None = None


@app.on_event("startup")
async def startup() -> None:
    global _redis_store, _audit_logger, _router, _rate_limiter
    _redis_store = RedisStore()
    _audit_logger = AuditLogger()
    await _audit_logger.initialize()
    _router = Router()
    _rate_limiter = RateLimiter(_redis_store._client)
    set_health_deps(_redis_store, _audit_logger)
    start_metrics_server(port=int(os.environ.get("METRICS_PORT", "9090")))
    logger.info("Orchestrator startup complete")


@app.on_event("shutdown")
async def shutdown() -> None:
    """Graceful shutdown: flush in-flight requests, close Redis."""
    logger.info("Orchestrator shutting down")
    if _redis_store:
        await _redis_store.close()


# ── Request / Response models ───────────────────────────────────────────────────

class RedactRequest(BaseModel):
    content: str         # base64-encoded bytes or plain text
    content_type: str    # MIME type
    session_id: str | None = None
    user_id: str = "anonymous"
    is_base64: bool = False


class RedactResponse(BaseModel):
    redacted_content: str
    session_id: str
    entities_found: int
    is_base64: bool


class DeanonRequest(BaseModel):
    content: str
    session_id: str
    user_id: str = "anonymous"
    is_base64: bool = False


class DeanonResponse(BaseModel):
    content: str
    session_id: str
    is_base64: bool


# ── Endpoints ───────────────────────────────────────────────────────────────────

@app.post("/v1/redact", response_model=RedactResponse)
async def redact(req: RedactRequest, request: Request) -> RedactResponse:
    assert _rate_limiter and _router and _redis_store and _audit_logger

    await _rate_limiter.check(req.user_id, request)

    import base64
    raw = base64.b64decode(req.content) if req.is_base64 else req.content.encode()

    redacted_bytes, mapping, session_id = await _router.dispatch(
        raw, req.content_type, req.session_id
    )

    if mapping:
        await _redis_store.store_bulk(session_id, mapping)
        await _audit_logger.log(
            session_id=session_id,
            event_type="redact",
            entity_type=",".join(set(t[:2] for t in mapping)),
            content_type=req.content_type,
            source_ip=request.client.host if request.client else None,
        )

    requests_total.labels(service="orchestrator", status="ok").inc()

    redacted_str = (
        base64.b64encode(redacted_bytes).decode()
        if req.is_base64
        else redacted_bytes.decode("utf-8", errors="replace")
    )
    return RedactResponse(
        redacted_content=redacted_str,
        session_id=session_id,
        entities_found=len(mapping),
        is_base64=req.is_base64,
    )


@app.post("/v1/deanonymize", response_model=DeanonResponse)
async def deanonymize(req: DeanonRequest, request: Request) -> DeanonResponse:
    from src.deanonymizer.deanonymizer import Deanonymizer

    assert _redis_store and _audit_logger

    import base64
    raw = base64.b64decode(req.content) if req.is_base64 else req.content.encode()

    mapping = await _redis_store.get_mapping(req.session_id)
    deanon = Deanonymizer()
    result_text, misses = deanon.deanonymize(raw.decode("utf-8", errors="replace"), mapping)

    # Clear mapping from memory immediately after use
    await _redis_store.clear_session(req.session_id)

    if misses:
        for token in misses:
            logger.warning(
                "Deanonymization miss: session=%s token=%s",
                req.session_id, token,
                extra={"session_id": req.session_id, "token": token},
            )
            await _audit_logger.log(
                session_id=req.session_id,
                event_type="deanon_miss",
                token=token,
                source_ip=request.client.host if request.client else None,
            )

    requests_total.labels(service="orchestrator", status="ok").inc()
    result_bytes = result_text.encode("utf-8")
    return DeanonResponse(
        content=(
            base64.b64encode(result_bytes).decode()
            if req.is_base64
            else result_text
        ),
        session_id=req.session_id,
        is_base64=req.is_base64,
    )


if __name__ == "__main__":
    import ssl as _ssl
    _is_dev = os.environ.get("ENVIRONMENT", "dev") == "dev"
    uvicorn.run(
        "src.orchestrator.main:app",
        host=os.environ.get("ORCHESTRATOR_HOST", "0.0.0.0"),
        port=int(os.environ.get("ORCHESTRATOR_PORT", "8443")),
        ssl_keyfile="/app/certs/mtls/orchestrator.key",
        ssl_certfile="/app/certs/mtls/orchestrator.crt",
        ssl_ca_certs="/app/certs/ca.crt",
        ssl_cert_reqs=_ssl.CERT_NONE if _is_dev else _ssl.CERT_REQUIRED,
        workers=int(os.environ.get("ORCHESTRATOR_WORKERS", "2")),
    )
