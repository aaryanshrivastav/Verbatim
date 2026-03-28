"""Mock Prometheus client for testing with synthetic data."""

import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PrometheusMetric:
    """Single metric value."""
    
    def __init__(self, timestamp: float, value: float):
        self.timestamp = timestamp
        self.value = value


class PrometheusQueryResult:
    """Result of a Prometheus query."""
    
    def __init__(self, metric: Dict[str, str], values: List[tuple]):
        self.metric = metric  # Labels
        self.values = values  # [(timestamp, value), ...]


class PrometheusClient:
    """Mock Prometheus client for synthetic testing.
    
    Returns synthetic metrics without requiring a real Prometheus instance.
    """
    
    def __init__(self, base_url: str = "http://localhost:9090"):
        """Initialize client.
        
        Args:
            base_url: Prometheus base URL (unused for mock)
        """
        self.base_url = base_url
        logger.info("Mock Prometheus client initialized (synthetic data mode)")
    
    def query(
        self,
        query: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[PrometheusQueryResult]:
        """Execute a PromQL query.
        
        Args:
            query: PromQL query string
            start_time: Query start time
            end_time: Query end time
            
        Returns:
            List of query results
        """
        logger.debug(f"Mock query: {query}")
        
        # Return empty results for mock
        return []
    
    def query_range(
        self,
        query: str,
        start_time: datetime,
        end_time: datetime,
        step: str = "15s",
    ) -> List[PrometheusQueryResult]:
        """Execute a range query.
        
        Args:
            query: PromQL query
            start_time: Range start
            end_time: Range end
            step: Query step
            
        Returns:
            List of range query results
        """
        logger.debug(f"Mock range query: {query}")
        return []
    
    def get_instant_value(
        self,
        query: str,
        time: datetime,
    ) -> Optional[float]:
        """Get instantaneous metric value.
        
        Args:
            query: PromQL query
            time: Query time
            
        Returns:
            Metric value or None
        """
        return None
