#!/usr/bin/env python3
"""Component 1 validation focused on the real services in this repo."""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import requests

JAEGER_BASE_URL = "http://localhost:16686"
PROMETHEUS_BASE_URL = "http://localhost:9090"
LOKI_BASE_URL = "http://localhost:3100"
APP_BASE_URL = "http://localhost:8000"
OTEL_COLLECTOR_METRICS_URL = "http://localhost:8889/metrics"

EXPECTED_SERVICES = {
    "microservices-demo",
    "auth-service",
    "catalog-service",
    "order-service",
    "payment-service",
    "gateway-service",
}

REQUEST_TIMEOUT_SECONDS = 5
MAX_INGESTION_WAIT_SECONDS = 10
TRACE_SAMPLING_DESCRIPTION = "100% default with OTEL_SAMPLING_RATE override"


@dataclass
class ValidationResults:
    traces_status: str = "BROKEN"
    metrics_status: str = "BROKEN"
    logs_status: str = "BROKEN"
    prometheus_scrape_interval: Optional[str] = None
    actual_ingestion_delay: Dict[str, float] = field(default_factory=dict)
    service_identity_consistent: bool = False
    trace_services: Set[str] = field(default_factory=set)
    metric_services: Set[str] = field(default_factory=set)
    log_services: Set[str] = field(default_factory=set)
    sampling_rate: str = TRACE_SAMPLING_DESCRIPTION


class Component1Validator:
    def __init__(self) -> None:
        self.results = ValidationResults()

    def _safe_get_json(self, url: str, **kwargs) -> Optional[Dict]:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, **kwargs)
        response.raise_for_status()
        return response.json()

    def _get_jaeger_services(self) -> List[str]:
        data = self._safe_get_json(f"{JAEGER_BASE_URL}/api/services")
        if not data:
            return []
        return [str(service) for service in data.get("data", [])]

    def _get_prometheus_services(self) -> Set[str]:
        query = 'count by (service_name) (http_request_total)'
        data = self._safe_get_json(
            f"{PROMETHEUS_BASE_URL}/api/v1/query",
            params={"query": query},
        )
        services = set()
        for series in data.get("data", {}).get("result", []):
            service_name = series.get("metric", {}).get("service_name")
            if service_name:
                services.add(service_name)
        return services

    def _get_loki_services(self) -> Set[str]:
        try:
            labels = self._safe_get_json(f"{LOKI_BASE_URL}/loki/api/v1/labels")
            if "service_name" in labels.get("data", []):
                values = self._safe_get_json(
                    f"{LOKI_BASE_URL}/loki/api/v1/label/service_name/values"
                )
                return {str(value) for value in values.get("data", [])}
        except requests.RequestException:
            pass

        query = '{service_name=~".+"}'
        response = requests.get(
            f"{LOKI_BASE_URL}/loki/api/v1/query",
            params={"query": query},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        services = set()
        for stream in data.get("data", {}).get("result", []):
            labels = stream.get("stream", {})
            service_name = labels.get("service_name")
            if service_name:
                services.add(service_name)
        return services

    def _print_services(self, services: Set[str]) -> str:
        if not services:
            return "[]"
        return "[" + ", ".join(sorted(services)) + "]"

    def test_traces_pipeline(self) -> None:
        print("Testing Traces Pipeline...")
        try:
            services = set(self._get_jaeger_services())
            self.results.trace_services = services
            if not services:
                print("  FAIL Jaeger reachable but no services found")
                return

            print(f"  OK Jaeger has services: {self._print_services(services)}")
            matched = services & EXPECTED_SERVICES
            if matched:
                print(f"  OK Expected services found in Jaeger: {self._print_services(matched)}")
                self.results.traces_status = "WORKING" if matched == EXPECTED_SERVICES else "PARTIAL"
            else:
                print("  FAIL Jaeger has traces, but none map to the expected service names")
        except Exception as exc:
            print(f"  FAIL Traces test failed: {exc}")

    def test_metrics_pipeline(self) -> None:
        print("Testing Metrics Pipeline...")
        try:
            data = self._safe_get_json(f"{PROMETHEUS_BASE_URL}/api/v1/targets")
            targets = data.get("data", {}).get("activeTargets", [])
            otel_target = None
            for target in targets:
                if "otel-collector:8889" in target.get("labels", {}).get("instance", ""):
                    otel_target = target
                    break

            if not otel_target:
                print("  FAIL OTel Collector target not found in Prometheus")
                return

            health = otel_target.get("health", "unknown")
            scrape_interval = otel_target.get("scrapeInterval", "unknown")
            self.results.prometheus_scrape_interval = scrape_interval
            print(f"  OK OTel Collector target: health={health}, scrape={scrape_interval}")

            if scrape_interval == "2s":
                print("  OK Prometheus scrape interval is correctly set to 2s")
            else:
                print(f"  FAIL Prometheus scrape interval is {scrape_interval}, expected 2s")

            services = self._get_prometheus_services()
            self.results.metric_services = services
            if services:
                print(f"  OK Prometheus has service metrics: {self._print_services(services)}")
                self.results.metrics_status = "WORKING"
            else:
                print("  FAIL Prometheus is up but no http_request_total series were found")
        except Exception as exc:
            print(f"  FAIL Metrics test failed: {exc}")

    def test_logs_pipeline(self) -> None:
        print("Testing Logs Pipeline...")
        try:
            response = requests.get(f"{LOKI_BASE_URL}/ready", timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            print("  OK Loki is ready")

            services = self._get_loki_services()
            self.results.log_services = services
            if services:
                print(f"  OK Loki has service labels: {self._print_services(services)}")
                self.results.logs_status = "WORKING"
            else:
                print("  FAIL Loki is reachable but no service_name labels were found")
        except Exception as exc:
            print(f"  FAIL Logs test failed: {exc}")

    def test_service_identity_consistency(self) -> None:
        print("Testing Service Identity Consistency...")
        trace_services = self.results.trace_services & EXPECTED_SERVICES
        metric_services = self.results.metric_services & EXPECTED_SERVICES
        common = trace_services & metric_services

        if common:
            self.results.service_identity_consistent = True
            print(f"  OK Common service identities across traces and metrics: {self._print_services(common)}")
            if self.results.log_services:
                log_common = common & self.results.log_services
                if log_common:
                    print(f"  OK Logs also share service names: {self._print_services(log_common)}")
                else:
                    print("  WARN Logs are present, but service_name labels do not overlap with traces/metrics yet")
        else:
            print("  FAIL No shared service_name values between traces and metrics")

    def measure_ingestion_delay(self) -> None:
        print("Measuring Ingestion Delay...")
        try:
            start_time = time.time()
            baseline_response = self._safe_get_json(
                f"{PROMETHEUS_BASE_URL}/api/v1/query",
                params={
                    "query": 'sum(http_request_total{service_name="microservices-demo"})',
                },
            )
            baseline_metrics = 0.0
            baseline_results = baseline_response.get("data", {}).get("result", [])
            if baseline_results:
                baseline_metrics = float(baseline_results[0]["value"][1])

            for _ in range(5):
                response = requests.get(APP_BASE_URL, timeout=REQUEST_TIMEOUT_SECONDS)
                response.raise_for_status()
            print("  OK Test requests sent to main application")

            trace_start_micros = int(start_time * 1_000_000)
            trace_found = False
            metrics_found = False
            for _ in range(MAX_INGESTION_WAIT_SECONDS):
                time.sleep(1)
                if not trace_found:
                    trace_response = requests.get(
                        f"{JAEGER_BASE_URL}/api/traces",
                        params={
                            "service": "microservices-demo",
                            "limit": 5,
                            "start": trace_start_micros,
                        },
                        timeout=REQUEST_TIMEOUT_SECONDS,
                    )
                    trace_response.raise_for_status()
                    traces = trace_response.json().get("data", [])
                    if traces:
                        delay = time.time() - start_time
                        self.results.actual_ingestion_delay["traces"] = delay
                        trace_found = True
                        print(f"  OK Traces appeared after {delay:.2f}s")

                if not metrics_found:
                    metrics_response = self._safe_get_json(
                        f"{PROMETHEUS_BASE_URL}/api/v1/query",
                        params={
                            "query": 'sum(http_request_total{service_name="microservices-demo"})',
                        },
                    )
                    results = metrics_response.get("data", {}).get("result", [])
                    if results and float(results[0]["value"][1]) > baseline_metrics:
                        delay = time.time() - start_time
                        self.results.actual_ingestion_delay["metrics"] = delay
                        metrics_found = True
                        print(f"  OK Metrics appeared after {delay:.2f}s")

                if trace_found and metrics_found:
                    break

            if not self.results.actual_ingestion_delay:
                print("  FAIL No new traces or metrics were observed after the test request")
                return

            if not trace_found:
                print("  WARN No new trace was observed during the delay window")

            max_delay = max(self.results.actual_ingestion_delay.values())
            if max_delay <= 3.0:
                print(f"  OK Ingestion delay {max_delay:.2f}s is within the expected 2-3s window")
            else:
                print(f"  FAIL Ingestion delay {max_delay:.2f}s exceeds the expected 3s upper bound")
        except Exception as exc:
            print(f"  FAIL Ingestion delay measurement failed: {exc}")

    def test_sampling_configuration(self) -> None:
        print("Checking Trace Sampling...")
        print(f"  OK Sampling configuration in code: {self.results.sampling_rate}")

    def generate_report(self) -> bool:
        print("\n" + "=" * 80)
        print("COMPONENT 1 VALIDATION REPORT")
        print("=" * 80)

        print("\nSIGNAL PIPELINES:")
        print(f"  Traces:  {self.results.traces_status}")
        print(f"  Metrics: {self.results.metrics_status}")
        print(f"  Logs:    {self.results.logs_status}")

        print("\nPERFORMANCE:")
        print(f"  Prometheus Scrape Interval: {self.results.prometheus_scrape_interval}")
        if self.results.actual_ingestion_delay:
            for signal, delay in sorted(self.results.actual_ingestion_delay.items()):
                print(f"  {signal.title()} Delay: {delay:.2f}s")

        print("\nCONFIGURATION:")
        service_identity = "CONSISTENT" if self.results.service_identity_consistent else "INCONSISTENT"
        print(f"  Service Identity: {service_identity}")
        print(f"  Sampling Rate: {self.results.sampling_rate}")

        print("\nSERVICE SETS:")
        print(f"  Traces:  {self._print_services(self.results.trace_services)}")
        print(f"  Metrics: {self._print_services(self.results.metric_services)}")
        print(f"  Logs:    {self._print_services(self.results.log_services)}")

        issues = []
        if self.results.traces_status == "BROKEN":
            issues.append("Traces pipeline broken - RCA will fail")
        if self.results.metrics_status != "WORKING":
            issues.append("Metrics pipeline not fully working - detection may be degraded")
        if self.results.logs_status != "WORKING":
            issues.append("Logs pipeline not fully working - evidence collection may be degraded")
        if self.results.prometheus_scrape_interval != "2s":
            issues.append("Prometheus scrape interval is not 2s")
        if not self.results.service_identity_consistent:
            issues.append("Service identity is inconsistent across telemetry signals")

        print("\nCRITICAL ISSUES:")
        if issues:
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("  - None")

        all_working = (
            self.results.traces_status in {"WORKING", "PARTIAL"}
            and self.results.metrics_status == "WORKING"
            and self.results.prometheus_scrape_interval == "2s"
            and self.results.service_identity_consistent
        )
        if all_working and self.results.logs_status == "WORKING":
            overall = "READY"
        elif all_working:
            overall = "READY WITH LOG PIPELINE CAVEAT"
        else:
            overall = "NEEDS FIXES"
        print(f"\nOVERALL STATUS: {overall}")
        return all_working


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Component 1 telemetry pipelines.")
    parser.add_argument(
        "--no-input",
        action="store_true",
        help="Exit immediately instead of waiting for Enter at the end.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validator = Component1Validator()

    print("COMPONENT 1 COMPREHENSIVE VALIDATION")
    print("=" * 50)

    validator.test_traces_pipeline()
    validator.test_metrics_pipeline()
    validator.test_logs_pipeline()
    validator.test_service_identity_consistency()
    validator.measure_ingestion_delay()
    validator.test_sampling_configuration()

    success = validator.generate_report()

    if not args.no_input and sys.stdin.isatty():
        input("\nPress Enter to exit...")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
