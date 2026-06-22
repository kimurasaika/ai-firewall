"""Whitelist management — CRUD for LLM domain entries."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/whitelist", tags=["whitelist"])

_WHITELIST_PATH = Path("config/domains/llm_whitelist.yaml")


def _load() -> dict[str, Any]:
    with _WHITELIST_PATH.open() as f:
        return yaml.safe_load(f)


def _save(data: dict[str, Any]) -> None:
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    with _WHITELIST_PATH.open("w") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)


class DomainEntry(BaseModel):
    domain: str
    provider: str
    active: bool = True


class DomainUpdate(BaseModel):
    active: bool


@router.get("")
async def list_domains() -> list[dict[str, Any]]:
    data = _load()
    return data.get("domains", [])


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_domain(entry: DomainEntry) -> dict[str, Any]:
    data = _load()
    domains: list[dict[str, Any]] = data.setdefault("domains", [])
    existing = {d["domain"] for d in domains}
    if entry.domain in existing:
        raise HTTPException(status_code=409, detail=f"Domain {entry.domain!r} already exists")
    new = entry.model_dump()
    domains.append(new)
    _save(data)
    logger.info("Domain added: %s", entry.domain)
    return new


@router.patch("/{domain:path}")
async def update_domain(domain: str, update: DomainUpdate) -> dict[str, Any]:
    data = _load()
    for entry in data.get("domains", []):
        if entry["domain"] == domain:
            entry["active"] = update.active
            _save(data)
            logger.info("Domain updated: %s active=%s", domain, update.active)
            return entry
    raise HTTPException(status_code=404, detail=f"Domain {domain!r} not found")


@router.delete("/{domain:path}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_domain(domain: str) -> None:
    data = _load()
    before = len(data.get("domains", []))
    data["domains"] = [d for d in data.get("domains", []) if d["domain"] != domain]
    if len(data["domains"]) == before:
        raise HTTPException(status_code=404, detail=f"Domain {domain!r} not found")
    _save(data)
    logger.info("Domain deleted: %s", domain)
