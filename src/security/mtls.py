"""mTLS helpers for inter-service communication."""
from __future__ import annotations

import logging
import os
import ssl
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_CA_CERT = os.environ.get("MTLS_CA_CERT", "/app/certs/ca.crt")
_CERT_DIR = Path(os.environ.get("MTLS_CERT_DIR", "/app/certs/mtls"))


def _cert_pair(service: str) -> tuple[str, str]:
    """Return (cert_path, key_path) for a named service."""
    cert = str(_CERT_DIR / f"{service}.crt")
    key = str(_CERT_DIR / f"{service}.key")
    for path in (cert, key):
        if not Path(path).exists():
            raise FileNotFoundError(f"mTLS cert not found: {path}")
    return cert, key


def build_server_ssl_context(service: str) -> ssl.SSLContext:
    """SSLContext for a service acting as server (verifies client certs)."""
    cert, key = _cert_pair(service)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(cert, key)
    ctx.load_verify_locations(_CA_CERT)
    ctx.verify_mode = ssl.CERT_REQUIRED
    logger.debug("mTLS server context built for service=%s", service)
    return ctx


def build_client_ssl_context(service: str) -> ssl.SSLContext:
    """SSLContext for a service acting as client (presents its own cert)."""
    cert, key = _cert_pair(service)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(cert, key)
    ctx.load_verify_locations(_CA_CERT)
    ctx.check_hostname = False   # internal hostnames may not match CN
    ctx.verify_mode = ssl.CERT_REQUIRED
    logger.debug("mTLS client context built for service=%s", service)
    return ctx


def build_httpx_client(caller_service: str, timeout: float = 30.0) -> httpx.AsyncClient:
    """Return an httpx.AsyncClient configured with mTLS for internal calls."""
    cert, key = _cert_pair(caller_service)
    return httpx.AsyncClient(
        cert=(cert, key),
        verify=_CA_CERT,
        timeout=timeout,
    )
