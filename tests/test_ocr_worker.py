"""Tests for OCRWorker image redaction."""
import io
import pytest
from unittest.mock import MagicMock, patch

pytest.importorskip("PIL", reason="Pillow not installed — pip install Pillow")
pytest.importorskip("easyocr", reason="easyocr not installed — pip install easyocr")
pytest.importorskip("presidio_analyzer", reason="presidio-analyzer not installed")

from PIL import Image


def make_test_image() -> bytes:
    img = Image.new("RGB", (200, 100), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def worker():
    from src.workers.ocr_worker import OCRWorker
    return OCRWorker()


def test_process_returns_bytes(worker):
    img_bytes = make_test_image()
    # Mock EasyOCR to avoid loading model in tests
    with patch("src.workers.ocr_worker._get_reader") as mock_reader:
        mock_reader.return_value.readtext.return_value = []
        result, mapping = worker.process(img_bytes, "image/jpeg")
    assert isinstance(result, bytes)
    assert len(result) > 0
    assert isinstance(mapping, dict)


def test_redacts_pii_bounding_box(worker):
    img_bytes = make_test_image()
    fake_bbox = [[10, 10], [100, 10], [100, 30], [10, 30]]
    with patch("src.workers.ocr_worker._get_reader") as mock_reader, \
         patch.object(worker._text_worker, "redact_safe") as mock_redact:
        mock_reader.return_value.readtext.return_value = [
            (fake_bbox, "somchai@company.com", 0.95)
        ]
        mock_redact.return_value = ("<<EM001>>", {"<<EM001>>": "somchai@company.com"})
        result, mapping = worker.process(img_bytes, "image/jpeg")
    assert "<<EM001>>" in mapping.values() or "somchai@company.com" in mapping.values()


def test_passthrough_on_low_confidence(worker):
    img_bytes = make_test_image()
    with patch("src.workers.ocr_worker._get_reader") as mock_reader:
        mock_reader.return_value.readtext.return_value = [
            ([[0, 0], [10, 0], [10, 10], [0, 10]], "blurry text", 0.1)
        ]
        result, mapping = worker.process(img_bytes, "image/jpeg")
    assert mapping == {}


def test_returns_original_on_error(worker):
    img_bytes = b"not an image"
    result, mapping = worker.process(img_bytes, "image/jpeg")
    assert result == img_bytes
    assert mapping == {}
