"""Fail-safe watchdog — monitors orchestrator health and alerts admin on crash."""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.mime.text import MIMEText

import httpx
from slack_sdk.webhook.async_client import AsyncWebhookClient

from src.observability.metrics import fail_safe_active
from src.security.secret_manager import get_secret

logger = logging.getLogger(__name__)

_HEALTH_URL = "https://orchestrator:8443/health"
_CHECK_INTERVAL = 10   # seconds
_MAX_FAILURES = 3


class FailSafeWatchdog:
    """Continuously polls orchestrator health; activates fail-safe on consecutive failures."""

    def __init__(self, mtls_client: httpx.AsyncClient) -> None:
        self._client = mtls_client
        self._failures = 0
        self._active = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())
        logger.info("FailSafeWatchdog started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    @property
    def is_active(self) -> bool:
        return self._active

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(_CHECK_INTERVAL)
            try:
                resp = await self._client.get(_HEALTH_URL, timeout=5)
                if resp.status_code == 200:
                    self._failures = 0
                    if self._active:
                        self._active = False
                        fail_safe_active.set(0)
                        logger.info("FailSafe deactivated — orchestrator recovered")
                else:
                    self._failures += 1
            except Exception as exc:
                self._failures += 1
                logger.warning("FailSafe health check failed (%d/%d): %s", self._failures, _MAX_FAILURES, exc)

            if self._failures >= _MAX_FAILURES and not self._active:
                self._active = True
                fail_safe_active.set(1)
                logger.critical("FailSafe ACTIVATED — blocking all LLM domains")
                asyncio.create_task(self._alert())

    async def _alert(self) -> None:
        """Send email + Slack alert when fail-safe activates."""
        message = (
            "CRITICAL: AI Firewall DLP Orchestrator is unreachable.\n"
            "LLM domains are now BLOCKED for all users.\n"
            "Please investigate immediately."
        )
        await asyncio.gather(
            self._send_email(message),
            self._send_slack(message),
            return_exceptions=True,
        )

    async def _send_slack(self, message: str) -> None:
        try:
            webhook_url = get_secret("slack_webhook_url")
            client = AsyncWebhookClient(webhook_url)
            await client.send(text=f":rotating_light: {message}")
        except Exception as exc:
            logger.error("Slack alert failed: %s", exc)

    async def _send_email(self, message: str) -> None:
        try:
            import os
            smtp_host = os.environ.get("SMTP_HOST", "smtp.company.local")
            smtp_port = int(os.environ.get("SMTP_PORT", "587"))
            smtp_user = get_secret("smtp_username")
            smtp_pass = get_secret("smtp_password")
            alert_from = os.environ.get("ALERT_FROM", "dlp-alert@company.local")
            alert_to = os.environ.get("ALERT_TO", "it-admin@company.local")

            msg = MIMEText(message)
            msg["Subject"] = "[CRITICAL] AI Firewall DLP Crash — LLM Domains Blocked"
            msg["From"] = alert_from
            msg["To"] = alert_to

            ctx = ssl.create_default_context()
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls(context=ctx)
                server.login(smtp_user, smtp_pass)
                server.sendmail(alert_from, alert_to.split(","), msg.as_string())
        except Exception as exc:
            logger.error("Email alert failed: %s", exc)
