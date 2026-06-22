"""mitmproxy addon — intercepts HTTPS traffic to LLM domains, sends to DLP Orchestrator."""
from __future__ import annotations

import base64
import json
import logging
import os
import uuid

import httpx
from mitmproxy import ctx, http

from src.observability.log_shipper import configure_logging
from src.observability.tracer import setup_tracer
from src.proxy.ssl_inspector import load_llm_domains
from src.security.mtls import build_httpx_client
from src.security.secret_manager import get_secret

configure_logging("proxy")
logger = logging.getLogger(__name__)
setup_tracer("proxy")

_ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "https://orchestrator:8443")
_FAIL_SAFE_ACTIVE = False  # updated by watchdog via IPC or shared state file


def _is_fail_safe_active() -> bool:
    """Check fail-safe state from shared file written by watchdog."""
    try:
        import json
        path = "/tmp/dlp_failsafe.json"
        with open(path) as f:
            data = json.load(f)
        return data.get("active", False)
    except Exception:
        return False


class DLPInterceptor:
    """mitmproxy addon that intercepts traffic to LLM domains."""

    def __init__(self) -> None:
        self._llm_domains: set[str] = set()
        self._client: httpx.AsyncClient | None = None

    def load(self, loader: object) -> None:
        self._llm_domains = load_llm_domains()
        is_dev = os.environ.get("ENVIRONMENT", "dev") == "dev"
        if is_dev:
            # In dev, skip mTLS cert verification to avoid self-signed CA chain issues
            self._client = httpx.AsyncClient(verify=False, timeout=30)
        else:
            self._client = build_httpx_client("proxy")
        logger.info("DLPInterceptor loaded: %d domains monitored (dev=%s)", len(self._llm_domains), is_dev)

    def _is_llm_domain(self, host: str) -> bool:
        return any(host == d or host.endswith("." + d) for d in self._llm_domains)

    async def request(self, flow: http.HTTPFlow) -> None:
        host = flow.request.pretty_host

        if not self._is_llm_domain(host):
            return  # pass-through for non-LLM traffic

        if _is_fail_safe_active():
            flow.response = http.Response.make(
                503,
                b"AI tools are temporarily unavailable. Please contact IT support.",
                {"Content-Type": "text/plain"},
            )
            logger.warning("FailSafe: blocked request to LLM domain=%s", host)
            return

        session_id = str(uuid.uuid4())
        flow.metadata["dlp_session_id"] = session_id

        content = flow.request.content or b""
        if not content:
            return  # GET / HEAD / empty body — nothing to redact

        content_type = flow.request.headers.get("content-type", "text/plain")
        is_binary = not content_type.startswith("text") and "json" not in content_type

        payload = {
            "content": base64.b64encode(content).decode() if is_binary else content.decode("utf-8", errors="replace"),
            "content_type": content_type,
            "session_id": session_id,
            "user_id": flow.request.headers.get("x-user-id", "unknown"),
            "is_base64": is_binary,
        }

        try:
            assert self._client
            resp = await self._client.post(
                f"{_ORCHESTRATOR_URL}/v1/redact",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            redacted = data["redacted_content"]
            flow.metadata["dlp_session_id"] = data["session_id"]

            if is_binary:
                flow.request.content = base64.b64decode(redacted)
            else:
                flow.request.content = redacted.encode("utf-8")

        except Exception as exc:
            logger.error("DLP redact failed: session=%s host=%s err=%s", session_id, host, exc)
            # Fail-safe: block this request rather than send unredacted PII
            flow.response = http.Response.make(
                503,
                b"DLP processing error. Request blocked for security.",
                {"Content-Type": "text/plain"},
            )

    async def response(self, flow: http.HTTPFlow) -> None:
        session_id = flow.metadata.get("dlp_session_id")
        if not session_id:
            return

        content = flow.response.content or b""
        content_type = flow.response.headers.get("content-type", "text/plain")
        is_binary = not content_type.startswith("text") and "json" not in content_type

        payload = {
            "content": base64.b64encode(content).decode() if is_binary else content.decode("utf-8", errors="replace"),
            "session_id": session_id,
            "user_id": "system",
            "is_base64": is_binary,
        }

        try:
            assert self._client
            resp = await self._client.post(
                f"{_ORCHESTRATOR_URL}/v1/deanonymize",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            restored = data["content"]

            if is_binary:
                flow.response.content = base64.b64decode(restored)
            else:
                flow.response.content = restored.encode("utf-8")

        except Exception as exc:
            logger.error("DLP deanon failed: session=%s err=%s", session_id, exc)
            # Return response as-is; don't break user experience for deanon failures


addons = [DLPInterceptor()]
