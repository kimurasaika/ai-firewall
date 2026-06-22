"""Tests for AuditLogger hash chain integrity."""
import os
import pytest

pytest.importorskip("sqlalchemy", reason="sqlalchemy not installed — pip install sqlalchemy")

# Set DATABASE_URL before any import that reads it at module level
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")

import src.audit.logger as _audit_module  # explicit import so patch path resolves
from src.audit.logger import AuditLogger


@pytest.fixture
def logger_instance():
    al = AuditLogger.__new__(AuditLogger)
    al._last_hash = "GENESIS"
    return al


def test_hash_chain_deterministic(logger_instance):
    row_data = {
        "id": "abc",
        "created_at": "2026-01-01T00:00:00",
        "session_id": "sess1",
        "event_type": "redact",
        "entity_type": "PERSON",
        "token": "<<P001>>",
        "content_type": "text/plain",
    }
    h1 = logger_instance._compute_hash(row_data, "GENESIS")
    h2 = logger_instance._compute_hash(row_data, "GENESIS")
    assert h1 == h2, "Hash must be deterministic"
    assert len(h1) == 64, "SHA-256 hex must be 64 chars"


def test_hash_changes_with_prev(logger_instance):
    row_data = {
        "id": "abc",
        "created_at": "2026-01-01T00:00:00",
        "session_id": "sess1",
        "event_type": "redact",
        "entity_type": "PERSON",
        "token": "<<P001>>",
        "content_type": "text/plain",
    }
    h1 = logger_instance._compute_hash(row_data, "GENESIS")
    h2 = logger_instance._compute_hash(row_data, "different_prev")
    assert h1 != h2, "Hash must change when prev_hash changes"


def test_hash_changes_with_data(logger_instance):
    base = {
        "id": "abc",
        "created_at": "2026-01-01T00:00:00",
        "session_id": "sess1",
        "event_type": "redact",
        "entity_type": "PERSON",
        "token": "<<P001>>",
        "content_type": "text/plain",
    }
    tampered = {**base, "token": "<<P002>>"}
    h1 = logger_instance._compute_hash(base, "GENESIS")
    h2 = logger_instance._compute_hash(tampered, "GENESIS")
    assert h1 != h2, "Hash must change when row data is tampered"


def test_no_pii_in_log_fields(logger_instance):
    """Ensure the logger API only accepts token, never original PII value."""
    import inspect
    sig = inspect.signature(AuditLogger.log)
    params = set(sig.parameters.keys())
    forbidden = {"original_value", "pii_value", "raw_value", "plaintext"}
    overlap = params & forbidden
    assert not overlap, f"PII leak risk — forbidden params in log() signature: {overlap}"


def test_hash_chain_links_correctly(logger_instance):
    """Second row's prev_hash must equal first row's row_hash."""
    row1 = {
        "id": "1", "created_at": "2026-01-01T00:00:00",
        "session_id": "s", "event_type": "redact",
        "entity_type": "EMAIL_ADDRESS", "token": "<<EM001>>", "content_type": "text/plain",
    }
    h1 = logger_instance._compute_hash(row1, "GENESIS")

    row2 = {
        "id": "2", "created_at": "2026-01-01T00:00:01",
        "session_id": "s", "event_type": "redact",
        "entity_type": "PHONE_NUMBER", "token": "<<PH001>>", "content_type": "text/plain",
    }
    h2 = logger_instance._compute_hash(row2, h1)  # chain: prev_hash = h1

    # If we recompute with wrong prev, it differs
    h2_wrong = logger_instance._compute_hash(row2, "WRONG_PREV")
    assert h2 != h2_wrong, "Hash chain broken — prev_hash not included"
