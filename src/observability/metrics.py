"""Prometheus-compatible metrics exposed for scraping by VictoriaMetrics."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, start_http_server

# ── Request metrics ─────────────────────────────────────────────────────────────
requests_total = Counter(
    "dlp_requests_total",
    "Total requests processed by DLP",
    ["service", "status"],
)

request_latency = Histogram(
    "dlp_request_latency_seconds",
    "End-to-end DLP processing latency in seconds",
    ["service", "content_type"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0, 2.5, 5.0),
)

# ── PII / Redaction metrics ─────────────────────────────────────────────────────
redactions_total = Counter(
    "dlp_redactions_total",
    "Total PII entities redacted",
    ["entity_type"],
)

deanon_misses_total = Counter(
    "dlp_deanon_misses_total",
    "De-anonymization failures (token not found in mapping store)",
    ["match_type"],   # exact | fuzzy | miss
)

# ── Worker metrics ──────────────────────────────────────────────────────────────
worker_queue_length = Gauge(
    "dlp_worker_queue_length",
    "Current queue depth per worker type",
    ["worker"],
)

worker_errors_total = Counter(
    "dlp_worker_errors_total",
    "Worker processing errors",
    ["worker", "error_type"],
)

# ── Redis metrics ───────────────────────────────────────────────────────────────
redis_sessions_active = Gauge(
    "dlp_redis_sessions_active",
    "Active session mappings stored in Redis",
)

redis_errors_total = Counter(
    "dlp_redis_errors_total",
    "Redis operation errors",
    ["operation"],
)

# ── Fail-safe metrics ───────────────────────────────────────────────────────────
fail_safe_active = Gauge(
    "dlp_fail_safe_active",
    "1 when fail-safe mode is active (LLM domains blocked)",
)


def start_metrics_server(port: int = 9090) -> None:
    """Start Prometheus /metrics endpoint for VictoriaMetrics scraping."""
    try:
        start_http_server(port)
    except OSError:
        pass  # Port already bound by another worker in multi-process mode
