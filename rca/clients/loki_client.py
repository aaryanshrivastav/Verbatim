"""Loki client for RCA log evidence gathering."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List

import requests

logger = logging.getLogger(__name__)


class LokiLogEntry:
    """Single log entry from Loki."""

    def __init__(self, timestamp: str, message: str, labels: Dict[str, str]):
        self.timestamp = timestamp
        self.message = message
        self.labels = labels


class LokiClient:
    """HTTP client for Loki log queries."""

    def __init__(self, base_url: str = "http://localhost:3100", timeout: int = 5):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def query(
        self,
        query: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 100,
    ) -> List[LokiLogEntry]:
        """Execute a LogQL range query and normalize the response."""
        url = f"{self.base_url}/loki/api/v1/query_range"
        params = {
            "query": query,
            "start": str(int(start_time.timestamp() * 1_000_000_000)),
            "end": str(int(end_time.timestamp() * 1_000_000_000)),
            "limit": limit,
            "direction": "backward",
        }

        response = requests.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success":
            logger.error("Loki query failed: %s", payload)
            return []

        entries: List[LokiLogEntry] = []
        for stream in payload.get("data", {}).get("result", []):
            labels = stream.get("stream", {})
            for timestamp, line in stream.get("values", []):
                entries.append(LokiLogEntry(timestamp=timestamp, message=line, labels=labels))
        return entries

    def get_logs(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
        level: str = "ERROR",
    ) -> List[LokiLogEntry]:
        """Get logs for a service, filtering by level/message content."""
        queries = [
            f'{{level=~"{level}|{level.lower()}"}} |= "{service}"',
            f'{{job=~".+"}} |= "{service}" |= "{level}"',
            f'{{job=~".+"}} |= "{service}"',
        ]

        for query in queries:
            try:
                results = self.query(query, start_time, end_time, limit=50)
            except requests.RequestException as exc:
                logger.error("Loki query error: %s", exc)
                return []
            if results:
                return results
        return []

    def query_error_logs(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 10,
    ) -> List[str]:
        """Return plain-text error log messages for RCA evidence."""
        entries = self.get_logs(service, start_time, end_time, level="ERROR")
        messages = [entry.message.strip() for entry in entries if entry.message.strip()]
        return messages[:limit]
