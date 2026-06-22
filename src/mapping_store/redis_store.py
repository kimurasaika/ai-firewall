"""Redis-backed session mapping store with TLS + password auth.

Keys:   session:{session_id}:map     → JSON dict {token: original_value}
TTL:    1 hour (from config/redis.yaml)
Clear:  call clear_session() immediately after de-anonymization completes.
"""
from __future__ import annotations

import json
import logging
import os
import ssl
from typing import Any

import redis.asyncio as aioredis

from src.observability.metrics import redis_errors_total, redis_sessions_active
from src.security.secret_manager import get_secret

logger = logging.getLogger(__name__)

_TTL = int(os.environ.get("REDIS_TTL_SECONDS", "3600"))
_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
_PORT = int(os.environ.get("REDIS_PORT", "6379"))
_USE_TLS = os.environ.get("REDIS_TLS", "true").lower() == "true"
_CA_CERT = os.environ.get("REDIS_TLS_CA", "/app/certs/ca.crt")
_CLIENT_CERT = os.environ.get("REDIS_TLS_CERT", "/app/certs/redis/client.crt")
_CLIENT_KEY = os.environ.get("REDIS_TLS_KEY", "/app/certs/redis/client.key")


def _build_ssl_context() -> ssl.SSLContext | None:
    return None  # replaced by native redis-py ssl params in RedisStore.__init__


def _session_key(session_id: str) -> str:
    return f"session:{session_id}:map"


class RedisStore:
    """Async Redis client for session token ↔ original-value mappings."""

    def __init__(self) -> None:
        password = get_secret("redis_password")
        ssl_kwargs: dict = {}
        if _USE_TLS:
            ssl_kwargs = {
                "ssl": True,
                "ssl_certfile": _CLIENT_CERT,
                "ssl_keyfile": _CLIENT_KEY,
                "ssl_ca_certs": _CA_CERT,
                "ssl_cert_reqs": "none",   # self-signed CA — skip server cert verify
                "ssl_check_hostname": False,
            }
        self._client: aioredis.Redis = aioredis.Redis(
            host=_HOST,
            port=_PORT,
            password=password,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=3,
            retry_on_timeout=True,
            health_check_interval=30,
            **ssl_kwargs,
        )
        logger.info("RedisStore initialized: %s:%d tls=%s", _HOST, _PORT, _USE_TLS)

    async def store_mapping(
        self,
        session_id: str,
        token: str,
        original_value: str,
    ) -> None:
        """Add a single token → original_value entry for a session."""
        key = _session_key(session_id)
        try:
            pipe = self._client.pipeline()
            pipe.hset(key, token, original_value)
            pipe.expire(key, _TTL)
            await pipe.execute()
        except Exception as exc:
            redis_errors_total.labels(operation="store").inc()
            logger.error("Redis store_mapping error: session=%s token=%s err=%s", session_id, token, exc)
            raise

    async def store_bulk(self, session_id: str, mapping: dict[str, str]) -> None:
        """Store all token → value pairs for a session in one pipeline."""
        if not mapping:
            return
        key = _session_key(session_id)
        try:
            pipe = self._client.pipeline()
            pipe.hset(key, mapping=mapping)
            pipe.expire(key, _TTL)
            await pipe.execute()
            redis_sessions_active.inc()
        except Exception as exc:
            redis_errors_total.labels(operation="bulk_store").inc()
            logger.error("Redis store_bulk error: session=%s err=%s", session_id, exc)
            raise

    async def get_mapping(self, session_id: str) -> dict[str, str]:
        """Retrieve full token → original_value mapping for a session."""
        key = _session_key(session_id)
        try:
            data = await self._client.hgetall(key)
            return data or {}
        except Exception as exc:
            redis_errors_total.labels(operation="get").inc()
            logger.error("Redis get_mapping error: session=%s err=%s", session_id, exc)
            raise

    async def clear_session(self, session_id: str) -> None:
        """Delete session mapping from Redis. Call immediately after de-anonymization."""
        key = _session_key(session_id)
        try:
            await self._client.delete(key)
            redis_sessions_active.dec()
            logger.debug("Redis session cleared: session=%s", session_id)
        except Exception as exc:
            redis_errors_total.labels(operation="clear").inc()
            logger.error("Redis clear_session error: session=%s err=%s", session_id, exc)
            raise

    async def ttl(self, session_id: str) -> int:
        """Return remaining TTL in seconds for a session, or -2 if not found."""
        key = _session_key(session_id)
        return await self._client.ttl(key)

    async def ping(self) -> bool:
        try:
            return await self._client.ping()
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
