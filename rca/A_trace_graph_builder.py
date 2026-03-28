"""Module A: Trace Graph Builder.

Queries Jaeger, extracts span metrics, builds trace graph,
computes suspicious span ratios per service.
"""

import logging
from typing import Dict, List, Tuple
from datetime import datetime

from rca.models import Incident, TraceMetrics
from rca.clients.jaeger_client import JaegerClient, JaegerTrace
from rca.ring_buffer import RingBuffer
from rca.config import RCAConfig

logger = logging.getLogger(__name__)


class TraceGraphBuilder:
    """Builds trace graph and computes metrics per service."""
    
    def __init__(self, config: RCAConfig):
        """Initialize builder.
        
        Args:
            config: RCAConfig instance
        """
        self.config = config
        self.jaeger = JaegerClient(
            config.jaeger_base_url,
            allow_synthetic_fallback=config.allow_synthetic_trace_fallback,
        )
        
        # Ring buffers for baseline durations: (service, endpoint) -> RingBuffer
        self.baseline_buffers: Dict[Tuple[str, str], RingBuffer] = {}
    
    def build_graph(self, incident: Incident) -> Dict[str, TraceMetrics]:
        """Build trace graph and compute metrics.
        
        Args:
            incident: Incident object
            
        Returns:
            Dict mapping service -> TraceMetrics
        """
        # Query traces from Jaeger
        traces = self.jaeger.query_traces_by_endpoint(
            incident.endpoint,
            incident.time_window_start,
            incident.time_window_end,
            limit=self.config.trace_query_limit
        )
        
        if not traces:
            logger.warning(f"No traces found for endpoint {incident.endpoint}")
            return {}
        
        # Initialize metrics dict
        service_metrics: Dict[str, Dict] = {}
        
        # Process each trace
        for trace in traces:
            self._process_trace(trace, incident, service_metrics)
        
        # Convert to TraceMetrics objects
        return self._finalize_metrics(service_metrics, len(traces))
    
    def _process_trace(
        self,
        trace: JaegerTrace,
        incident: Incident,
        service_metrics: Dict[str, Dict]
    ):
        """Process a single trace and update metrics.
        
        Args:
            trace: JaegerTrace object
            incident: Parent incident
            service_metrics: Dict to update
        """
        seen_in_trace = set()
        for service in trace.get_service_names():
            if service not in service_metrics:
                service_metrics[service] = {
                    "span_count": 0,
                    "suspicious_count": 0,
                    "durations": [],
                    "trace_hits": 0,
                }
            
            # Get span metrics for this service
            span_count, error_count, durations = self.jaeger.get_service_span_metrics(
                trace, service
            )
            service_metrics[service]["span_count"] += span_count
            if span_count > 0 and service not in seen_in_trace:
                service_metrics[service]["trace_hits"] += 1
                seen_in_trace.add(service)
            
            # Update baseline with these durations
            self._update_baseline(service, incident.endpoint, durations)
            
            # Count suspicious spans
            baseline_mean = self._get_baseline_mean(service, incident.endpoint)
            suspicious = sum(
                1 for d in durations
                if d > baseline_mean * self.config.span_suspicious_multiplier or
                   d < 0  # Error indicator
            )
            service_metrics[service]["suspicious_count"] += error_count + suspicious
            service_metrics[service]["durations"].extend(durations)
    
    def _update_baseline(self, service: str, endpoint: str, durations: List[float]):
        """Update rolling baseline for service/endpoint.
        
        Args:
            service: Service name
            endpoint: HTTP endpoint
            durations: List of span durations in ms
        """
        key = (service, endpoint)
        
        if key not in self.baseline_buffers:
            self.baseline_buffers[key] = RingBuffer(
                max_size=int(self.config.baseline_window_seconds * 10)  # ~1 per 100ms
            )
        
        for duration in durations:
            self.baseline_buffers[key].push(duration)
    
    def _get_baseline_mean(self, service: str, endpoint: str) -> float:
        """Get baseline mean duration for service/endpoint.
        
        Args:
            service: Service name
            endpoint: HTTP endpoint
            
        Returns:
            Baseline mean duration in ms
        """
        key = (service, endpoint)
        if key in self.baseline_buffers:
            return self.baseline_buffers[key].mean()
        
        # Default: assume 50ms baseline
        return 50.0
    
    def _finalize_metrics(
        self,
        service_metrics: Dict[str, Dict],
        total_traces: int
    ) -> Dict[str, TraceMetrics]:
        """Convert raw metrics to TraceMetrics objects.
        
        Args:
            service_metrics: Raw metrics dict
            total_traces: Total number of traces processed
            
        Returns:
            Dict mapping service -> TraceMetrics
        """
        result = {}
        
        for service, metrics in service_metrics.items():
            span_count = metrics["span_count"]
            suspicious_count = metrics["suspicious_count"]
            
            # Compute ratios
            trace_coverage = (
                metrics.get("trace_hits", 0) / total_traces if total_traces > 0 else 0.0
            )
            suspicious_ratio = (
                suspicious_count / span_count if span_count > 0 else 0.0
            )
            
            result[service] = TraceMetrics(
                service=service,
                span_count=span_count,
                suspicious_count=suspicious_count,
                trace_coverage=trace_coverage,
                suspicious_span_ratio=suspicious_ratio
            )
        
        return result
