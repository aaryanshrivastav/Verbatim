#!/usr/bin/env python3
"""Smoke test for the full Component 1 telemetry pipeline."""

from __future__ import annotations

import argparse
import asyncio
import threading
import time

import requests
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from shared.otel_metrics import init_metrics
from shared.telemetry import instrument_fastapi_app, setup_opentelemetry

tracer, meter, logger = setup_opentelemetry(
    service_name="pipeline-test",
    otlp_endpoint="http://localhost:4317",
    enable_prometheus_metrics=False,
)
otel_metrics = init_metrics(meter, "pipeline-test")

app = FastAPI(title="Pipeline Test")
instrument_fastapi_app(app, "pipeline-test")


class TestRequest(BaseModel):
    message: str


@app.get("/")
async def root():
    with tracer.start_as_current_span("root-span") as span:
        span.set_attribute("test.operation", "root")
        otel_metrics.record_request_count("GET", "/", 200)
        otel_metrics.record_request_duration("GET", "/", 0.05)
        logger.info("Root endpoint called", service_name="pipeline-test")
        return {"service": "pipeline-test", "status": "instrumented"}


@app.post("/test")
async def test_endpoint(request: TestRequest):
    with tracer.start_as_current_span("test-operation") as span:
        span.set_attribute("test.message", request.message)
        await asyncio.sleep(0.1)
        with tracer.start_as_current_span("nested-operation") as nested_span:
            nested_span.set_attribute("test.nested", True)
            await asyncio.sleep(0.05)
        otel_metrics.record_request_count("POST", "/test", 200)
        otel_metrics.record_request_duration("POST", "/test", 0.15)
        logger.info(
            "Test endpoint called",
            service_name="pipeline-test",
            payload=request.message,
        )
        return {"received": request.message, "processed": True}


@app.get("/slow")
async def slow_endpoint():
    with tracer.start_as_current_span("slow-operation") as span:
        span.set_attribute("test.slow", True)
        await asyncio.sleep(0.5)
        otel_metrics.record_request_count("GET", "/slow", 200)
        otel_metrics.record_request_duration("GET", "/slow", 0.5)
        logger.warning("Slow endpoint called", service_name="pipeline-test")
        return {"status": "completed", "duration": 0.5}


def test_backends():
    results = {}

    for name, url in {
        "jaeger": "http://localhost:16686/api/services",
        "prometheus": "http://localhost:9090/api/v1/query?query=up",
        "loki": "http://localhost:3100/ready",
        "otel_collector": "http://localhost:8889/metrics",
    }.items():
        try:
            response = requests.get(url, timeout=2)
            results[name] = response.status_code == 200
            status = "OK" if results[name] else "FAIL"
            print(f"{status} {name} backend accessible")
        except Exception:
            results[name] = False
            print(f"FAIL {name} backend not accessible")

    return results


def generate_test_traffic():
    print("Generating test traffic...")
    base_url = "http://localhost:8000"
    for idx in range(10):
        try:
            response = requests.get(f"{base_url}/", timeout=1)
            print(f"  Request {idx + 1}: GET / -> {response.status_code}")
            response = requests.post(
                f"{base_url}/test",
                json={"message": f"test-{idx}"},
                timeout=1,
            )
            print(f"  Request {idx + 1}: POST /test -> {response.status_code}")
            if idx < 3:
                response = requests.get(f"{base_url}/slow", timeout=2)
                print(f"  Request {idx + 1}: GET /slow -> {response.status_code}")
            time.sleep(0.1)
        except Exception as exc:
            print(f"  Request {idx + 1} failed: {exc}")


def verify_telemetry_in_backends():
    print("\nVerifying telemetry in backends...")

    try:
        response = requests.get("http://localhost:16686/api/services", timeout=5)
        response.raise_for_status()
        services = response.json().get("data", [])
        if services:
            print("OK Traces found in Jaeger")
            for service in services:
                print(f"  - Trace service: {service}")
        else:
            print("WARN No traces found in Jaeger yet")
    except Exception as exc:
        print(f"FAIL Error checking Jaeger: {exc}")

    try:
        response = requests.get(
            "http://localhost:9090/api/v1/query",
            params={"query": 'http_request_total{service_name="pipeline-test"}'},
            timeout=5,
        )
        response.raise_for_status()
        result = response.json().get("data", {}).get("result", [])
        if result:
            print("OK Metrics found in Prometheus")
            for series in result:
                print(f"  - {series['metric'].get('__name__', 'metric')} = {series['value'][1]}")
        else:
            print("WARN No pipeline-test metrics found in Prometheus yet")
    except Exception as exc:
        print(f"FAIL Error checking Prometheus: {exc}")

    try:
        response = requests.get("http://localhost:8889/metrics", timeout=5)
        response.raise_for_status()
        print(f"OK OTel Collector metrics endpoint reachable ({response.text.count('# HELP')} metric definitions)")
    except Exception as exc:
        print(f"FAIL Error checking OTel Collector: {exc}")

    try:
        labels = requests.get("http://localhost:3100/loki/api/v1/labels", timeout=5)
        labels.raise_for_status()
        if "service_name" in labels.json().get("data", []):
            values = requests.get(
                "http://localhost:3100/loki/api/v1/label/service_name/values",
                timeout=5,
            )
            values.raise_for_status()
            services = values.json().get("data", [])
            if services:
                print("OK Logs found in Loki")
                for service in services:
                    print(f"  - Log service: {service}")
            else:
                print("WARN Loki service_name label exists, but no values were returned")
        else:
            print("WARN Loki reachable, but service_name label not present yet")
    except Exception as exc:
        print(f"FAIL Error checking Loki: {exc}")


def parse_args():
    parser = argparse.ArgumentParser(description="Run the complete Component 1 pipeline smoke test.")
    parser.add_argument(
        "--no-input",
        action="store_true",
        help="Exit immediately instead of waiting for Enter at the end.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    print("COMPONENT 1 COMPLETE PIPELINE TEST")
    print("=" * 50)

    print("\nTesting backend connectivity...")
    backend_results = test_backends()
    if not all(backend_results.values()):
        print(f"\nFAIL Some backends are not accessible: {backend_results}")
        return False

    print("\nAll backends accessible. Starting pipeline test...")

    def run_server():
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(2)

    generate_test_traffic()

    print("\nWaiting for telemetry processing...")
    time.sleep(5)

    verify_telemetry_in_backends()

    print("\nPipeline smoke test complete.")
    if not args.no_input:
        input("\nPress Enter to exit...")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
