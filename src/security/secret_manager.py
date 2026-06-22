"""Secret manager — Vault in production, .env in dev."""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

import hvac
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class _EnvSettings(BaseSettings):
    """Reads all secrets from environment / .env file."""

    secret_manager: str = "env"
    vault_addr: str = "http://vault:8200"
    vault_token: str = ""
    vault_mount_path: str = "secret"
    vault_secret_path: str = "ai-firewall"

    redis_password: str = ""
    database_url: str = ""
    admin_jwt_secret: str = ""
    dashboard_api_key: str = ""
    slack_webhook_url: str = ""
    smtp_password: str = ""
    smtp_username: str = ""
    mitmproxy_ca_key: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache(maxsize=1)
def _settings() -> _EnvSettings:
    return _EnvSettings()


class SecretManager:
    """Unified interface for dev (.env) and production (Vault) secrets."""

    def __init__(self) -> None:
        cfg = _settings()
        self._mode = cfg.secret_manager
        self._vault_client: hvac.Client | None = None

        if self._mode == "vault":
            self._vault_client = hvac.Client(
                url=cfg.vault_addr,
                token=cfg.vault_token,
            )
            if not self._vault_client.is_authenticated():
                raise RuntimeError("Vault authentication failed")
            logger.info("SecretManager: using HashiCorp Vault at %s", cfg.vault_addr)
        else:
            logger.info("SecretManager: using .env (dev mode)")

        self._mount = cfg.vault_mount_path
        self._path = cfg.vault_secret_path
        self._cache: dict[str, Any] = {}

    def get(self, key: str) -> str:
        """Retrieve secret by key. Raises KeyError if not found."""
        if key in self._cache:
            return self._cache[key]

        if self._mode == "vault":
            value = self._get_from_vault(key)
        else:
            value = self._get_from_env(key)

        self._cache[key] = value
        return value

    def _get_from_vault(self, key: str) -> str:
        assert self._vault_client is not None
        secret = self._vault_client.secrets.kv.v2.read_secret_version(
            path=self._path,
            mount_point=self._mount,
        )
        data: dict[str, Any] = secret["data"]["data"]
        if key not in data:
            raise KeyError(f"Secret '{key}' not found in Vault path {self._path}")
        return str(data[key])

    @staticmethod
    def _get_from_env(key: str) -> str:
        env_key = key.upper()
        value = os.environ.get(env_key)
        if value is None:
            # Try pydantic settings as fallback
            cfg = _settings()
            value = getattr(cfg, key.lower(), None)
        if value is None:
            raise KeyError(f"Secret '{key}' not found in environment")
        return str(value)

    def invalidate_cache(self) -> None:
        self._cache.clear()


@lru_cache(maxsize=1)
def get_secret_manager() -> SecretManager:
    return SecretManager()


def get_secret(key: str) -> str:
    return get_secret_manager().get(key)
