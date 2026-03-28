"""Derived metrics computation from raw Prometheus metrics.

Derives p95_latency, error_rate, and request_rate from
raw counters and histograms.
"""

import logging
from typing import Dict, Tuple, Optional

from detection.prometheus_client import PrometheusClient
from detection.config import DetectionConfig

logger = logging.getLogger(__name__)


class DerivedMetricsComputer:
    """Computes derived metrics from Prometheus raw metrics.
    
    Attributes:
        client: PrometheusClient instance
        config: DetectionConfig with metric names
    """
    
    def __init__(self, client: PrometheusClient, config: DetectionConfig):
        """Initialize.
        
        Args:
            client: PrometheusClient instance
            config: DetectionConfig
        """
        self.client = client
        self.config = config
    
    def get_p95_latencies(self) -> Dict[Tuple[str, str], float]:
        """Fetch p95 latency for all service/endpoint pairs.
        
        Returns:
            Dict mapping (service, endpoint) -> p95_latency_seconds
        """
        return self.client.get_p95_latency_by_service_endpoint(
            latency_metric=self.config.latency_metric_name,
            service_label=self.config.service_label,
            endpoint_label=self.config.endpoint_label
        )
    
    def get_error_rates(self) -> Dict[Tuple[str, str], float]:
        """Fetch error rate for all service/endpoint pairs.
        
        Returns:
            Dict mapping (service, endpoint) -> error_rate [0, 1]
        """
        return self.client.get_error_rate_by_service_endpoint(
            request_metric=self.config.request_count_metric_name,
            service_label=self.config.service_label,
            endpoint_label=self.config.endpoint_label,
            status_label=self.config.status_label
        )
    
    def get_request_rates(self) -> Dict[Tuple[str, str], float]:
        """Fetch request rate for all service/endpoint pairs.
        
        Used for debug metadata only, not for triggering.
        
        Returns:
            Dict mapping (service, endpoint) -> requests_per_second
        """
        return self.client.get_request_rate_by_service_endpoint(
            request_metric=self.config.request_count_metric_name,
            service_label=self.config.service_label,
            endpoint_label=self.config.endpoint_label
        )
    
    def refresh_all(self) -> Dict[Tuple[str, str], Dict[str, float]]:
        """Fetch all derived metrics in one call.
        
        Returns:
            Dict mapping (service, endpoint) -> {
                "p95_latency": float,
                "error_rate": float,
                "request_rate": float
            }
        """
        latencies = self.get_p95_latencies()
        error_rates = self.get_error_rates()
        request_rates = self.get_request_rates()
        
        # Merge into single dict
        all_keys = set(latencies.keys()) | set(error_rates.keys()) | set(request_rates.keys())
        result = {}
        
        for key in all_keys:
            result[key] = {
                "p95_latency": latencies.get(key, 0.0),
                "error_rate": error_rates.get(key, 0.0),
                "request_rate": request_rates.get(key, 0.0),
            }
        
        return result
