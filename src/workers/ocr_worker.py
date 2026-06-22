"""OCR worker — extracts text from images, redacts PII, blacks out bounding boxes."""
from __future__ import annotations

import io
import logging
import time
from typing import Any

import easyocr
from PIL import Image, ImageDraw

from opentelemetry import trace

from src.observability.metrics import request_latency, worker_errors_total
from src.observability.tracer import get_tracer
from src.workers.text_worker import TextWorker

logger = logging.getLogger(__name__)
tracer = get_tracer("ocr_worker")

_READER: easyocr.Reader | None = None


def _get_reader() -> easyocr.Reader:
    global _READER
    if _READER is None:
        # Load both Thai and English; GPU disabled for predictable resource use
        _READER = easyocr.Reader(["th", "en"], gpu=False)
        logger.info("EasyOCR reader initialized")
    return _READER


class OCRWorker:
    """Detects text in images via EasyOCR, redacts PII, blacks out bounding boxes."""

    def __init__(self) -> None:
        self._text_worker = TextWorker()
        logger.info("OCRWorker initialized")

    def process(self, image_bytes: bytes, content_type: str = "image/jpeg") -> tuple[bytes, dict[str, str]]:
        """
        Extract text, redact PII, draw black rectangles over detected text regions.
        Returns (redacted_image_bytes, mapping).
        """
        with tracer.start_as_current_span("ocr_worker.process") as span:
            t0 = time.perf_counter()
            try:
                image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                reader = _get_reader()

                results = reader.readtext(image_bytes)
                span.set_attribute("ocr.regions_found", len(results))

                draw = ImageDraw.Draw(image)
                combined_mapping: dict[str, str] = {}

                for bbox, text, confidence in results:
                    if not text.strip() or confidence < 0.3:
                        continue

                    redacted_text, mapping = self._text_worker.redact_safe(text)
                    combined_mapping.update(mapping)

                    if redacted_text != text:
                        # Black out the bounding box of any region containing PII
                        xs = [p[0] for p in bbox]
                        ys = [p[1] for p in bbox]
                        draw.rectangle(
                            [min(xs), min(ys), max(xs), max(ys)],
                            fill="black",
                        )

                # Re-encode in original format
                fmt = self._mime_to_pil_format(content_type)
                out_buf = io.BytesIO()
                image.save(out_buf, format=fmt)

                request_latency.labels(service="ocr_worker", content_type="image").observe(
                    time.perf_counter() - t0
                )
                return out_buf.getvalue(), combined_mapping

            except Exception as exc:
                worker_errors_total.labels(worker="ocr", error_type=type(exc).__name__).inc()
                logger.error("OCRWorker.process failed: %s", exc, exc_info=True)
                return image_bytes, {}

    @staticmethod
    def _mime_to_pil_format(content_type: str) -> str:
        mapping = {
            "image/jpeg": "JPEG",
            "image/jpg": "JPEG",
            "image/png": "PNG",
            "image/gif": "GIF",
            "image/webp": "WEBP",
            "image/bmp": "BMP",
        }
        return mapping.get(content_type.lower(), "JPEG")
