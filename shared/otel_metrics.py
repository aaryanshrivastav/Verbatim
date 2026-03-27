"""OpenTelemetry Metrics definitions for microservices."""

from opentelemetry import metrics
from typing import Optional


class ServiceMetrics:
    """Metrics for a microservice using OpenTelemetry."""
    
    def __init__(self, meter: metrics.Meter, service_name: str):
        self.service_name = service_name
        self.meter = meter
        
        # HTTP Request Metrics
        self.request_count = meter.create_counter(
            name="http_request_total",
            description="Total HTTP requests",
            unit="1",
        )
        
        self.request_duration = meter.create_histogram(
            name="http_request_duration_seconds",
            description="HTTP request duration",
            unit="s",
        )
        
        self.error_count = meter.create_counter(
            name="http_error_total",
            description="Total HTTP errors",
            unit="1",
        )
        
        # External service call metrics
        self.external_call_duration = meter.create_histogram(
            name="external_call_duration_seconds",
            description="Duration of external service calls",
            unit="s",
        )
        
        self.external_call_errors = meter.create_counter(
            name="external_call_errors_total",
            description="Total external service call errors",
            unit="1",
        )
        
        # Database metrics
        self.db_query_duration = meter.create_histogram(
            name="db_query_duration_seconds",
            description="Duration of database queries",
            unit="s",
        )
        
        self.db_query_errors = meter.create_counter(
            name="db_query_errors_total",
            description="Total database query errors",
            unit="1",
        )
        
        # Cache metrics
        self.cache_hits = meter.create_counter(
            name="cache_hits_total",
            description="Total cache hits",
            unit="1",
        )
        
        self.cache_misses = meter.create_counter(
            name="cache_misses_total",
            description="Total cache misses",
            unit="1",
        )
        
        # Authentication metrics
        self.auth_failures = meter.create_counter(
            name="auth_failures_total",
            description="Total authentication failures",
            unit="1",
        )
        
        # Payment metrics
        self.payment_failures = meter.create_counter(
            name="payment_failures_total",
            description="Total payment failures",
            unit="1",
        )
    
    def record_request_count(self, method: str, endpoint: str, status_code: int):
        """Record an HTTP request."""
        self.request_count.add(
            1,
            attributes={
                "service": self.service_name,
                "method": method,
                "endpoint": endpoint,
                "status_code": str(status_code),
            },
        )
    
    def record_request_duration(self, method: str, endpoint: str, duration_seconds: float):
        """Record HTTP request duration."""
        self.request_duration.record(
            duration_seconds,
            attributes={
                "service": self.service_name,
                "method": method,
                "endpoint": endpoint,
            },
        )
    
    def record_error(self, method: str, endpoint: str, error_type: str):
        """Record an HTTP error."""
        self.error_count.add(
            1,
            attributes={
                "service": self.service_name,
                "method": method,
                "endpoint": endpoint,
                "error_type": error_type,
            },
        )
    
    def record_external_call_duration(self, service: str, duration_seconds: float):
        """Record external service call duration."""
        self.external_call_duration.record(
            duration_seconds,
            attributes={
                "source_service": self.service_name,
                "target_service": service,
            },
        )
    
    def record_external_call_error(self, service: str, error_type: str):
        """Record external service call error."""
        self.external_call_errors.add(
            1,
            attributes={
                "source_service": self.service_name,
                "target_service": service,
                "error_type": error_type,
            },
        )
    
    def record_db_query_duration(self, query_type: str, duration_seconds: float):
        """Record database query duration."""
        self.db_query_duration.record(
            duration_seconds,
            attributes={
                "service": self.service_name,
                "query_type": query_type,
            },
        )
    
    def record_db_query_error(self, query_type: str, error_type: str):
        """Record database query error."""
        self.db_query_errors.add(
            1,
            attributes={
                "service": self.service_name,
                "query_type": query_type,
                "error_type": error_type,
            },
        )
    
    def record_cache_hit(self):
        """Record a cache hit."""
        self.cache_hits.add(1, attributes={"service": self.service_name})
    
    def record_cache_miss(self):
        """Record a cache miss."""
        self.cache_misses.add(1, attributes={"service": self.service_name})
    
    def record_auth_failure(self, reason: str):
        """Record an authentication failure."""
        self.auth_failures.add(
            1,
            attributes={
                "service": self.service_name,
                "reason": reason,
            },
        )
    
    def record_payment_failure(self, reason: str):
        """Record a payment failure."""
        self.payment_failures.add(
            1,
            attributes={
                "service": self.service_name,
                "reason": reason,
            },
        )


# Global metrics instance (set by each service)
_metrics: Optional[ServiceMetrics] = None


def get_metrics() -> ServiceMetrics:
    """Get the global metrics instance."""
    if _metrics is None:
        raise RuntimeError("Metrics not initialized. Call init_metrics first.")
    return _metrics


def init_metrics(meter: metrics.Meter, service_name: str) -> ServiceMetrics:
    """Initialize global metrics instance."""
    global _metrics
    _metrics = ServiceMetrics(meter, service_name)
    return _metrics
