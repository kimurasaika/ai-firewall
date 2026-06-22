"""
Integration tests against the running Orchestrator API.
Requires: docker compose up orchestrator redis timescaledb

Run: pytest tests/integration/test_orchestrator_api.py -v
     ORCHESTRATOR_URL=https://localhost:8443 pytest tests/integration/test_orchestrator_api.py -v
"""
from __future__ import annotations

import os
import uuid

import httpx
import pytest

BASE = os.environ.get("ORCHESTRATOR_URL", "https://localhost:8443")
# Skip TLS verification in dev (self-signed cert)
CLIENT = httpx.Client(verify=False, timeout=30)


def post(path: str, payload: dict) -> httpx.Response:
    return CLIENT.post(f"{BASE}{path}", json=payload)


# ── Health ────────────────────────────────────────────────────────────────────────

def test_health_returns_ok():
    resp = CLIENT.get(f"{BASE}/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")


# ── Redact endpoint ───────────────────────────────────────────────────────────────

def test_redact_plain_text_removes_email():
    resp = post("/v1/redact", {
        "content": "Please contact john.doe@acme.com for the proposal",
        "content_type": "text/plain",
        "user_id": "test-user",
        "is_base64": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "john.doe@acme.com" not in data["redacted_content"], \
        f"Email leaked: {data['redacted_content']}"
    assert data["entities_found"] >= 1
    assert data["session_id"]


def test_redact_thai_phone():
    resp = post("/v1/redact", {
        "content": "โทรหาได้ที่เบอร์ 0891234567 ครับ",
        "content_type": "text/plain",
        "user_id": "test-user",
        "is_base64": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "0891234567" not in data["redacted_content"], \
        f"Phone leaked: {data['redacted_content']}"


def test_redact_thai_id_card():
    resp = post("/v1/redact", {
        "content": "เลขบัตรประชาชน 1234567890123 ของลูกค้า",
        "content_type": "text/plain",
        "user_id": "test-user",
        "is_base64": False,
    })
    assert resp.status_code == 200
    assert "1234567890123" not in resp.json()["redacted_content"]


def test_redact_no_pii_entities_found_zero():
    resp = post("/v1/redact", {
        "content": "The weather is nice today",
        "content_type": "text/plain",
        "user_id": "test-user",
        "is_base64": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["entities_found"] == 0
    assert data["redacted_content"].strip() == "The weather is nice today"


def test_redact_returns_unique_session_per_request():
    def do_redact():
        return post("/v1/redact", {
            "content": "test@example.com",
            "content_type": "text/plain",
            "user_id": "test-user",
            "is_base64": False,
        }).json()["session_id"]

    s1, s2 = do_redact(), do_redact()
    assert s1 != s2, "Session IDs must be unique"


# ── Deanonymize endpoint ──────────────────────────────────────────────────────────

def test_deanonymize_restores_original_value():
    # Step 1: redact
    redact_resp = post("/v1/redact", {
        "content": "Email alice@secret.com for details",
        "content_type": "text/plain",
        "user_id": "test-user",
        "is_base64": False,
    })
    assert redact_resp.status_code == 200
    redact_data = redact_resp.json()
    session_id = redact_data["session_id"]
    redacted_content = redact_data["redacted_content"]

    assert "alice@secret.com" not in redacted_content

    # Step 2: deanonymize
    deanon_resp = post("/v1/deanonymize", {
        "content": redacted_content,
        "session_id": session_id,
        "user_id": "test-user",
        "is_base64": False,
    })
    assert deanon_resp.status_code == 200
    restored = deanon_resp.json()["content"]
    assert "alice@secret.com" in restored, f"Value not restored: {restored}"


def test_deanonymize_clears_session_after_use():
    """After deanonymization, the session mapping must be gone from Redis."""
    redact_resp = post("/v1/redact", {
        "content": "Call 0811112222 now",
        "content_type": "text/plain",
        "user_id": "test-user",
        "is_base64": False,
    })
    session_id = redact_resp.json()["session_id"]
    redacted = redact_resp.json()["redacted_content"]

    # First deanon — should work
    post("/v1/deanonymize", {
        "content": redacted,
        "session_id": session_id,
        "user_id": "test-user",
        "is_base64": False,
    })

    # Second deanon with same session — mapping already cleared, tokens become misses
    resp2 = post("/v1/deanonymize", {
        "content": redacted,
        "session_id": session_id,
        "user_id": "test-user",
        "is_base64": False,
    })
    assert resp2.status_code == 200
    # Tokens not restored (mapping gone) — they remain as <<PH001>> in response
    content = resp2.json()["content"]
    assert "0811112222" not in content or "<<PH" in content


def test_multiple_entity_types_round_trip():
    original = "Contact bob@test.com or call 0899998888"
    redact_resp = post("/v1/redact", {
        "content": original,
        "content_type": "text/plain",
        "user_id": "test-user",
        "is_base64": False,
    })
    data = redact_resp.json()
    session_id = data["session_id"]
    redacted = data["redacted_content"]

    assert "bob@test.com" not in redacted

    deanon_resp = post("/v1/deanonymize", {
        "content": redacted,
        "session_id": session_id,
        "user_id": "test-user",
        "is_base64": False,
    })
    restored = deanon_resp.json()["content"]
    assert "bob@test.com" in restored


# ── Rate limiting ─────────────────────────────────────────────────────────────────

def test_rate_limiter_returns_429_after_burst():
    """Hammering the endpoint with the same user_id should eventually hit 429."""
    hit_429 = False
    for _ in range(120):   # exceed 60/min limit
        r = post("/v1/redact", {
            "content": "test@example.com",
            "content_type": "text/plain",
            "user_id": "rate-limit-test-user",
            "is_base64": False,
        })
        if r.status_code == 429:
            hit_429 = True
            break
    assert hit_429, "Rate limiter did not trigger after 120 requests"
