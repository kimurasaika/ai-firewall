"""LLM domain whitelist updater — runs on cron schedule via APScheduler."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.observability.log_shipper import configure_logging
from src.observability.tracer import setup_tracer

configure_logging("domain_updater", os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)
setup_tracer("domain_updater")

_WHITELIST_PATH = Path("config/domains/llm_whitelist.yaml")
_SCHEDULE_CRON = os.environ.get("DOMAIN_UPDATE_CRON", "0 2 * * *")   # daily 02:00


def _load_whitelist() -> dict[str, Any]:
    with _WHITELIST_PATH.open() as f:
        return yaml.safe_load(f)


def _save_whitelist(data: dict[str, Any]) -> None:
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    with _WHITELIST_PATH.open("w") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    logger.info("Whitelist saved: %d domains", len(data.get("domains", [])))


async def update_domains() -> None:
    """Check for newly discovered LLM domains and merge into whitelist (pending approval)."""
    logger.info("Domain update job started")
    try:
        data = _load_whitelist()
        existing = {entry["domain"] for entry in data.get("domains", [])}

        # Auto-update from source_urls (if configured)
        source_urls: list[str] = data.get("auto_update", {}).get("source_urls", [])
        require_approval: bool = data.get("auto_update", {}).get("require_admin_approval", True)
        new_domains: list[str] = []

        if source_urls:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                for url in source_urls:
                    try:
                        resp = await client.get(url)
                        resp.raise_for_status()
                        fetched = resp.json()
                        new_domains.extend(fetched.get("domains", []))
                    except Exception as exc:
                        logger.warning("Failed to fetch domain list from %s: %s", url, exc)

        added = 0
        for domain in new_domains:
            if domain not in existing:
                data["domains"].append({
                    "domain": domain,
                    "provider": "auto-detected",
                    "active": not require_approval,   # inactive until admin approves
                })
                existing.add(domain)
                added += 1
                logger.info("New domain queued: %s (active=%s)", domain, not require_approval)

        if added > 0:
            _save_whitelist(data)

        logger.info("Domain update complete: %d new domains added", added)

    except Exception as exc:
        logger.error("Domain update failed: %s", exc, exc_info=True)


class DomainUpdaterService:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()

    def start(self) -> None:
        hour, minute = 2, 0  # default: daily at 02:00
        env_cron = os.environ.get("DOMAIN_UPDATE_CRON_HOUR", "2")
        try:
            hour = int(env_cron)
        except ValueError:
            pass

        self._scheduler.add_job(
            update_domains,
            trigger="cron",
            hour=hour,
            minute=minute,
            id="domain_update",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info("DomainUpdater scheduler started: daily at %02d:%02d", hour, minute)

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
