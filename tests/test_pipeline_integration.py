"""Tests for the temporary Detection -> Decision -> Executor integration layer."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from decision_engine.events import InMemoryEventPublisher
from decision_engine.registry import DecisionRegistry
from feedback_loop.models import RecoveryMetrics
from feedback_loop.q_learning import QTableLearner
from feedback_loop.service import FeedbackLoopConfig, FeedbackLoopService
from feedback_loop.stores import DictBaselineProvider
from pipeline_integration.adapter import DetectionIncidentAdapter, IncidentAdapterConfig
from pipeline_integration.runner import IntegratedPipelineRunner
from pipeline_integration.service import IntegratedPipeline, IntegratedPipelineConfig
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


class StaticRecoveryProvider:
    def __init__(self, metrics: RecoveryMetrics) -> None:
        self.metrics = metrics

    def get_recovery_metrics(self, service: str, endpoint: str | None = None) -> RecoveryMetrics:
        return self.metrics


def build_feedback_loop(
    tmp_path: Path,
    *,
    catalog: ServiceCatalog,
    runtime: FakeDockerRuntime,
    registry: DecisionRegistry,
    publisher: InMemoryEventPublisher,
    decision_engine,
    executor,
    recovery_metrics: RecoveryMetrics,
) -> FeedbackLoopService:
    return FeedbackLoopService(
        config=FeedbackLoopConfig(enable_sleep=False),
        catalog=catalog,
        runtime=runtime,
        registry=registry,
        publisher=publisher,
        baseline_provider=DictBaselineProvider(
            {("payment-service", "/checkout"): {"error_rate_baseline": 0.008, "p95_latency_baseline_ms": 312.0}}
        ),
        recovery_provider=StaticRecoveryProvider(recovery_metrics),
        learner=QTableLearner(load_path=tmp_path / "missing.pkl", checkpoint_path=tmp_path / "checkpoint.pkl"),
        decision_engine=decision_engine,
        executor=executor,
    )


def test_adapter_builds_rca_output_from_detection_incident():
    """Fallback adapter should still emit the expected Decision-compatible RCA payload."""
    adapter = DetectionIncidentAdapter(IncidentAdapterConfig(use_full_rca=False))

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
    runtime = FakeDockerRuntime(containers={"payment-service": "running", "order-service": "running"})
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
    feedback_loop = build_feedback_loop(
        tmp_path,
        catalog=catalog,
        runtime=runtime,
        registry=registry,
        publisher=publisher,
        decision_engine=decision_engine,
        executor=executor,
        recovery_metrics=RecoveryMetrics(error_rate=0.008, p95_latency_ms=300.0, source="mock"),
    )
    pipeline = IntegratedPipeline(
        config=IntegratedPipelineConfig(feedback_sleep_enabled=False, enable_rca=False),
        decision_engine=decision_engine,
        executor=executor,
        feedback_loop=feedback_loop,
        registry=registry,
        publisher=publisher,
    )

    result = await pipeline.handle_incident(sample_incident_dict())

    assert result["decision"]["action"]["action_type"] == "restart"
    assert result["execution_log"]["api_status"] == "success"
    assert result["feedback_result"]["outcome"] == "RECOVERED"
    assert result["feedback_result"]["phase2"]["result"] == "CONFIRMED_RECOVERED"
    assert result["feedback_result"]["closure"]["outcome"] == "RECOVERED"
    assert result["cascade_feedback_result"]["outcome"] == "RECOVERED"
    assert result["cascade_feedback_result"]["closure"]["outcome"] == "RECOVERED"
    assert registry.active_count() == 0
    assert runtime.calls[0][0] == "restart"


@pytest.mark.asyncio
async def test_integrated_pipeline_runs_feedback_and_cascade_round_trip(tmp_path):
    publisher = InMemoryEventPublisher()
    registry = DecisionRegistry()
    runtime = FakeDockerRuntime(containers={"payment-service": "running", "order-service": "running"})
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
    feedback_loop = build_feedback_loop(
        tmp_path,
        catalog=catalog,
        runtime=runtime,
        registry=registry,
        publisher=publisher,
        decision_engine=decision_engine,
        executor=executor,
        recovery_metrics=RecoveryMetrics(error_rate=0.008, p95_latency_ms=300.0, source="mock"),
    )
    pipeline = IntegratedPipeline(
        config=IntegratedPipelineConfig(feedback_sleep_enabled=False, enable_rca=False),
        decision_engine=decision_engine,
        executor=executor,
        feedback_loop=feedback_loop,
        registry=registry,
        publisher=publisher,
    )

    result = await pipeline.handle_incident(sample_incident_dict())

    assert result["feedback_result"] is not None
    assert result["feedback_result"]["cascade_status"] == "EMITTED_TO_DECISION"
    assert result["feedback_result"]["cascade_incident"]["root_cause"] == "order-service"
    assert result["feedback_result"]["cascade_execution_log"]["service"] == "order-service"
    assert result["cascade_feedback_result"] is not None
    assert result["cascade_feedback_result"]["service"] == "order-service"
    assert result["cascade_feedback_result"]["closure"]["outcome"] == "RECOVERED"
    assert registry.active_count() == 0
    event_types = [event.type for event in publisher.events]
    assert "PHASE1_CONFIRMED" in event_types
    assert "PHASE2_CONFIRMED" in event_types
    assert "RL_Q_UPDATED" in event_types
    assert "CASCADE_DETECTED" in event_types
    assert event_types.count("INCIDENT_CLOSED") >= 2


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
    runtime = FakeDockerRuntime(containers={"payment-service": "running", "order-service": "running"})
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
    feedback_loop = build_feedback_loop(
        tmp_path,
        catalog=catalog,
        runtime=runtime,
        registry=registry,
        publisher=publisher,
        decision_engine=decision_engine,
        executor=executor,
        recovery_metrics=RecoveryMetrics(error_rate=0.008, p95_latency_ms=300.0, source="mock"),
    )

    runner = IntegratedPipelineRunner(
        pipeline=IntegratedPipeline(
            config=IntegratedPipelineConfig(feedback_sleep_enabled=False, enable_rca=False),
            decision_engine=decision_engine,
            executor=executor,
            feedback_loop=feedback_loop,
            registry=registry,
            publisher=publisher,
        ),
        detection_service=FakeDetectionService(),
    )

    result = await runner.run_once()

    assert len(result["outcomes"]) == 1
    assert result["outcomes"][0]["execution_log"]["api_status"] == "success"
    assert result["outcomes"][0]["feedback_result"]["outcome"] == "RECOVERED"
