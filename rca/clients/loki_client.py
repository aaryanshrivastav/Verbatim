"""Mock Loki client for testing with synthetic data."""

import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class LokiLogEntry:
    """Single log entry from Loki."""
    
    def __init__(self, timestamp: str, message: str, labels: Dict[str, str]):
        self.timestamp = timestamp
        self.message = message
        self.labels = labels


class LokiClient:
    """Mock Loki client for synthetic testing.
    
    Returns synthetic logs without requiring a real Loki instance.
    """
    
    def __init__(self, base_url: str = "http://localhost:3100"):
        """Initialize client.
        
        Args:
            base_url: Loki base URL (unused for mock)
        """
        self.base_url = base_url
        logger.info("Mock Loki client initialized (synthetic data mode)")
    
    def query(
        self,
        query: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 100,
    ) -> List[LokiLogEntry]:
        """Query logs.
        
        Args:
            query: LogQL query
            start_time: Query start
            end_time: Query end
            limit: Max results
            
        Returns:
            List of log entries
        """
        logger.debug(f"Mock Loki query: {query}")
        return []
    
    def get_logs(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
        level: str = "ERROR",
    ) -> List[LokiLogEntry]:
        """Get logs for a service.
        
        Args:
            service: Service name
            start_time: Time range start
            end_time: Time range end
            level: Log level filter
            
        Returns:
            List of logs
        """
        return []
