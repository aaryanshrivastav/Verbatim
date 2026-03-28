"""Prometheus HTTP client for querying metrics."""

import logging
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class PrometheusClient:
    """HTTP client for Prometheus API."""
    
    def __init__(self, base_url: str = "http://localhost:9090"):
        """Initialize Prometheus client.
        
        Args:
            base_url: Prometheus API base URL
        """
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
    
    def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "60s"
    ) -> Dict:
        """Execute a range query.
        
        Args:
            query: PromQL query string
            start: Start timestamp
            end: End timestamp
            step: Time step (e.g., "60s")
            
        Returns:
            Query result dict
        """
        url = f"{self.base_url}/api/v1/query_range"
        
        params = {
            "query": query,
            "start": int(start.timestamp()),
            "end": int(end.timestamp()),
            "step": step
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json().get("data", {})
        except Exception as e:
            logger.error(f"Prometheus query failed: {e}")
            return {}
    
    def query_instant(self, query: str, timestamp: Optional[datetime] = None) -> Dict:
        """Execute an instant query.
        
        Args:
            query: PromQL query string
            timestamp: Query timestamp (default: now)
            
        Returns:
            Query result dict
        """
        url = f"{self.base_url}/api/v1/query"
        
        params = {"query": query}
        if timestamp:
            params["time"] = int(timestamp.timestamp())
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json().get("data", {})
        except Exception as e:
            logger.error(f"Prometheus instant query failed: {e}")
            return {}
    
    def get_latency_baseline(
        self,
        service: str,
        endpoint: str,
        window_minutes: int = 5
    ) -> Optional[float]:
        """Get p95 latency baseline for service/endpoint.
        
        Args:
            service: Service name
            endpoint: HTTP endpoint
            window_minutes: Historical window to average
            
        Returns:
            Baseline latency in ms, or None
        """
        end = datetime.utcnow()
        start = end - timedelta(minutes=window_minutes)
        
        # PromQL: p95 latency over window
        query = (
            f'histogram_quantile(0.95, '
            f'rate(http_request_duration_seconds_bucket'
            f'{{service_name="{service}", http_route="{endpoint}"}}[1m]))'
        )
        
        result = self.query_range(query, start, end)
        
        # Extract latest value
        if result.get("type") == "matrix":
            for metric in result.get("result", []):
                values = metric.get("values", [])
                if values:
                    latest = values[-1]
                    # Prometheus returns in seconds, convert to ms
                    return float(latest[1]) * 1000.0
        
        return None
    
    def get_error_rate(
        self,
        service: str,
        endpoint: str,
        window: str = "5m"
    ) -> Optional[float]:
        """Get error rate for service/endpoint.
        
        Args:
            service: Service name
            endpoint: HTTP endpoint
            window: Time window (e.g., "5m")
            
        Returns:
            Error rate as fraction [0, 1], or None
        """
        query = (
            f'sum(rate(http_requests_total'
            f'{{service_name="{service}", http_route="{endpoint}", '
            f'http_status_code=~"5.."}}'
            f'[{window}])) / '
            f'sum(rate(http_requests_total'
            f'{{service_name="{service}", http_route="{endpoint}"}}'
            f'[{window}]))'
        )
        
        result = self.query_instant(query)
        
        if result.get("type") == "vector":
            for item in result.get("result", []):
                return float(item.get("value", [0, 0])[1])
        
        return None
    
    def get_request_rate(
        self,
        service: str,
        endpoint: str,
        window: str = "1m"
    ) -> Optional[float]:
        """Get request rate for service/endpoint.
        
        Args:
            service: Service name
            endpoint: HTTP endpoint
            window: Time window
            
        Returns:
            Request rate (requests/sec), or None
        """
        query = (
            f'sum(rate(http_requests_total'
            f'{{service_name="{service}", http_route="{endpoint}"}}'
            f'[{window}]))'
        )
        
        result = self.query_instant(query)
        
        if result.get("type") == "vector":
            for item in result.get("result", []):
                return float(item.get("value", [0, 0])[1])
        
        return None
