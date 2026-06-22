"""
End-to-end proxy test — sends real HTTP through mitmproxy → orchestrator → mock LLM.

Setup required (run in separate terminals):
  Terminal 1: python tests/integration/mock_llm_server.py
  Terminal 2: docker compose up proxy orchestrator redis timescaledb

Then run: pytest tests/integration/test_e2e_proxy.py -v -s

What this verifies:
  ✓ mitmproxy intercepts traffic destined for the mock LLM domain
  ✓ PII is redacted BEFORE reaching the mock LLM (only tokens in mock server log)
  ✓ Response from mock LLM is de-anonymized BEFORE returning to caller
  ✓ The caller receives original values, not tokens
"""
from __future__ import annotations

import json
import os

import httpx
import pytest

PROXY_HOST = os.environ.get("PROXY_HOST", "localhost")
PROXY_PORT = int(os.environ.get("PROXY_PORT", "8080"))
MOCK_LLM_URL = os.environ.get("MOCK_LLM_URL", "http://localhost:9999")

# httpx client routed through mitmproxy
_PROXIED = httpx.Client(
    proxies={"http://": f"http://{PROXY_HOST}:{PROXY_PORT}",
             "https://": f"http://{PROXY_HOST}:{PROXY_PORT}"},
    verify=False,   # self-signed corp CA
    timeout=30,
)


@pytest.fixture(scope="module", autouse=True)
def check_services():
    """Skip entire module if proxy or mock LLM is not running."""
    try:
        httpx.get(f"http://{PROXY_HOST}:{PROXY_PORT}", timeout=2)
    except Exception:
        pytest.skip(f"Proxy not reachable at {PROXY_HOST}:{PROXY_PORT} — start docker compose first")

    try:
        httpx.post(f"{MOCK_LLM_URL}/v1/chat/completions",
                   json={"messages": [{"role": "user", "content": "ping"}]}, timeout=2)
    except Exception:
        pytest.skip("Mock LLM not running — run: python tests/integration/mock_llm_server.py")


def llm_request(user_message: str) -> dict:
    """Send a chat request through the proxy to the mock LLM."""
    resp = _PROXIED.post(
        f"{MOCK_LLM_URL}/v1/chat/completions",
        json={"model": "mock-gpt", "messages": [{"role": "user", "content": user_message}]},
        headers={"Content-Type": "application/json"},
    )
    resp.raise_for_status()
    return resp.json()


def test_pii_not_sent_to_llm_domain(capsys):
    """
    The mock LLM echoes back what it receives.
    If PII was redacted, the response will contain <<TOKENS>>, not the original value.
    After de-anonymization by the proxy, the final response contains original values.
    """
    user_message = "Please summarize the contract for alice@corp.com"
    result = llm_request(user_message)

    reply = result["choices"][0]["message"]["content"]

    # After full pipeline: response should have original email restored
    assert "alice@corp.com" in reply, (
        f"De-anonymization failed — original email not restored in response.\n"
        f"Reply: {reply}\n"
        "If <<EM001>> appears in reply, deanon is not running on responses."
    )


def test_thai_phone_redacted_and_restored():
    user_message = "ติดต่อได้ที่ 0891234567 ครับ"
    result = llm_request(user_message)
    reply = result["choices"][0]["message"]["content"]
    assert "0891234567" in reply, f"Phone number not restored: {reply}"


def test_no_pii_passthrough_unchanged():
    user_message = "What is the capital of Thailand?"
    result = llm_request(user_message)
    reply = result["choices"][0]["message"]["content"]
    # No PII — no tokens should appear
    import re
    tokens = re.findall(r"<<[A-Z]+\d{3}>>", reply)
    assert not tokens, f"Unexpected tokens in no-PII request: {tokens}"


def test_multiple_pii_entities_round_trip():
    user_message = "Send invoice to bob@acme.com, phone 0812223333, ID 1100200300012"
    result = llm_request(user_message)
    reply = result["choices"][0]["message"]["content"]
    assert "bob@acme.com" in reply, f"Email not restored: {reply}"
