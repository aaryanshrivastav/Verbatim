"""Jaeger client for RCA trace queries with synthetic fallback."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List

import requests

logger = logging.getLogger(__name__)


@dataclass
class JaegerSpan:
    """Single span in a trace."""

    trace_id: str
    span_id: str
    service: str
    operation: str
    start_time: int  # microseconds
    duration: int  # microseconds
    tags: Dict[str, object]


@dataclass
class JaegerTrace:
    """Jaeger trace object."""

    trace_id: str
    spans: List[JaegerSpan]

    def get_service_names(self) -> List[str]:
        return list({span.service for span in self.spans})

    def get_spans_for_service(self, service: str) -> List[JaegerSpan]:
        return [span for span in self.spans if span.service == service]


class JaegerClient:
    """HTTP client for Jaeger traces with synthetic fallback."""

    SERVICES = [
        "gateway-service",
        "auth-service",
        "catalog-service",
        "order-service",
        "payment-service",
        "redis",
        "postgres",
    ]

    def __init__(
        self,
        base_url: str = "http://localhost:16686",
        timeout: int = 5,
        allow_synthetic_fallback: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.allow_synthetic_fallback = allow_synthetic_fallback

    def query_traces_by_endpoint(
        self,
        endpoint: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 100,
    ) -> List[JaegerTrace]:
        """Get traces for an endpoint in a time window."""
        try:
            traces_by_id: Dict[str, JaegerTrace] = {}
            for service in self._get_services():
                traces = self._query_live_traces(start_time, end_time, service=service, limit=limit)
                for trace in traces:
                    if self._trace_matches_endpoint(trace, endpoint):
                        traces_by_id[trace.trace_id] = trace
                if len(traces_by_id) >= limit:
                    break
            filtered = list(traces_by_id.values())
            if filtered:
                return filtered[:limit]
            logger.warning("No live Jaeger traces matched %s", endpoint)
        except requests.RequestException as exc:
            logger.warning("Jaeger query failed (%s)", exc)
        if self.allow_synthetic_fallback:
            logger.warning("Using synthetic Jaeger fallback for %s", endpoint)
            return self._generate_synthetic_traces(endpoint, start_time, limit)
        return []

    def query_traces_by_service(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 100,
    ) -> List[JaegerTrace]:
        """Get traces for a specific service in a time window."""
        try:
            traces = self._query_live_traces(start_time, end_time, service=service, limit=limit)
            if traces:
                return traces
        except requests.RequestException as exc:
            logger.warning("Jaeger service query failed (%s)", exc)
        if self.allow_synthetic_fallback:
            logger.warning("Using synthetic Jaeger fallback for service %s", service)
            return self._generate_synthetic_traces(f"/{service}/mock", start_time, limit)
        return []

    def get_service_span_metrics(self, trace: JaegerTrace, service: str) -> tuple:
        """Get span count, error count, and durations in ms for one service."""
        spans = trace.get_spans_for_service(service)
        if not spans:
            return (0, 0, [])

        span_count = len(spans)
        error_count = sum(1 for span in spans if self._span_is_error(span))
        durations = [span.duration / 1000.0 for span in spans]
        return (span_count, error_count, durations)

    def _query_live_traces(
        self,
        start_time: datetime,
        end_time: datetime,
        service: str | None = None,
        limit: int = 100,
    ) -> List[JaegerTrace]:
        url = f"{self.base_url}/api/traces"
        params: Dict[str, object] = {
            "start": int(start_time.timestamp() * 1_000_000),
            "end": int(end_time.timestamp() * 1_000_000),
            "limit": limit,
        }
        if service:
            params["service"] = service

        response = requests.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        traces = []
        for item in payload.get("data", []):
            trace = self._parse_trace(item)
            if trace.spans:
                traces.append(trace)
        return traces

    def _get_services(self) -> List[str]:
        response = requests.get(f"{self.base_url}/api/services", timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        return [str(service) for service in payload.get("data", [])]

    def _parse_trace(self, payload: Dict[str, object]) -> JaegerTrace:
        processes = payload.get("processes", {}) or {}
        spans: List[JaegerSpan] = []
        for span in payload.get("spans", []) or []:
            process = processes.get(span.get("processID"), {}) if isinstance(processes, dict) else {}
            service_name = process.get("serviceName", "unknown")
            tags = {
                tag.get("key"): tag.get("value")
                for tag in span.get("tags", []) or []
                if isinstance(tag, dict)
            }
            spans.append(
                JaegerSpan(
                    trace_id=str(span.get("traceID")),
                    span_id=str(span.get("spanID")),
                    service=str(service_name),
                    operation=str(span.get("operationName", "")),
                    start_time=int(span.get("startTime", 0)),
                    duration=int(span.get("duration", 0)),
                    tags=tags,
                )
            )
        return JaegerTrace(trace_id=str(payload.get("traceID", "")), spans=spans)

    @staticmethod
    def _trace_matches_endpoint(trace: JaegerTrace, endpoint: str) -> bool:
        for span in trace.spans:
            values = [str(span.operation), str(span.tags.get("http.route", "")), str(span.tags.get("http.target", ""))]
            if any(endpoint == value or endpoint in value for value in values if value):
                return True
        return False

    @staticmethod
    def _span_is_error(span: JaegerSpan) -> bool:
        error_flag = span.tags.get("error")
        if error_flag in (True, "true", "True", 1, "1"):
            return True
        status = span.tags.get("http.status_code")
        try:
            return int(status) >= 500
        except (TypeError, ValueError):
            return False

    def _generate_synthetic_traces(
        self,
        endpoint: str,
        start_time: datetime,
        limit: int,
    ) -> List[JaegerTrace]:
        traces = []
        num_traces = min(limit, random.randint(20, 50))
        for i in range(num_traces):
            trace_id = f"mock-trace-{i:04d}"
            spans = self._generate_trace_spans(endpoint, trace_id, start_time)
            traces.append(JaegerTrace(trace_id=trace_id, spans=spans))
        return traces

    def _generate_trace_spans(
        self,
        endpoint: str,
        trace_id: str,
        start_time: datetime,
    ) -> List[JaegerSpan]:
        spans = []
        base_micros = int(start_time.timestamp() * 1e6)
        span_id = 1
        gateway_duration = random.randint(10_000, 100_000)
        spans.append(
            JaegerSpan(
                trace_id=trace_id,
                span_id=str(span_id),
                service="gateway-service",
                operation=f"GET {endpoint}",
                start_time=base_micros,
                duration=gateway_duration,
                tags={"http.route": endpoint, "http.status_code": 200},
            )
        )
        span_id += 1

        current_time = base_micros + random.randint(1000, 5000)
        selected_services = random.sample(self.SERVICES[1:], random.randint(2, 4))
        for service in selected_services:
            duration = random.randint(5000, 50000)
            spans.append(
                JaegerSpan(
                    trace_id=trace_id,
                    span_id=str(span_id),
                    service=service,
                    operation="call",
                    start_time=current_time,
                    duration=duration,
                    tags={"status": "ok"},
                )
            )
            span_id += 1
            current_time += duration + random.randint(1000, 5000)
        return spans
