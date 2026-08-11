"""
OpenTelemetry tracing helpers.
"""

import os
from typing import List

from fastapi import FastAPI

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from .config import settings
from .logging_config import setup_logging

logger = setup_logging("tracing")


def _build_exporter() -> List[BatchSpanProcessor]:
    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT or os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
    )
    use_console = settings.OTEL_TRACING_CONSOLE or (
        os.getenv("OTEL_TRACING_CONSOLE", "false").lower() == "true"
    )

    span_processors: List[BatchSpanProcessor] = []
    if endpoint:
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        span_processors.append(BatchSpanProcessor(exporter))
    if use_console or not span_processors:
        span_processors.append(BatchSpanProcessor(ConsoleSpanExporter()))

    return span_processors


def setup_tracing(
    app: FastAPI,
    service_name: str,
    *,
    instrument_httpx: bool = False,
    instrument_requests: bool = False,
) -> None:
    """
    Configure OpenTelemetry tracer for a FastAPI application.
    """
    # Standard OTel env var (https://opentelemetry.io/docs/languages/sdk-configuration/general/):
    # use a no-op tracer instead of a real BatchSpanProcessor/OTLPSpanExporter
    # pair. Without this, every process that imports a service's main.py (each
    # test file, in particular) starts a background export thread that
    # retries against an unreachable collector forever; at interpreter exit,
    # each one's atexit shutdown hook blocks joining that thread, so a test
    # run with several services loaded can take a very long time to actually
    # return control even after all tests have passed.
    if os.getenv("OTEL_SDK_DISABLED", "false").lower() == "true":
        trace.set_tracer_provider(trace.NoOpTracerProvider())
        logger.info("Tracing disabled for %s (OTEL_SDK_DISABLED=true)", service_name)
        return

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": settings.APP_VERSION,
            "deployment.environment": settings.ENVIRONMENT,
        }
    )

    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT or os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
    )

    provider = TracerProvider(resource=resource)
    for processor in _build_exporter():
        provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)

    if instrument_httpx:
        HTTPXClientInstrumentor().instrument()
    if instrument_requests:
        RequestsInstrumentor().instrument()

    logger.info(
        "Tracing configured for %s (endpoint=%s)",
        service_name,
        endpoint or "console",
    )
