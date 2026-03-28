"""Prometheus middleware plus OTLP metric bridge."""

import time
from typing import Callable

from prometheus_client import Counter, Histogram, REGISTRY
from prometheus_client.exposition import generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from shared.otel_metrics import try_get_metrics

# Define metrics
HTTP_REQUESTS_TOTAL = Counter(
    "http_request_total",
    "Total HTTP requests",
    ["service_name", "method", "http_route", "http_status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["service_name", "method", "http_route"],
)

# Service name (set by each service)
SERVICE_NAME = "microservice"


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect HTTP metrics."""

    @staticmethod
    def _route_label(request: Request) -> str:
        route = request.scope.get("route")
        route_path = getattr(route, "path", None)
        return route_path or request.url.path

    @staticmethod
    def _record_otel_metrics(
        method: str,
        route: str,
        status_code: int,
        duration: float,
        error_type: str | None = None,
    ) -> None:
        otel_metrics = try_get_metrics()
        if otel_metrics is None:
            return

        otel_metrics.record_request_count(method, route, status_code)
        otel_metrics.record_request_duration(method, route, duration)
        if status_code >= 500 or error_type is not None:
            otel_metrics.record_error(method, route, error_type or f"http_{status_code}")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Track request duration and count."""
        # Skip metrics endpoint itself
        if request.url.path == "/metrics":
            return await call_next(request)

        start_time = time.perf_counter()
        route = self._route_label(request)
        
        try:
            response = await call_next(request)
        except Exception as exc:
            duration = time.perf_counter() - start_time
            # Track error responses
            HTTP_REQUESTS_TOTAL.labels(
                service_name=SERVICE_NAME,
                method=request.method,
                http_route=route,
                http_status_code=500,
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                service_name=SERVICE_NAME,
                method=request.method,
                http_route=route,
            ).observe(duration)
            self._record_otel_metrics(
                method=request.method,
                route=route,
                status_code=500,
                duration=duration,
                error_type=type(exc).__name__,
            )
            raise

        duration = time.perf_counter() - start_time
        status_code = response.status_code

        # Record metrics
        HTTP_REQUESTS_TOTAL.labels(
            service_name=SERVICE_NAME,
            method=request.method,
            http_route=route,
            http_status_code=status_code,
        ).inc()

        HTTP_REQUEST_DURATION_SECONDS.labels(
            service_name=SERVICE_NAME,
            method=request.method,
            http_route=route,
        ).observe(duration)
        self._record_otel_metrics(
            method=request.method,
            route=route,
            status_code=status_code,
            duration=duration,
        )

        return response


def get_metrics_text() -> str:
    """Get metrics in Prometheus text format."""
    return generate_latest(REGISTRY).decode("utf-8")
