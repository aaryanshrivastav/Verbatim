"""Prometheus client for RCA evidence gathering and baselines."""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class PrometheusMetric:
    """Single metric value."""

    def __init__(self, timestamp: float, value: float):
        self.timestamp = timestamp
        self.value = value


class PrometheusQueryResult:
    """Result of a Prometheus query."""

    def __init__(self, metric: Dict[str, str], values: List[tuple]):
        self.metric = metric
        self.values = values


class PrometheusClient:
    """HTTP client for Prometheus queries used by RCA."""

    def __init__(self, base_url: str = "http://localhost:9090", timeout: int = 5):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def query(
        self,
        query: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[PrometheusQueryResult]:
        """Execute an instant PromQL query and normalize the response."""
        url = f"{self.base_url}/api/v1/query"
        params = {"query": query}
        response = requests.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success":
            logger.error("Prometheus query failed: %s", payload)
            return []

        results = []
        for series in payload.get("data", {}).get("result", []):
            results.append(
                PrometheusQueryResult(
                    metric=series.get("metric", {}),
                    values=[tuple(series.get("value", [0, "0"]))],
                )
            )
        return results

    def query_range(
        self,
        query: str,
        start_time: datetime,
        end_time: datetime,
        step: str = "15s",
    ) -> List[PrometheusQueryResult]:
        """Execute a range PromQL query and normalize the response."""
        url = f"{self.base_url}/api/v1/query_range"
        params = {
            "query": query,
            "start": int(start_time.timestamp()),
            "end": int(end_time.timestamp()),
            "step": step,
        }
        response = requests.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success":
            logger.error("Prometheus range query failed: %s", payload)
            return []

        results = []
        for series in payload.get("data", {}).get("result", []):
            results.append(
                PrometheusQueryResult(
                    metric=series.get("metric", {}),
                    values=[tuple(v) for v in series.get("values", [])],
                )
            )
        return results

    def get_instant_value(
        self,
        query: str,
        time: Optional[datetime] = None,
    ) -> Optional[float]:
        """Get the first scalar value returned by a PromQL query."""
        try:
            results = self.query(query)
        except requests.RequestException as exc:
            logger.error("Prometheus query error: %s", exc)
            return None

        if not results or not results[0].values:
            return None

        raw_value = results[0].values[0][1]
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return None
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    def get_latency_baseline(self, service: str, endpoint: str, window_minutes: int = 10) -> Optional[float]:
        """Return p95 latency baseline in milliseconds."""
        queries = [
            self._latency_query(service=service, endpoint=endpoint, window=f"{window_minutes}m"),
            self._latency_query(service=service, endpoint=None, window=f"{window_minutes}m"),
        ]
        for query in queries:
            value_seconds = self.get_instant_value(query)
            if value_seconds is None:
                continue
            return round(value_seconds * 1000.0, 3)
        return None

    def get_error_rate(self, service: str, endpoint: str) -> Optional[float]:
        """Return 5xx error rate as a fraction in [0, 1]."""
        queries = [
            self._error_rate_query(service=service, endpoint=endpoint),
            self._error_rate_query(service=service, endpoint=None),
        ]
        for query in queries:
            value = self.get_instant_value(query)
            if value is None:
                continue
            return max(0.0, min(1.0, value))
        return None

    @staticmethod
    def _latency_query(service: str, endpoint: Optional[str], window: str) -> str:
        selector = f'service_name="{service}"'
        if endpoint is not None:
            selector += f',http_route="{endpoint}"'
        return (
            "histogram_quantile(0.95, "
            f"sum by (le) (rate(http_request_duration_seconds_bucket{{{selector}}}[{window}])))"
        )

    @staticmethod
    def _error_rate_query(service: str, endpoint: Optional[str]) -> str:
        base_selector = f'service_name="{service}"'
        if endpoint is not None:
            base_selector += f',http_route="{endpoint}"'
        total = f'sum(rate(http_request_total{{{base_selector}}}[5m]))'
        errors = f'sum(rate(http_request_total{{{base_selector},http_status_code=~"5.."}}[5m]))'
        return f"({errors}) / clamp_min(({total}), 0.000001)"
