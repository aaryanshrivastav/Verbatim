"""Tests for the temporary Detection -> Decision -> Executor integration layer."""

from datetime import datetime, timedelta, timezone

import pytest

from decision_engine.events import InMemoryEventPublisher
from decision_engine.registry import DecisionRegistry
from pipeline_integration.adapter import DetectionIncidentAdapter
from pipeline_integration.runner import IntegratedPipelineRunner
from pipeline_integration.service import IntegratedPipeline
from remediation_executor.catalog import ServiceCatalog, ServiceTarget
from remediation_executor.runtime import FakeDockerRuntime


def sample_incident_dict() -> dict:
    """Build a serialized Detection incident payload."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(seconds=10)
    return {
        "incident_id": "inc-demo-1",
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


def test_adapter_builds_rca_output_from_detection_incident():
    """Detection incidents should convert into a Decision-compatible RCA payload."""
    adapter = DetectionIncidentAdapter()

    rca = adapter.adapt(sample_incident_dict())

    assert rca.root_cause == "payment-service"
    assert rca.original_severity == 0.91
    assert rca.affected_services == ["payment-service", "order-service"]
    assert rca.state_vector == [0, 0, 0, 1, 2, 0]


@pytest.mark.asyncio
async def test_integrated_pipeline_processes_detection_incident_end_to_end(tmp_path):
    """One detection incident should flow through Decision and Executor cleanly."""
    publisher = InMemoryEventPublisher()
    registry = DecisionRegistry()
    runtime = FakeDockerRuntime(containers={"payment-service": "running"})
    catalog = ServiceCatalog(
        targets={
            "payment": ServiceTarget("payment", "payment-service", "payment", False, False),
            "order": ServiceTarget("order", "order-service", "order", False, False),
        },
        aliases={
            "payment-service": "payment",
            "order-service": "order",
        },
    )

    from decision_engine.service import DecisionEngine, DecisionEngineConfig
    from remediation_executor.service import RemediationExecutor

    decision_engine = DecisionEngine(
        DecisionEngineConfig(q_table_path=tmp_path / "missing.pkl"),
        registry=registry,
        publisher=publisher,
    )
    executor = RemediationExecutor(
        catalog=catalog,
        runtime=runtime,
        registry=registry,
        publisher=publisher,
    )
    pipeline = IntegratedPipeline(
        decision_engine=decision_engine,
        executor=executor,
        registry=registry,
        publisher=publisher,
    )

    result = await pipeline.handle_incident(sample_incident_dict())

    assert result["decision"]["action"]["action_type"] == "restart"
    assert result["execution_log"]["api_status"] == "success"
    assert runtime.calls[0][0] == "restart"


@pytest.mark.asyncio
async def test_runner_executes_one_tick_from_detection_service(tmp_path):
    """Runner should forward incidents from a detection-like service."""
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

    publisher = InMemoryEventPublisher()
    registry = DecisionRegistry()
    runtime = FakeDockerRuntime(containers={"payment-service": "running"})
    catalog = ServiceCatalog(
        targets={
            "payment": ServiceTarget("payment", "payment-service", "payment", False, False),
            "order": ServiceTarget("order", "order-service", "order", False, False),
        },
        aliases={
            "payment-service": "payment",
            "order-service": "order",
        },
    )

    from decision_engine.service import DecisionEngine, DecisionEngineConfig
    from remediation_executor.service import RemediationExecutor

    runner = IntegratedPipelineRunner(
        pipeline=IntegratedPipeline(
            decision_engine=DecisionEngine(
                DecisionEngineConfig(q_table_path=tmp_path / "missing.pkl"),
                registry=registry,
                publisher=publisher,
            ),
            executor=RemediationExecutor(
                catalog=catalog,
                runtime=runtime,
                registry=registry,
                publisher=publisher,
            ),
            registry=registry,
            publisher=publisher,
        ),
        detection_service=FakeDetectionService(),
    )

    result = await runner.run_once()

    assert len(result["outcomes"]) == 1
    assert result["outcomes"][0]["execution_log"]["api_status"] == "success"
