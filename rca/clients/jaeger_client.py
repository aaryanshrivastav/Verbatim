"""Jaeger HTTP client for querying traces."""

import logging
import requests
from typing import List, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class JaegerTrace:
    """Representation of a Jaeger trace."""
    
    def __init__(self, trace_id: str, spans: List[Dict]):
        """Initialize trace.
        
        Args:
            trace_id: Unique trace identifier
            spans: List of span dictionaries from Jaeger
        """
        self.trace_id = trace_id
        self.spans = spans
    
    def get_service_names(self) -> List[str]:
        """Get unique services in trace."""
        services = set()
        for span in self.spans:
            if "process" in span and "serviceName" in span["process"]:
                services.add(span["process"]["serviceName"])
        return list(services)
    
    def count_error_spans(self) -> int:
        """Count spans with error tags/logs."""
        error_count = 0
        for span in self.spans:
            if self._span_has_error(span):
                error_count += 1
        return error_count
    
    def total_duration(self) -> float:
        """Get total trace duration in milliseconds."""
        if not self.spans:
            return 0.0
        # Duration is in microseconds in Jaeger
        max_end = max((s.get("startTime", 0) + s.get("duration", 0) 
                      for s in self.spans), default=0)
        return max_end / 1000.0  # Convert to ms
    
    @staticmethod
    def _span_has_error(span: Dict) -> bool:
        """Check if span has error indicators."""
        # Check tags
        tags = span.get("tags", [])
        for tag in tags:
            if tag.get("key") == "error" and tag.get("value"):
                return True
        
        # Check logs for error keywords
        logs = span.get("logs", [])
        for log in logs:
            fields = log.get("fields", [])
            for field in fields:
                if field.get("key") in ["message", "event"]:
                    value = field.get("value", "").lower()
                    if "error" in value or "exception" in value:
                        return True
        
        return False


class JaegerClient:
    """HTTP client for Jaeger API."""
    
    def __init__(self, base_url: str = "http://localhost:16686"):
        """Initialize Jaeger client.
        
        Args:
            base_url: Jaeger query service URL
        """
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
    
    def query_traces_by_endpoint(
        self,
        endpoint: str,
        time_window_start: datetime,
        time_window_end: datetime,
        limit: int = 20
    ) -> List[JaegerTrace]:
        """Query traces by endpoint and time window.
        
        Args:
            endpoint: HTTP endpoint (e.g., "/checkout")
            time_window_start: Start of window
            time_window_end: End of window
            limit: Max traces to return
            
        Returns:
            List of JaegerTrace objects
        """
        # Convert to microseconds (Jaeger uses microseconds)
        start_us = int(time_window_start.timestamp() * 1e6)
        end_us = int(time_window_end.timestamp() * 1e6)
        
        # Jaeger query API: /api/traces?service=X&tags=...&limit=N
        # For simplicity, query by tag http.url contains endpoint
        url = f"{self.base_url}/api/traces"
        
        params = {
            "tags": f'http.url="{endpoint}"',
            "start": start_us,
            "end": end_us,
            "limit": limit,
            "lookback": "custom"
        }
        
        try:
            # MOCK: In production, this queries real Jaeger
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            traces = []
            for trace_data in data.get("data", []):
                trace_id = trace_data.get("traceID")
                spans = trace_data.get("spans", [])
                traces.append(JaegerTrace(trace_id, spans))
            
            # Sort by: has_error DESC, duration DESC
            traces.sort(
                key=lambda t: (-t.count_error_spans(), -t.total_duration()),
                reverse=False  # Descending
            )
            
            return traces[:limit]
        except Exception as e:
            logger.error(f"Failed to query Jaeger: {e}")
            # MOCK: Return empty list on error
            return []
    
    def get_trace(self, trace_id: str) -> Optional[JaegerTrace]:
        """Get single trace by ID.
        
        Args:
            trace_id: Trace identifier
            
        Returns:
            JaegerTrace or None if not found
        """
        url = f"{self.base_url}/api/traces/{trace_id}"
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            trace_data = data.get("data", {})
            trace_id = trace_data.get("traceID")
            spans = trace_data.get("spans", [])
            
            return JaegerTrace(trace_id, spans) if spans else None
        except Exception as e:
            logger.error(f"Failed to get trace {trace_id}: {e}")
            return None
    
    def get_service_span_metrics(
        self,
        trace: JaegerTrace,
        service: str
    ) -> tuple[int, int, List[float]]:
        """Get span metrics for a service in a trace.
        
        Args:
            trace: JaegerTrace object
            service: Service name
            
        Returns:
            Tuple of (span_count, error_count, durations_ms)
        """
        span_count = 0
        error_count = 0
        durations = []
        
        for span in trace.spans:
            span_service = span.get("process", {}).get("serviceName", "")
            if span_service != service:
                continue
            
            span_count += 1
            if JaegerTrace._span_has_error(span):
                error_count += 1
            
            # Duration in microseconds, convert to ms
            duration_ms = span.get("duration", 0) / 1000.0
            durations.append(duration_ms)
        
        return span_count, error_count, durations
    
    def get_span_hierarchy(self, trace: JaegerTrace) -> Dict[str, Dict]:
        """Build service call hierarchy from trace spans.
        
        Simple: compute which service calls which.
        
        Returns:
            Dict mapping service -> set of called services
        """
        hierarchy = {}
        
        # Group spans by service
        spans_by_service = {}
        for span in trace.spans:
            svc = span.get("process", {}).get("serviceName", "unknown")
            if svc not in spans_by_service:
                spans_by_service[svc] = []
            spans_by_service[svc].append(span)
        
        # For each service, find upstream/downstream based on span tree
        # Jaeger: parentSpanID indicates parent span
        for service in spans_by_service:
            hierarchy[service] = set()
        
        for service, spans in spans_by_service.items():
            for span in spans:
                # If this span references another service, add dependency
                # This is a simplified approach; real implementation would walk the DAG
                parent_span_id = span.get("parentSpanID")
                if parent_span_id:
                    # Find parent span to determine parent service
                    for other_service, other_spans in spans_by_service.items():
                        if other_service != service:
                            for other_span in other_spans:
                                if other_span.get("spanID") == parent_span_id:
                                    if service not in hierarchy.get(other_service, set()):
                                        if other_service not in hierarchy:
                                            hierarchy[other_service] = set()
                                        hierarchy[other_service].add(service)
        
        return hierarchy
