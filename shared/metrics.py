"""Prometheus metrics setup and collection."""

import time
from prometheus_client import Counter, Histogram, REGISTRY
from prometheus_client.exposition import generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable

# Define metrics
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["service", "method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["service", "method", "endpoint"],
)

# Service name (set by each service)
SERVICE_NAME = "microservice"


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect HTTP metrics."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Track request duration and count."""
        # Skip metrics endpoint itself
        if request.url.path == "/metrics":
            return await call_next(request)

        start_time = time.time()
        
        try:
            response = await call_next(request)
        except Exception as exc:
            # Track error responses
            HTTP_REQUESTS_TOTAL.labels(
                service=SERVICE_NAME,
                method=request.method,
                endpoint=request.url.path,
                status_code=500,
            ).inc()
            raise

        duration = time.time() - start_time

        # Record metrics
        HTTP_REQUESTS_TOTAL.labels(
            service=SERVICE_NAME,
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code,
        ).inc()

        HTTP_REQUEST_DURATION_SECONDS.labels(
            service=SERVICE_NAME,
            method=request.method,
            endpoint=request.url.path,
        ).observe(duration)

        return response


def get_metrics_text() -> str:
    """Get metrics in Prometheus text format."""
    return generate_latest(REGISTRY).decode("utf-8")
