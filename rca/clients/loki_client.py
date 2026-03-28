"""Loki HTTP client for querying logs."""

import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class LokiClient:
    """HTTP client for Loki API."""
    
    def __init__(self, base_url: str = "http://localhost:3100"):
        """Initialize Loki client.
        
        Args:
            base_url: Loki API base URL
        """
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
    
    def query_logs(
        self,
        service: str,
        start: datetime,
        end: datetime,
        limit: int = 100
    ) -> List[Dict]:
        """Query logs for service in time range.
        
        Args:
            service: Service name
            start: Start timestamp
            end: End timestamp
            limit: Max log entries
            
        Returns:
            List of log entries
        """
        url = f"{self.base_url}/loki/api/v1/query_range"
        
        # LogQL query: filter by service label
        query = f'{{service="{service}"}}'
        
        params = {
            "query": query,
            "start": int(start.timestamp() * 1e9),  # Nanoseconds
            "end": int(end.timestamp() * 1e9),
            "limit": limit
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            logs = []
            for stream in data.get("data", {}).get("result", []):
                for entry in stream.get("values", []):
                    # entry[0] is timestamp (ns), entry[1] is log line
                    logs.append({
                        "timestamp": int(entry[0]),
                        "message": entry[1]
                    })
            
            return logs
        except Exception as e:
            logger.error(f"Loki query failed: {e}")
            return []
    
    def query_error_logs(
        self,
        service: str,
        start: datetime,
        end: datetime,
        limit: int = 50
    ) -> List[str]:
        """Query error/exception logs for service.
        
        Args:
            service: Service name
            start: Start timestamp
            end: End timestamp
            limit: Max entries
            
        Returns:
            List of error log messages
        """
        url = f"{self.base_url}/loki/api/v1/query_range"
        
        # LogQL: filter service, search for error keywords
        query = f'{{service="{service}"}} |= "error" or |= "exception" or |= "timeout"'
        
        params = {
            "query": query,
            "start": int(start.timestamp() * 1e9),
            "end": int(end.timestamp() * 1e9),
            "limit": limit
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            error_logs = []
            for stream in data.get("data", {}).get("result", []):
                for entry in stream.get("values", []):
                    message = entry[1]
                    error_logs.append(message)
            
            return error_logs
        except Exception as e:
            logger.error(f"Loki error log query failed: {e}")
            return []
    
    def query_logs_for_pattern(
        self,
        service: str,
        pattern: str,
        start: datetime,
        end: datetime,
        limit: int = 20
    ) -> List[str]:
        """Query logs matching pattern for service.
        
        Args:
            service: Service name
            pattern: Search pattern (keyword)
            start: Start timestamp
            end: End timestamp
            limit: Max entries
            
        Returns:
            List of matching log messages
        """
        url = f"{self.base_url}/loki/api/v1/query_range"
        
        # LogQL: filter by service and pattern
        query = f'{{service="{service}"}} |= "{pattern}"'
        
        params = {
            "query": query,
            "start": int(start.timestamp() * 1e9),
            "end": int(end.timestamp() * 1e9),
            "limit": limit
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            results = []
            for stream in data.get("data", {}).get("result", []):
                for entry in stream.get("values", []):
                    results.append(entry[1])
            
            return results
        except Exception as e:
            logger.error(f"Loki pattern query failed: {e}")
            return []
