"""HTTP client for Prometheus metrics queries.

Encapsulates all PromQL queries in one place.
Easy to swap with other time-series backends if needed.
"""

import logging
from typing import Dict, Optional, Tuple
import time

import requests

logger = logging.getLogger(__name__)


class PrometheusClient:
    """HTTP client for querying Prometheus.
    
    Attributes:
        base_url: Prometheus base URL (e.g., http://localhost:9090)
        timeout: Request timeout in seconds
    """
    
    def __init__(self, base_url: str, timeout: int = 5):
        """Initialize client.
        
        Args:
            base_url: Prometheus base URL
            timeout: HTTP request timeout (seconds)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
    
    def query(self, promql: str) -> Dict:
        """Execute instant query against Prometheus.
        
        Args:
            promql: PromQL query string
            
        Returns:
            Response dict from Prometheus API
            
        Raises:
            requests.RequestException: If query fails
        """
        url = f"{self.base_url}/api/v1/query"
        params = {"query": promql, "time": int(time.time())}
        
        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("status") != "success":
                logger.error(f"Prometheus query failed: {data}")
                return {"result": []}
            
            return data
        except requests.RequestException as e:
            logger.error(f"Prometheus query error: {e}")
            raise
    
    def query_range(self, promql: str, start: int, end: int, step: int = 1) -> Dict:
        """Execute range query against Prometheus.
        
        Args:
            promql: PromQL query string
            start: Start timestamp (seconds since epoch)
            end: End timestamp (seconds since epoch)
            step: Resolution (seconds)
            
        Returns:
            Response dict from Prometheus API
            
        Raises:
            requests.RequestException: If query fails
        """
        url = f"{self.base_url}/api/v1/query_range"
        params = {"query": promql, "start": start, "end": end, "step": step}
        
        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("status") != "success":
                logger.error(f"Prometheus range query failed: {data}")
                return {"result": []}
            
            return data
        except requests.RequestException as e:
            logger.error(f"Prometheus range query error: {e}")
            raise
    
    def get_p95_latency_by_service_endpoint(
        self, 
        latency_metric: str = "http_request_duration_seconds",
        service_label: str = "service_name",
        endpoint_label: str = "http_route"
    ) -> Dict[Tuple[str, str], float]:
        """Fetch p95 latency for each (service, endpoint) pair.
        
        Args:
            latency_metric: Name of latency histogram metric
            service_label: Label name for service
            endpoint_label: Label name for endpoint
            
        Returns:
            Dict mapping (service, endpoint) -> p95_latency_seconds
        """
        promql = (
            f"histogram_quantile(0.95, "
            f"sum by (le, {service_label}, {endpoint_label}) "
            f"(rate({latency_metric}_bucket[1m])))"
        )
        
        try:
            data = self.query(promql)
            result = {}
            
            for series in data.get("result", []):
                labels = series.get("metric", {})
                service = labels.get(service_label, "unknown")
                endpoint = labels.get(endpoint_label, "unknown")
                value = float(series.get("value", [0, "0"])[1])
                
                result[(service, endpoint)] = value
            
            return result
        except Exception as e:
            logger.error(f"Error fetching p95 latency: {e}")
            return {}
    
    def get_request_rate_by_service_endpoint(
        self,
        request_metric: str = "http_request_total",
        service_label: str = "service_name",
        endpoint_label: str = "http_route"
    ) -> Dict[Tuple[str, str], float]:
        """Fetch request rate (req/sec) for each (service, endpoint).
        
        Args:
            request_metric: Name of request counter metric
            service_label: Label name for service
            endpoint_label: Label name for endpoint
            
        Returns:
            Dict mapping (service, endpoint) -> requests_per_second
        """
        promql = (
            f"sum by ({service_label}, {endpoint_label}) "
            f"(rate({request_metric}[1m]))"
        )
        
        try:
            data = self.query(promql)
            result = {}
            
            for series in data.get("result", []):
                labels = series.get("metric", {})
                service = labels.get(service_label, "unknown")
                endpoint = labels.get(endpoint_label, "unknown")
                value = float(series.get("value", [0, "0"])[1])
                
                result[(service, endpoint)] = value
            
            return result
        except Exception as e:
            logger.error(f"Error fetching request rate: {e}")
            return {}
    
    def get_error_rate_by_service_endpoint(
        self,
        request_metric: str = "http_request_total",
        service_label: str = "service_name",
        endpoint_label: str = "http_route",
        status_label: str = "http_status_code"
    ) -> Dict[Tuple[str, str], float]:
        """Fetch error rate for each (service, endpoint).
        
        Computes: (5xx errors) / (total requests)
        
        Args:
            request_metric: Name of request counter metric
            service_label: Label name for service
            endpoint_label: Label name for endpoint
            status_label: Label name for HTTP status code
            
        Returns:
            Dict mapping (service, endpoint) -> error_rate [0, 1]
        """
        # Total request rate
        total_promql = (
            f"sum by ({service_label}, {endpoint_label}) "
            f"(rate({request_metric}[1m]))"
        )
        
        # 5xx error rate
        error_promql = (
            f"sum by ({service_label}, {endpoint_label}) "
            f"(rate({request_metric}{{{status_label}=~\"5..\"}}[1m]))"
        )
        
        try:
            # Fetch total requests
            total_data = self.query(total_promql)
            total_requests = {}
            for series in total_data.get("result", []):
                labels = series.get("metric", {})
                key = (labels.get(service_label, "unknown"), 
                       labels.get(endpoint_label, "unknown"))
                value = float(series.get("value", [0, "0"])[1])
                total_requests[key] = value
            
            # Fetch error requests
            error_data = self.query(error_promql)
            error_requests = {}
            for series in error_data.get("result", []):
                labels = series.get("metric", {})
                key = (labels.get(service_label, "unknown"), 
                       labels.get(endpoint_label, "unknown"))
                value = float(series.get("value", [0, "0"])[1])
                error_requests[key] = value
            
            # Compute rates
            result = {}
            for key in total_requests:
                total = total_requests[key]
                errors = error_requests.get(key, 0.0)
                # Avoid division by zero: use epsilon
                if total > 1e-6:
                    error_rate = errors / total
                else:
                    error_rate = 0.0
                result[key] = min(1.0, error_rate)  # Clip to [0, 1]
            
            return result
        except Exception as e:
            logger.error(f"Error fetching error rate: {e}")
            return {}
