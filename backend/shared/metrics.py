"""
Prometheus metrics helper for FastAPI services.
"""
import time
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

from .logging_config import setup_logging

logger = setup_logging("metrics")

try:
    from prometheus_client import (
        Counter,
        Histogram,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )

    METRICS_ENABLED = True
    REQUEST_LATENCY = Histogram(
        "service_request_latency_seconds",
        "Request latency in seconds per endpoint",
        ["service", "method", "path"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
    )
    REQUEST_COUNT = Counter(
        "service_requests_total",
        "Total HTTP requests",
        ["service", "method", "status"],
    )
    REQUEST_ERRORS = Counter(
        "service_request_errors_total",
        "Total HTTP errors (status >= 500)",
        ["service", "method", "status"],
    )
except ImportError:  # pragma: no cover
    METRICS_ENABLED = False
    REQUEST_LATENCY = REQUEST_COUNT = REQUEST_ERRORS = None  # type: ignore


class MetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, service_name: str):
        super().__init__(app)
        self.service_name = service_name

    async def dispatch(self, request, call_next):
        if not METRICS_ENABLED or request.url.path == "/metrics":
            return await call_next(request)

        start = time.perf_counter()
        status_code: Optional[int] = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            status_code = 500
            REQUEST_ERRORS.labels(
                self.service_name, request.method, str(status_code)
            ).inc()
            REQUEST_COUNT.labels(
                self.service_name, request.method, str(status_code)
            ).inc()
            raise
        finally:
            duration = time.perf_counter() - start
            if status_code is not None:
                REQUEST_COUNT.labels(
                    self.service_name,
                    request.method,
                    str(status_code),
                ).inc()
                if status_code >= 500:
                    REQUEST_ERRORS.labels(
                        self.service_name,
                        request.method,
                        str(status_code),
                    ).inc()
            REQUEST_LATENCY.labels(
                self.service_name,
                request.method,
                request.url.path,
            ).observe(duration)


def setup_metrics(app: FastAPI, service_name: str):
    """
    Attach Prometheus middleware and /metrics endpoint to the app.
    """
    if not METRICS_ENABLED:
        logger.warning(
            "prometheus-client not installed; metrics disabled for %s", service_name
        )

        @app.get("/metrics")
        async def metrics_unavailable():
            raise HTTPException(
                status_code=503, detail="Prometheus client not available"
            )

        return

    if not getattr(app.state, "metrics_configured", False):
        app.state.metrics_configured = True

        @app.get("/metrics")
        async def metrics_endpoint():
            return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.add_middleware(MetricsMiddleware, service_name=service_name)
