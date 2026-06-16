from __future__ import annotations

import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from config.settings import AppSettings

logger = logging.getLogger(__name__)
_instrumented = False


def setup_otel(app: object, settings: AppSettings) -> None:
    global _instrumented
    if _instrumented or not settings.telemetry.enabled:
        return
    try:
        resource = Resource.create({"service.name": settings.telemetry.service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=settings.telemetry.otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)  # type: ignore[arg-type]
        _instrumented = True
        logger.info("otel tracing enabled -> %s", settings.telemetry.otlp_endpoint)
    except Exception:
        logger.warning("otel setup failed; continuing without distributed tracing", exc_info=True)


def get_tracer(name: str = "insightiq") -> trace.Tracer:
    return trace.get_tracer(name)
