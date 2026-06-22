"""Structured JSON logging with Loki push support."""
from __future__ import annotations

import gzip
import json
import logging
import os
import time
import threading
from collections import deque
from typing import Any

import requests

_LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")
_ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
_BATCH_SIZE = int(os.environ.get("LOKI_BATCH_SIZE", "100"))
_BATCH_TIMEOUT = float(os.environ.get("LOKI_BATCH_TIMEOUT_SECONDS", "5"))


class LokiHandler(logging.Handler):
    """Logging handler that batches and pushes structured logs to Loki."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service
        self._queue: deque[dict[str, Any]] = deque()
        self._lock = threading.Lock()
        self._push_url = f"{_LOKI_URL}/loki/api/v1/push"
        self._base_labels = {
            "app": "ai-firewall",
            "service": service,
            "env": _ENVIRONMENT,
        }
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    def emit(self, record: logging.LogRecord) -> None:
        entry = {
            "ts": int(time.time_ns()),
            "line": self.format(record),
            "level": record.levelname,
            "logger": record.name,
        }
        with self._lock:
            self._queue.append(entry)
            if len(self._queue) >= _BATCH_SIZE:
                self._push()

    def _flush_loop(self) -> None:
        while True:
            time.sleep(_BATCH_TIMEOUT)
            with self._lock:
                if self._queue:
                    self._push()

    def _push(self) -> None:
        """Push queued entries to Loki. Must be called under self._lock."""
        if not self._queue:
            return

        entries = list(self._queue)
        self._queue.clear()

        label_str = "{" + ",".join(f'{k}="{v}"' for k, v in self._base_labels.items()) + "}"
        streams = [
            {
                "stream": self._base_labels,
                "values": [[str(e["ts"]), e["line"]] for e in entries],
            }
        ]
        payload = json.dumps({"streams": streams}).encode()
        compressed = gzip.compress(payload)

        try:
            requests.post(
                self._push_url,
                data=compressed,
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                    "X-Scope-OrgID": "dlp",
                },
                timeout=5,
            )
        except Exception:
            pass   # Loki push failure must never crash the application


class JsonFormatter(logging.Formatter):
    """Structured JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_record: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%f"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": getattr(record, "service", "unknown"),
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        for key in ("session_id", "trace_id", "span_id", "token"):
            val = getattr(record, key, None)
            if val is not None:
                log_record[key] = val
        return json.dumps(log_record, ensure_ascii=False)


def configure_logging(service: str, level: str = "INFO") -> None:
    """Set up root logger with JSON formatter + Loki handler."""
    json_fmt = JsonFormatter()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(json_fmt)

    loki_handler = LokiHandler(service=service)
    loki_handler.setFormatter(json_fmt)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    root.addHandler(stream_handler)
    root.addHandler(loki_handler)
