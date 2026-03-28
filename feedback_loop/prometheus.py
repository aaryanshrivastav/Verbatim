"""Prometheus-backed recovery metrics provider for Component 6."""

from __future__ import annotations

import math
import time
from typing import Optional

import requests

from feedback_loop.models import RecoveryMetrics


class PrometheusRecoveryProvider:
    """Fetch current error-rate and latency metrics from Prometheus."""

    def __init__(
        self,
        base_url: str = "http://localhost:9090",
        timeout_seconds: int = 3,
        range_window: str = "10s",
        request_metric: str = "http_request_total",
        latency_bucket_metric: str = "http_request_duration_seconds_bucket",
        service_label: str = "service_name",
        endpoint_label: str = "http_route",
        status_label: str = "http_status_code",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.range_window = range_window
        self.request_metric = request_metric
        self.latency_bucket_metric = latency_bucket_metric
        self.service_label = service_label
        self.endpoint_label = endpoint_label
        self.status_label = status_label

    def get_recovery_metrics(self, service: str, endpoint: Optional[str] = None) -> RecoveryMetrics:
        """Return current recovery metrics, with service-level fallback when needed."""
        issues = []
        error_rate = self._query_error_rate(service, endpoint)
        latency_ms = self._query_p95_latency_ms(service, endpoint)
        source = "prometheus"

        if error_rate is None and endpoint is not None:
            issues.append("endpoint_error_rate_missing")
            error_rate = self._query_error_rate(service, None)
            source = "prometheus_service_fallback"
        if latency_ms is None and endpoint is not None:
            issues.append("endpoint_latency_missing")
            latency_ms = self._query_p95_latency_ms(service, None)
            source = "prometheus_service_fallback"

        if error_rate is None:
            issues.append("error_rate_unknown")
        if latency_ms is None:
            issues.append("latency_unknown")

        return RecoveryMetrics(
            error_rate=error_rate,
            p95_latency_ms=latency_ms,
            source=source,
            issues=issues,
        )

    def _query_error_rate(self, service: str, endpoint: Optional[str]) -> Optional[float]:
        total_query = self._request_rate_query(service, endpoint)
        error_query = self._request_rate_query(service, endpoint, status_regex="5..")

        total = self._query_scalar(total_query)
        if total is None:
            return None
        if total <= 1e-6:
            return 0.0

        errors = self._query_scalar(error_query)
        if errors is None:
            return 0.0
        return min(1.0, max(0.0, errors / total))

    def _query_p95_latency_ms(self, service: str, endpoint: Optional[str]) -> Optional[float]:
        label_filters = [f'{self.service_label}="{service}"']
        if endpoint is not None:
            label_filters.append(f'{self.endpoint_label}="{endpoint}"')
            by_clause = f"le, {self.service_label}, {self.endpoint_label}"
        else:
            by_clause = f"le, {self.service_label}"
        filter_expr = ",".join(label_filters)
        promql = (
            "histogram_quantile(0.95, "
            f"sum by ({by_clause}) "
            f"(rate({self.latency_bucket_metric}{{{filter_expr}}}[{self.range_window}]))) * 1000"
        )
        return self._query_scalar(promql)

    def _request_rate_query(
        self,
        service: str,
        endpoint: Optional[str],
        status_regex: Optional[str] = None,
    ) -> str:
        label_filters = [f'{self.service_label}="{service}"']
        if endpoint is not None:
            label_filters.append(f'{self.endpoint_label}="{endpoint}"')
            by_clause = f"{self.service_label}, {self.endpoint_label}"
        else:
            by_clause = self.service_label
        if status_regex is not None:
            label_filters.append(f'{self.status_label}=~"{status_regex}"')
        filter_expr = ",".join(label_filters)
        return (
            f"sum by ({by_clause}) "
            f"(rate({self.request_metric}{{{filter_expr}}}[{self.range_window}]))"
        )

    def _query_scalar(self, promql: str) -> Optional[float]:
        response = requests.get(
            f"{self.base_url}/api/v1/query",
            params={"query": promql, "time": int(time.time())},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        series = payload.get("data", {}).get("result", [])
        if not series:
            return None

        raw_value = series[0].get("value", [0, "0"])[1]
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return None
        if math.isnan(value) or math.isinf(value):
            return None
        return value
