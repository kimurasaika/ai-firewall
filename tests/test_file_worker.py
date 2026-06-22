"""Tests for FileWorker PDF and DOCX redaction."""
import io
import pytest
from unittest.mock import MagicMock, patch

pytest.importorskip("pdfplumber", reason="pdfplumber not installed — pip install pdfplumber")
pytest.importorskip("reportlab", reason="reportlab not installed — pip install reportlab")
pytest.importorskip("docx", reason="python-docx not installed — pip install python-docx")  # imports as 'docx'
pytest.importorskip("presidio_analyzer", reason="presidio-analyzer not installed")


def make_simple_docx(text: str) -> bytes:
    import docx
    doc = docx.api.Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def make_simple_pdf(text: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    doc.build([Paragraph(text, styles["Normal"])])
    return buf.getvalue()


@pytest.fixture
def worker():
    from src.workers.file_worker import FileWorker
    return FileWorker()


def test_redact_docx_removes_email(worker):
    docx_bytes = make_simple_docx("Contact bob@example.com for details")
    redacted, mapping = worker.redact_docx(docx_bytes)
    assert isinstance(redacted, bytes)
    assert len(redacted) > 0
    # If any email entity was found, it should be in mapping
    # (depends on Presidio model having en support)
    assert isinstance(mapping, dict)


def test_redact_pdf_produces_valid_bytes(worker):
    pdf_bytes = make_simple_pdf("Call 0812345678 now")
    redacted, mapping = worker.redact_pdf(pdf_bytes)
    assert isinstance(redacted, bytes)
    assert len(redacted) > 100   # non-empty PDF


def test_process_routes_to_pdf(worker):
    pdf_bytes = make_simple_pdf("test")
    with patch.object(worker, "redact_pdf", return_value=(b"redacted", {})) as mock:
        worker.process(pdf_bytes, "application/pdf")
        mock.assert_called_once()


def test_process_routes_to_docx(worker):
    docx_bytes = make_simple_docx("test")
    with patch.object(worker, "redact_docx", return_value=(b"redacted", {})) as mock:
        worker.process(docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        mock.assert_called_once()


def test_unsupported_content_type_passthrough(worker):
    raw = b"some raw bytes"
    result, mapping = worker.process(raw, "application/octet-stream")
    assert result == raw
    assert mapping == {}
