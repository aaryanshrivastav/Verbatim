"""Mock Jaeger client for testing with synthetic data.

This replaces the need for a real Jaeger instance during pipeline testing.
"""

import logging
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class JaegerSpan:
    """Single span in a trace."""
    trace_id: str
    span_id: str
    service: str
    operation: str
    start_time: int  # microseconds
    duration: int    # microseconds
    tags: Dict[str, str]


@dataclass
class JaegerTrace:
    """Jaeger trace object."""
    trace_id: str
    spans: List[JaegerSpan]
    
    def get_service_names(self) -> List[str]:
        """Get unique service names in this trace."""
        return list(set(span.service for span in self.spans))
    
    def get_spans_for_service(self, service: str) -> List[JaegerSpan]:
        """Get spans from a specific service."""
        return [span for span in self.spans if span.service == service]


class JaegerClient:
    """Mock Jaeger client for synthetic testing.
    
    Returns synthetic traces for testing without a real Jaeger instance.
    """
    
    SERVICES = [
        "frontend", "gateway", "auth-service", "catalog-service",
        "order-service", "payment-service", "redis", "db"
    ]
    
    def __init__(self, base_url: str = "http://localhost:16686"):
        """Initialize client.
        
        Args:
            base_url: Jaeger base URL (unused for mock, but keeps interface)
        """
        self.base_url = base_url
        logger.info("Mock Jaeger client initialized (synthetic data mode)")
    
    def query_traces_by_endpoint(
        self,
        endpoint: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 100,
    ) -> List[JaegerTrace]:
        """Get traces for an endpoint in time window.
        
        Args:
            endpoint: API endpoint (e.g., "/checkout")
            start_time: Window start
            end_time: Window end
            limit: Max traces to return
            
        Returns:
            List of synthetic traces
        """
        traces = []
        
        # Generate synthetic traces
        num_traces = min(limit, random.randint(20, 50))
        
        for i in range(num_traces):
            trace_id = f"mock-trace-{i:04d}"
            spans = self._generate_trace_spans(endpoint, trace_id, start_time, end_time)
            trace = JaegerTrace(trace_id=trace_id, spans=spans)
            traces.append(trace)
        
        logger.debug(f"Generated {len(traces)} synthetic traces for {endpoint}")
        return traces
    
    def _generate_trace_spans(
        self,
        endpoint: str,
        trace_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[JaegerSpan]:
        """Generate synthetic spans for a trace.
        
        Args:
            endpoint: API endpoint
            trace_id: Trace ID
            start_time: Window start
            end_time: Window end
            
        Returns:
            List of spans
        """
        spans = []
        
        # Start with frontend
        base_micros = int(start_time.timestamp() * 1e6)
        span_id = 1
        
        # Frontend span (gateway)
        gateway_duration = random.randint(10000, 100000)  # 10-100ms
        spans.append(JaegerSpan(
            trace_id=trace_id,
            span_id=f"{span_id}",
            service="gateway",
            operation="request",
            start_time=base_micros,
            duration=gateway_duration,
            tags={"endpoint": endpoint, "http.status_code": "200"}
        ))
        span_id += 1
        
        # Backend services (randomly selected)
        current_time = base_micros + random.randint(1000, 5000)
        num_services = random.randint(2, 4)
        selected_services = random.sample(self.SERVICES[2:], num_services)
        
        for service in selected_services:
            duration = random.randint(5000, 50000)  # 5-50ms
            
            spans.append(JaegerSpan(
                trace_id=trace_id,
                span_id=f"{span_id}",
                service=service,
                operation="query" if service in ["db", "redis"] else "call",
                start_time=current_time,
                duration=duration,
                tags={"status": "ok", "db.type": "sql" if service == "db" else ""}
            ))
            span_id += 1
            current_time += duration + random.randint(1000, 5000)
        
        return spans
    
    def query_traces_by_service(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 100,
    ) -> List[JaegerTrace]:
        """Get traces from a specific service.
        
        Args:
            service: Service name
            start_time: Window start
            end_time: Window end
            limit: Max traces
            
        Returns:
            List of synthetic traces
        """
        # Simplified: just return random traces
        endpoint = f"/{service}/mock"
        return self.query_traces_by_endpoint(endpoint, start_time, end_time, limit)
    
    def get_service_span_metrics(
        self,
        trace: JaegerTrace,
        service: str,
    ) -> tuple:
        """Get span metrics for a service in a trace.
        
        Args:
            trace: JaegerTrace object
            service: Service name
            
        Returns:
            Tuple of (span_count, error_count, durations_ms)
        """
        spans = trace.get_spans_for_service(service)
        
        if not spans:
            return (0, 0, [])
        
        span_count = len(spans)
        error_count = random.randint(0, max(1, span_count // 5))  # 0-20% error rate
        durations = [span.duration / 1000.0 for span in spans]  # Convert to ms
        
        return (span_count, error_count, durations)
