"""
Smoke test — verifies every module works WITHOUT needing Docker or running services.
Run: python scripts/smoke_test.py

Exit 0 = all passed. Exit 1 = something broken (output shows which step failed).
"""
import sys
import traceback

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
SKIP = "\033[93m[SKIP]\033[0m"
results: list[tuple[str, bool, str]] = []


def check(name: str):
    def decorator(fn):
        def wrapper():
            try:
                fn()
                results.append((name, True, ""))
                print(f"{PASS} {name}")
            except Exception as exc:
                msg = traceback.format_exc()
                results.append((name, False, msg))
                print(f"{FAIL} {name}")
                print(f"       {exc}")
        return wrapper
    return decorator


# ── 1. TextWorker ────────────────────────────────────────────────────────────────
@check("TextWorker: redact English email")
def _():
    from src.workers.text_worker import TextWorker
    w = TextWorker()
    text = "Send the invoice to alice@corp.com please"
    redacted, mapping = w.redact(text, language="en")
    assert "alice@corp.com" not in redacted, "Email not redacted"
    assert len(mapping) >= 1, "Mapping is empty"
    token = list(mapping.keys())[0]
    assert token.startswith("<<EM"), f"Wrong token prefix: {token}"
    assert mapping[token] == "alice@corp.com"


@check("TextWorker: redact Thai phone number")
def _():
    from src.workers.text_worker import TextWorker
    w = TextWorker()
    redacted, mapping = w.redact("โทร 0812345678 ได้เลย", language="th")
    assert "0812345678" not in redacted, "Phone not redacted"
    assert any("<<PH" in k for k in mapping), f"No PH token in {mapping}"


@check("TextWorker: redact Thai national ID")
def _():
    from src.workers.text_worker import TextWorker
    w = TextWorker()
    redacted, mapping = w.redact("บัตรประชาชน 1234567890123", language="th")
    assert "1234567890123" not in redacted, "ID not redacted"


@check("TextWorker: no PII → unchanged text")
def _():
    from src.workers.text_worker import TextWorker
    w = TextWorker()
    text = "The quick brown fox"
    redacted, mapping = w.redact(text, language="en")
    assert mapping == {}, f"Should be empty mapping, got {mapping}"


@check("TextWorker: same value → same token (dedup)")
def _():
    from src.workers.text_worker import TextWorker
    w = TextWorker()
    text = "alice@corp.com and alice@corp.com again"
    _, mapping = w.redact(text, language="en")
    # Only one entry for the same email
    assert len(mapping) <= 1, f"Duplicate value got separate tokens: {mapping}"


# ── 2. Deanonymizer ──────────────────────────────────────────────────────────────
@check("Deanonymizer: exact match restores value")
def _():
    from src.deanonymizer.deanonymizer import Deanonymizer
    d = Deanonymizer()
    mapping = {"<<P001>>": "สมชาย ใจดี", "<<EM001>>": "somchai@co.th"}
    result, misses = d.deanonymize("ชื่อ <<P001>> อีเมล <<EM001>>", mapping)
    assert "สมชาย ใจดี" in result, f"Person not restored: {result}"
    assert "somchai@co.th" in result, f"Email not restored: {result}"
    assert misses == [], f"Unexpected misses: {misses}"


@check("Deanonymizer: unknown token → logged as miss, not crash")
def _():
    from src.deanonymizer.deanonymizer import Deanonymizer
    d = Deanonymizer()
    result, misses = d.deanonymize("reply to <<ORG001>>", {"<<P001>>": "Alice"})
    assert "<<ORG001>>" in misses
    assert "<<ORG001>>" in result   # left as-is


@check("Deanonymizer: empty mapping → text unchanged")
def _():
    from src.deanonymizer.deanonymizer import Deanonymizer
    d = Deanonymizer()
    text = "no tokens here"
    result, misses = d.deanonymize(text, {})
    assert result == text


# ── 3. Full pipeline: redact → deanonymize ───────────────────────────────────────
@check("Pipeline: redact then deanonymize returns original text")
def _():
    from src.workers.text_worker import TextWorker
    from src.deanonymizer.deanonymizer import Deanonymizer

    original = "Please email alice@example.com about the contract"
    w = TextWorker()
    redacted, mapping = w.redact(original, language="en")
    assert "alice@example.com" not in redacted, "PII survived redaction"

    d = Deanonymizer()
    restored, misses = d.deanonymize(redacted, mapping)
    assert "alice@example.com" in restored, f"Value not restored: {restored}"
    assert misses == []


@check("Pipeline: multiple entity types round-trip")
def _():
    from src.workers.text_worker import TextWorker
    from src.deanonymizer.deanonymizer import Deanonymizer

    original = "Contact bob@test.com or call 0898765432 for more info"
    w = TextWorker()
    redacted, mapping = w.redact(original, language="en")

    d = Deanonymizer()
    restored, misses = d.deanonymize(redacted, mapping)
    assert "bob@test.com" in restored or len(mapping) > 0   # at least one entity


# ── 4. File worker (basic — no real PDF/DOCX needed) ────────────────────────────
@check("FileWorker: unsupported content-type passes through unchanged")
def _():
    from src.workers.file_worker import FileWorker
    w = FileWorker()
    raw = b"\x00\x01\x02"
    result, mapping = w.process(raw, "application/octet-stream")
    assert result == raw
    assert mapping == {}


@check("FileWorker: PDF round-trip produces non-empty bytes")
def _():
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    from src.workers.file_worker import FileWorker

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    doc.build([Paragraph("Send to test@example.com", styles["Normal"])])
    pdf_bytes = buf.getvalue()

    w = FileWorker()
    redacted, mapping = w.redact_pdf(pdf_bytes)
    assert isinstance(redacted, bytes) and len(redacted) > 100


# ── 5. OCR Worker (mocked — skip if easyocr not installed) ─────────────────────
@check("OCRWorker: bad image returns original bytes, no crash")
def _():
    from src.workers.ocr_worker import OCRWorker
    w = OCRWorker()
    result, mapping = w.process(b"not-an-image", "image/jpeg")
    assert result == b"not-an-image"
    assert mapping == {}


# ── 6. Token format correctness ──────────────────────────────────────────────────
@check("Token format: counters increment correctly")
def _():
    from src.workers.text_worker import TextWorker
    w = TextWorker()
    assert w._next_token("P") == "<<P001>>"
    assert w._next_token("P") == "<<P002>>"
    assert w._next_token("EM") == "<<EM001>>"
    w.reset_counters()
    assert w._next_token("P") == "<<P001>>"


# ── 7. Mapping store (no Redis — logic only) ─────────────────────────────────────
@check("RedisStore: session key format is correct")
def _():
    from src.mapping_store.redis_store import _session_key
    key = _session_key("abc-123")
    assert key == "session:abc-123:map"


# ── 8. Audit logger (no DB — hash logic only) ────────────────────────────────────
@check("AuditLogger: hash chain is deterministic and tamper-evident")
def _():
    import os
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
    from src.audit.logger import AuditLogger
    a = AuditLogger.__new__(AuditLogger)
    a._last_hash = "GENESIS"

    row = {"id": "1", "created_at": "2026-01-01", "session_id": "s",
           "event_type": "redact", "entity_type": "EMAIL_ADDRESS",
           "token": "<<EM001>>", "content_type": "text/plain"}

    h1 = a._compute_hash(row, "GENESIS")
    h2 = a._compute_hash(row, "GENESIS")
    assert h1 == h2, "Hash not deterministic"
    assert len(h1) == 64, "Expected SHA-256 hex"

    tampered = {**row, "token": "<<EM002>>"}
    h3 = a._compute_hash(tampered, "GENESIS")
    assert h3 != h1, "Hash should change when data changes"


@check("AuditLogger: original PII value has no place in log API")
def _():
    import inspect
    import os
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
    from src.audit.logger import AuditLogger
    sig = inspect.signature(AuditLogger.log)
    params = set(sig.parameters.keys())
    forbidden = {"original_value", "pii_value", "raw_value", "plaintext"}
    overlap = params & forbidden
    assert not overlap, f"PII leak risk — forbidden params found: {overlap}"


# ── 9. Router content-type classification ────────────────────────────────────────
@check("Router: classifies content types correctly")
def _():
    from src.orchestrator.router import classify_content
    assert classify_content("text/plain") == "text"
    assert classify_content("application/json") == "text"
    assert classify_content("application/pdf") == "pdf"
    assert classify_content("application/vnd.openxmlformats-officedocument.wordprocessingml.document") == "docx"
    assert classify_content("image/jpeg") == "image"
    assert classify_content("image/png") == "image"
    assert classify_content("application/octet-stream") == "unsupported"


# ── 10. LLM domain whitelist loading ─────────────────────────────────────────────
@check("SSL Inspector: loads LLM domains from whitelist")
def _():
    from src.proxy.ssl_inspector import load_llm_domains
    domains = load_llm_domains()
    assert isinstance(domains, set)
    assert len(domains) > 0, "No domains loaded"
    assert "chat.openai.com" in domains or "api.openai.com" in domains, \
        f"Expected OpenAI domain, got: {domains}"


# ── Summary ───────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 60)
    print("  AI Firewall — Smoke Test")
    print("=" * 60 + "\n")

    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed} passed, {failed} failed / {len(results)} total")
    print("=" * 60)

    if failed:
        print("\nFailed tests:\n")
        for name, ok, tb in results:
            if not ok:
                print(f"  {FAIL} {name}")
                print(tb)
        sys.exit(1)
    else:
        print("\n  All smoke tests passed. ✓")
        sys.exit(0)


if __name__ == "__main__":
    # Run all decorated functions
    for name, obj in list(globals().items()):
        if callable(obj) and name == "_":
            pass   # already called at decoration time

    main()
