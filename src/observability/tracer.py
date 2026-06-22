"""OpenTelemetry tracer setup — sends to Jaeger via OTLP."""
from __future__ import annotations

import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

_initialized = False


def setup_tracer(service_name: str) -> trace.Tracer:
    """Initialize OTel tracer for a service. Safe to call multiple times."""
    global _initialized
    if _initialized:
        return trace.get_tracer(service_name)

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317")
    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    _initialized = True
    logger.info("OTel tracer initialized: service=%s endpoint=%s", service_name, endpoint)
    return trace.get_tracer(service_name)


def get_tracer(service_name: str) -> trace.Tracer:
    return trace.get_tracer(service_name)
