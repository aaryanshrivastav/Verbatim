from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from rca.models import CandidatePrediction, Confidence, ConfidenceBucket, Evidence, RCAOutput
from triage_integration.adapter import DetectionRCAAdapter, DetectionRCAAdapterConfig
from triage_integration.runner import TriagePipelineRunner
from triage_integration.service import TriagePipeline


def sample_incident_dict() -> dict:
    now = datetime.now(timezone.utc)
    start = now - timedelta(seconds=10)
    return {
        "incident_id": "inc-triage-1",
        "endpoint": "/checkout",
        "time_window_start": start.isoformat().replace("+00:00", "Z"),
        "time_window_end": now.isoformat().replace("+00:00", "Z"),
        "affected_services": ["payment-service", "order-service"],
        "anomaly_count": 2,
        "anomalies": [
            {
                "service": "payment-service",
                "severity": 0.91,
                "anomaly_type": "latency_spike",
                "detected_at": now.isoformat().replace("+00:00", "Z"),
            },
            {
                "service": "order-service",
                "severity": 0.61,
                "anomaly_type": "mixed",
                "detected_at": now.isoformat().replace("+00:00", "Z"),
            },
        ],
    }


class FailingPipeline:
    def analyze(self, incident):
        raise RuntimeError("boom")


class TraceAwarePipeline:
    def __init__(self):
        self.calls = 0
        self.trace_builder = type(
            "TraceBuilder",
            (),
            {
                "jaeger": type(
                    "Jaeger",
                    (),
                    {"query_traces_by_endpoint": self._query_traces_by_endpoint},
                )()
            },
        )()

    def _query_traces_by_endpoint(self, endpoint, start, end, limit=20):
        self.calls += 1
        return [] if self.calls == 1 else [object()]

    def analyze(self, incident):
        return RCAOutput(
            incident_id=incident.incident_id,
            endpoint=incident.endpoint,
            root_cause="payment-service",
            confidence=Confidence(value=0.72, bucket=ConfidenceBucket.HIGH),
            top_candidates=[CandidatePrediction(service="payment-service", probability=0.85)],
            affected_services=["payment-service"],
            state_vector=[0, 0, 0, 0, 2, 0],
            original_severity=0.91,
            time_window=[incident.time_window_start.isoformat(), incident.time_window_end.isoformat()],
            evidence=Evidence(traces=["payment-service trace matched"]),
        )


class StubAdapter:
    def analyze(self, incident):
        return RCAOutput(
            incident_id=incident["incident_id"],
            endpoint=incident["endpoint"],
            root_cause="payment-service",
            confidence=Confidence(value=0.72, bucket=ConfidenceBucket.HIGH),
            top_candidates=[
                CandidatePrediction(service="payment-service", probability=0.85),
                CandidatePrediction(service="order-service", probability=0.13),
            ],
            affected_services=["payment-service", "order-service"],
            state_vector=[0, 0, 0, 1, 2, 0],
            original_severity=0.91,
            time_window=[incident["time_window_start"], incident["time_window_end"]],
            evidence=Evidence(metrics=["payment-service p95 latency elevated"]),
        )


def test_detection_rca_adapter_fallback_builds_native_output():
    adapter = DetectionRCAAdapter(
        DetectionRCAAdapterConfig(fallback_on_error=True),
        pipeline=FailingPipeline(),
    )

    output = adapter.analyze(sample_incident_dict())

    assert output.root_cause == "payment-service"
    assert output.original_severity == 0.91
    assert output.affected_services == ["payment-service", "order-service"]
    assert output.state_vector == [0, 0, 0, 1, 2, 0]
    assert output.evidence.metrics == []


def test_detection_rca_adapter_waits_briefly_for_live_traces(monkeypatch):
    pipeline = TraceAwarePipeline()
    adapter = DetectionRCAAdapter(
        DetectionRCAAdapterConfig(
            fallback_on_error=False,
            max_trace_wait_seconds=1.0,
            trace_poll_interval_seconds=0.1,
        ),
        pipeline=pipeline,
    )
    monkeypatch.setattr("triage_integration.adapter.time.sleep", lambda _: None)

    output = adapter.analyze(sample_incident_dict())

    assert pipeline.calls >= 2
    assert output.root_cause == "payment-service"
    assert output.evidence.traces == ["payment-service trace matched"]


@pytest.mark.asyncio
async def test_triage_pipeline_processes_detection_incident_end_to_end():
    pipeline = TriagePipeline(adapter=StubAdapter())

    result = await pipeline.handle_incident(sample_incident_dict())

    assert result["incident_id"] == "inc-triage-1"
    assert result["rca_output"]["root_cause"] == "payment-service"
    assert result["rca_output"]["confidence"]["bucket"] == "high"
    assert result["rca_output"]["state_vector"] == [0, 0, 0, 1, 2, 0]


@pytest.mark.asyncio
async def test_runner_executes_one_tick_detection_to_rca():
    class FakeDetectionService:
        def __init__(self):
            self.config = type("Config", (), {"poll_interval_seconds": 1})()

        def tick(self):
            return {
                "events": [],
                "incidents": [sample_incident_dict()],
                "warmup_remaining_seconds": 0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "in_warmup": False,
            }

    runner = TriagePipelineRunner(
        pipeline=TriagePipeline(adapter=StubAdapter()),
        detection_service=FakeDetectionService(),
    )

    result = await runner.run_once()

    assert len(result["outcomes"]) == 1
    assert result["outcomes"][0]["rca_output"]["root_cause"] == "payment-service"
