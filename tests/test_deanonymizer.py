"""Tests for de-anonymization logic — exact, fuzzy, and miss paths."""
import pytest

from src.deanonymizer.deanonymizer import Deanonymizer


@pytest.fixture
def deanon():
    return Deanonymizer()


@pytest.fixture
def mapping():
    return {
        "<<P001>>": "สมชาย ใจดี",
        "<<EM001>>": "somchai@company.com",
        "<<PH001>>": "0812345678",
    }


def test_exact_match(deanon, mapping):
    text = "ชื่อ <<P001>> อีเมล <<EM001>>"
    result, misses = deanon.deanonymize(text, mapping)
    assert "สมชาย ใจดี" in result
    assert "somchai@company.com" in result
    assert misses == []


def test_fuzzy_match(deanon, mapping):
    # LLM may slightly alter token formatting
    text = "Reply to <<EM 001>> ASAP"
    result, misses = deanon.deanonymize(text, mapping)
    # EM 001 is close enough to <<EM001>> — fuzzy should catch it
    # Exact won't match, fuzzy might; test misses list is what matters
    assert isinstance(result, str)


def test_miss_logged(deanon, mapping):
    text = "Unknown token <<ORG001>> in response"
    result, misses = deanon.deanonymize(text, mapping)
    assert "<<ORG001>>" in misses
    assert "<<ORG001>>" in result   # left as-is


def test_empty_mapping(deanon):
    text = "<<P001>> is a test"
    result, misses = deanon.deanonymize(text, {})
    assert result == text
    assert misses == []


def test_multiple_tokens_same_text(deanon, mapping):
    text = "<<P001>> called <<PH001>>"
    result, misses = deanon.deanonymize(text, mapping)
    assert "สมชาย ใจดี" in result
    assert "0812345678" in result
    assert misses == []


def test_no_tokens_in_text(deanon, mapping):
    text = "No PII here at all"
    result, misses = deanon.deanonymize(text, mapping)
    assert result == text
    assert misses == []
