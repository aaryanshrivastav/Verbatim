"""Derive higher-level metrics from raw Prometheus metrics."""

from typing import Dict, List, Optional
from datetime import datetime

from .models import DerivedMetrics
from .prometheus_client import PrometheusClient


class DerivedMetricsAggregator:
    """Aggregates raw metrics into derived metrics (p95, error_rate, request_rate)."""
    
    def __init__(self, prometheus_client: PrometheusClient):
        """Initialize aggregator.
        
        Args:
            prometheus_client: Prometheus HTTP client.
        """
        self.client = prometheus_client
    
    def compute_for_service_endpoint(
        self,
        service: str,
        endpoint: str,
    ) -> Optional[DerivedMetrics]:
        """Compute derived metrics for a service/endpoint.
        
        Args:
            service: Service name.
            endpoint: Endpoint path.
            
        Returns:
            DerivedMetrics object, or None if any metric is unavailable.
        """
        p95_latency = self.client.get_p95_latency(service, endpoint)
        error_rate = self.client.get_error_rate(service, endpoint)
        request_rate = self.client.get_request_rate(service, endpoint)
        
        # All metrics must be available for valid derivation
        if p95_latency is None or error_rate is None or request_rate is None:
            return None
        
        return DerivedMetrics(
            service=service,
            endpoint=endpoint,
            p95_latency=p95_latency,
            error_rate=error_rate,
            request_rate=request_rate,
            timestamp=datetime.utcnow(),
        )
    
    def compute_for_all_services(self) -> List[DerivedMetrics]:
        """Compute derived metrics for all discovered services/endpoints.
        
        Returns:
            List of DerivedMetrics objects.
        """
        services_and_endpoints = self.client.get_available_services_and_endpoints()
        results = []
        
        for service, endpoints in services_and_endpoints.items():
            for endpoint in endpoints:
                metrics = self.compute_for_service_endpoint(service, endpoint)
                if metrics:
                    results.append(metrics)
        
        return results
