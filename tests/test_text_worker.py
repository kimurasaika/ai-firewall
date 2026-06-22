"""Tests for TextWorker PII redaction."""
import pytest
from unittest.mock import MagicMock, patch

pytest.importorskip("presidio_analyzer", reason="presidio-analyzer not installed — pip install presidio-analyzer presidio-anonymizer")
pytest.importorskip("pythainlp", reason="pythainlp not installed — pip install pythainlp")

from src.workers.text_worker import TextWorker


@pytest.fixture
def worker():
    return TextWorker()


def test_redact_email(worker):
    text = "Send report to somchai@company.com please"
    redacted, mapping = worker.redact(text, language="en")
    assert "somchai@company.com" not in redacted
    assert len(mapping) >= 1
    assert "<<EM001>>" in redacted


def test_redact_phone_thai(worker):
    text = "โทรหาได้ที่ 0812345678"
    redacted, mapping = worker.redact(text, language="th")
    assert "0812345678" not in redacted
    assert len(mapping) >= 1


def test_redact_thai_id(worker):
    text = "เลขบัตร 1234567890123 ของลูกค้า"
    redacted, mapping = worker.redact(text, language="th")
    assert "1234567890123" not in redacted
    assert any("<<ID" in k for k in mapping.keys())


def test_same_value_same_token(worker):
    text = "สมชาย สมชาย สมชาย"
    _, mapping = worker.redact(text, language="th")
    # All occurrences map to one token
    assert len(mapping) <= 1


def test_no_pii_unchanged(worker):
    text = "The sky is blue today"
    redacted, mapping = worker.redact(text, language="en")
    assert mapping == {}
    assert redacted.strip() == text.strip()


def test_reset_counters(worker):
    worker.redact("Call 0812345678", language="th")
    worker.reset_counters()
    _, mapping = worker.redact("Email test@example.com", language="en")
    # After reset, counter starts from 1 again
    assert "<<EM001>>" in mapping


def test_redact_safe_returns_original_on_error(worker):
    with patch.object(worker, "redact", side_effect=RuntimeError("boom")):
        result, mapping = worker.redact_safe("hello world")
    assert result == "hello world"
    assert mapping == {}
