"""Prometheus HTTP API client for fetching metrics.

Encapsulates PromQL queries and metric aggregation.
"""

import requests
from typing import Dict, List, Optional
from datetime import datetime


class PrometheusClient:
    """HTTP client for querying Prometheus metrics."""
    
    def __init__(self, base_url: str = "http://localhost:9090"):
        """Initialize Prometheus client.
        
        Args:
            base_url: Base URL for Prometheus (e.g., http://localhost:9090)
        """
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
    
    def query(self, promql: str) -> Dict:
        """Execute instant query against Prometheus.
        
        Args:
            promql: PromQL query string.
            
        Returns:
            Response dict with 'data.result' containing time series.
            
        Raises:
            Exception: If query fails.
        """
        url = f"{self.base_url}/api/v1/query"
        params = {"query": promql}
        
        try:
            response = self.session.get(url, params=params, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"Prometheus query failed: {e}")
    
    def get_p95_latency(self, service: str, endpoint: str) -> Optional[float]:
        """Fetch p95 latency for service/endpoint.
        
        Args:
            service: Service name label value.
            endpoint: Endpoint path label value.
            
        Returns:
            p95 latency in seconds, or None if not found.
        """
        promql = (
            f'histogram_quantile(0.95, '
            f'rate(request_latency_seconds_bucket'
            f'{{service="{service}", endpoint="{endpoint}"}}[1m]))'
        )
        
        try:
            result = self.query(promql)
            if result.get("data", {}).get("result"):
                value_str = result["data"]["result"][0]["value"][1]
                return float(value_str)
        except Exception:
            pass
        
        return None
    
    def get_error_rate(self, service: str, endpoint: str) -> Optional[float]:
        """Fetch error rate for service/endpoint.
        
        error_rate = error_count / total_count
        
        Args:
            service: Service name label value.
            endpoint: Endpoint path label value.
            
        Returns:
            Error rate in [0, 1], or None if not found.
        """
        promql = (
            f'('
            f'  sum(rate(error_count_total{{service="{service}", endpoint="{endpoint}"}}[1m]))'
            f'  /'
            f'  sum(rate(request_count_total{{service="{service}", endpoint="{endpoint}"}}[1m]))'
            f')'
        )
        
        try:
            result = self.query(promql)
            if result.get("data", {}).get("result"):
                value_str = result["data"]["result"][0]["value"][1]
                rate = float(value_str)
                return max(0.0, min(1.0, rate))
        except Exception:
            pass
        
        return None
    
    def get_request_rate(self, service: str, endpoint: str) -> Optional[float]:
        """Fetch request rate for service/endpoint.
        
        request_rate = requests per second
        
        Args:
            service: Service name label value.
            endpoint: Endpoint path label value.
            
        Returns:
            Request rate in requests/second, or None if not found.
        """
        promql = (
            f'sum(rate(request_count_total{{service="{service}", endpoint="{endpoint}"}}[1m]))'
        )
        
        try:
            result = self.query(promql)
            if result.get("data", {}).get("result"):
                value_str = result["data"]["result"][0]["value"][1]
                return float(value_str)
        except Exception:
            pass
        
        return None
    
    def get_available_services_and_endpoints(self) -> Dict[str, List[str]]:
        """Discover all services and endpoints currently in Prometheus.
        
        Returns:
            Dict mapping service name to list of endpoint paths.
        """
        # Query for all unique (service, endpoint) pairs from request_latency_seconds
        promql = 'count(request_latency_seconds) by (service, endpoint)'
        
        services_and_endpoints = {}
        
        try:
            result = self.query(promql)
            for entry in result.get("data", {}).get("result", []):
                labels = entry.get("metric", {})
                service = labels.get("service", "unknown")
                endpoint = labels.get("endpoint", "unknown")
                
                if service not in services_and_endpoints:
                    services_and_endpoints[service] = []
                
                if endpoint not in services_and_endpoints[service]:
                    services_and_endpoints[service].append(endpoint)
        except Exception:
            pass
        
        return services_and_endpoints
