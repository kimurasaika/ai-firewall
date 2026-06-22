"""Content-type router — dispatches to the appropriate worker."""
from __future__ import annotations

import logging
import uuid
from typing import Literal

from src.workers.file_worker import FileWorker
from src.workers.ocr_worker import OCRWorker
from src.workers.text_worker import TextWorker

logger = logging.getLogger(__name__)

ContentCategory = Literal["text", "pdf", "docx", "image", "unsupported"]


def classify_content(content_type: str) -> ContentCategory:
    ct = content_type.lower()
    if "text/plain" in ct or "application/json" in ct:
        return "text"
    if "pdf" in ct:
        return "pdf"
    if "docx" in ct or "wordprocessingml" in ct or "msword" in ct:
        return "docx"
    if "image/" in ct:
        return "image"
    return "unsupported"


class Router:
    """Routes content to the correct worker and returns (redacted_content, mapping)."""

    def __init__(self) -> None:
        self._text_worker = TextWorker()
        self._file_worker = FileWorker()
        self._ocr_worker = OCRWorker()

    async def dispatch(
        self,
        content: bytes,
        content_type: str,
        session_id: str | None = None,
    ) -> tuple[bytes, dict[str, str], str]:
        """
        Returns (redacted_bytes, mapping, session_id).
        session_id is generated if not provided.
        """
        sid = session_id or str(uuid.uuid4())
        category = classify_content(content_type)
        logger.info("Router.dispatch: session=%s category=%s ct=%s", sid, category, content_type)

        mapping: dict[str, str] = {}
        redacted: bytes = content

        if category == "text":
            text = content.decode("utf-8", errors="replace")
            redacted_text, mapping = self._text_worker.redact_safe(text)
            redacted = redacted_text.encode("utf-8")

        elif category in ("pdf", "docx"):
            redacted, mapping = self._file_worker.process(content, content_type)

        elif category == "image":
            redacted, mapping = self._ocr_worker.process(content, content_type)

        else:
            logger.warning("Router: unsupported content_type=%s session=%s — passing through", content_type, sid)

        return redacted, mapping, sid
