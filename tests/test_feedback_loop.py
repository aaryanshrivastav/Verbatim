from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from decision_engine.events import InMemoryEventPublisher
from decision_engine.models import ConfidenceLog, DecisionAction, DecisionOutput, DecisionReasoning, SafetyChecks
from decision_engine.registry import DecisionRegistry
from feedback_loop.models import FeedbackRequest, RecoveryMetrics
from feedback_loop.q_learning import QTableLearner
from feedback_loop.service import FeedbackLoopConfig, FeedbackLoopService
from feedback_loop.stores import DictBaselineProvider, DictSeverityProvider
from remediation_executor.models import ExecutionLog
from remediation_executor.runtime import FakeDockerRuntime


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sample_execution_log(**overrides) -> ExecutionLog:
    now = utc_now()
    payload = {
        "incident_id": "inc-feedback-1",
        "service": "payment-service",
        "container_name": "payment-service",
        "compose_service_name": "payment",
        "action_type": "restart",
        "action_id": 0,
        "requested_action_type": "restart",
        "requested_action_id": 0,
        "source": "rl_agent",
        "q_value": 1.23,
        "all_q_values": {"restart": 1.23, "scale_up": 0.84, "scale_down": -0.12, "force_kill": 0.61},
        "state_vector": [0, 0, 0, 1, 2, 0],
        "original_severity": 0.91,
        "confidence_bucket": "high",
        "execution_start": now - timedelta(seconds=0.3),
        "execution_end": now,
        "api_latency_ms": 250,
        "pipeline_elapsed_s": 9.43,
        "api_status": "success",
        "docker_response": "container restarting",
        "rollback_watch": False,
        "cascade_secondary_pending": False,
        "fallback_used": False,
        "safety_overridden": False,
        "detection_timestamp": now - timedelta(seconds=9.43),
    }
    payload.update(overrides)
    return ExecutionLog.model_validate(payload)


class StaticRecoveryProvider:
    def __init__(self, metrics: RecoveryMetrics) -> None:
        self.metrics = metrics

    def get_recovery_metrics(self, service: str, endpoint: str | None = None) -> RecoveryMetrics:
        return self.metrics


class StubDecisionEngine:
    def process(self, rca_output):
        now = utc_now()
        return DecisionOutput(
            incident_id=rca_output.incident_id,
            decision_timestamp=now,
            decision_latency_ms=15,
            action=DecisionAction(
                service=rca_output.root_cause,
                action_type="restart",
                action_id=0,
                q_value=0.0,
                all_q_values={"restart": 0.0, "scale_up": 0.0, "scale_down": 0.0, "force_kill": 0.0},
            ),
            confidence_log=ConfidenceLog(rca_confidence=0.6, tier="MEDIUM", dashboard_color="amber"),
            safety_checks=SafetyChecks(cooldown_passed=True, global_lock_passed=True, dedup_passed=True),
            state_vector=rca_output.state_vector,
            original_severity=rca_output.original_severity,
            rollback_watch=False,
            cascade_secondary_pending=False,
            reasoning=DecisionReasoning(
                policy_source="q_table",
                selection_mode="argmax",
                q_table_hit=False,
                masked_actions=[],
                defaulted=True,
            ),
        )


class StubExecutor:
    def __init__(self) -> None:
        self.calls = []

    async def execute(self, request):
        self.calls.append(request)
        return sample_execution_log(
            incident_id=request.incident_id,
            service=request.service,
            container_name="order-service",
            compose_service_name="order",
        )


@pytest.mark.asyncio
async def test_feedback_loop_happy_path_releases_registry_and_updates_qtable(tmp_path: Path):
    publisher = InMemoryEventPublisher()
    registry = DecisionRegistry()
    registry.reserve("inc-feedback-1", "payment-service")
    service = FeedbackLoopService(
        config=FeedbackLoopConfig(enable_sleep=False),
        runtime=FakeDockerRuntime(containers={"verbatim-payment-1": "running"}),
        registry=registry,
        publisher=publisher,
        baseline_provider=DictBaselineProvider(
            {("payment-service", "/checkout"): {"error_rate_baseline": 0.008, "p95_latency_baseline_ms": 312.0, "source": "baseline-store"}}
        ),
        severity_provider=DictSeverityProvider({"payment-service": 0.1, "order-service": 0.0}),
        recovery_provider=StaticRecoveryProvider(RecoveryMetrics(error_rate=0.008, p95_latency_ms=300.0, source="mock")),
        learner=QTableLearner(load_path=tmp_path / "missing.pkl", checkpoint_path=tmp_path / "checkpoint.pkl"),
    )

    result = await service.process(
        FeedbackRequest(
            execution_log=sample_execution_log(),
            endpoint="/checkout",
            affected_services=["payment-service", "order-service"],
        )
    )

    assert result.outcome == "RECOVERED"
    assert result.phase1.result == "PROVISIONALLY_RECOVERED"
    assert result.phase2 is not None and result.phase2.result == "CONFIRMED_RECOVERED"
    assert result.q_update.skipped is False
    assert result.q_update.q_after is not None
    assert registry.active_count() == 0
    event_types = [event.type for event in publisher.events]
    assert "PHASE1_CONFIRMED" in event_types
    assert "PHASE2_CONFIRMED" in event_types
    assert "RL_Q_UPDATED" in event_types
    assert "INCIDENT_CLOSED" in event_types


@pytest.mark.asyncio
async def test_feedback_loop_failure_path_suppresses_cascade_and_learns_negative_reward(tmp_path: Path):
    publisher = InMemoryEventPublisher()
    registry = DecisionRegistry()
    registry.reserve("inc-feedback-1", "payment-service")
    service = FeedbackLoopService(
        config=FeedbackLoopConfig(enable_sleep=False),
        runtime=FakeDockerRuntime(containers={"verbatim-payment-1": "running"}),
        registry=registry,
        publisher=publisher,
        baseline_provider=DictBaselineProvider(
            {("payment-service", "/checkout"): {"error_rate_baseline": 0.008, "p95_latency_baseline_ms": 312.0}}
        ),
        severity_provider=DictSeverityProvider({"payment-service": 0.9, "order-service": 0.7}),
        recovery_provider=StaticRecoveryProvider(RecoveryMetrics(error_rate=0.089, p95_latency_ms=1047.0, source="mock")),
        learner=QTableLearner(load_path=tmp_path / "missing.pkl", checkpoint_path=tmp_path / "checkpoint.pkl"),
    )

    result = await service.process(
        FeedbackRequest(
            execution_log=sample_execution_log(cascade_secondary_pending=True),
            endpoint="/checkout",
            affected_services=["payment-service", "order-service"],
        )
    )

    assert result.outcome == "REMEDIATION_INEFFECTIVE"
    assert result.phase2 is not None and result.phase2.result == "METRICS_DEGRADED"
    assert result.q_update.q_shift is not None and result.q_update.q_shift < 0
    assert result.cascade_status == "SUPPRESSED"
    assert registry.active_count() == 0
    event_types = [event.type for event in publisher.events]
    assert "REMEDIATION_INEFFECTIVE" in event_types
    assert "CASCADE_SUPPRESSED" in event_types


@pytest.mark.asyncio
async def test_feedback_loop_skips_q_update_when_safety_overridden(tmp_path: Path):
    publisher = InMemoryEventPublisher()
    registry = DecisionRegistry()
    registry.reserve("inc-feedback-1", "payment-service")
    service = FeedbackLoopService(
        config=FeedbackLoopConfig(enable_sleep=False),
        runtime=FakeDockerRuntime(containers={"verbatim-payment-1": "running"}),
        registry=registry,
        publisher=publisher,
        baseline_provider=DictBaselineProvider(
            {("payment-service", "/checkout"): {"error_rate_baseline": 0.008, "p95_latency_baseline_ms": 312.0}}
        ),
        severity_provider=DictSeverityProvider({"payment-service": 0.0}),
        recovery_provider=StaticRecoveryProvider(RecoveryMetrics(error_rate=0.008, p95_latency_ms=300.0, source="mock")),
        learner=QTableLearner(load_path=tmp_path / "missing.pkl", checkpoint_path=tmp_path / "checkpoint.pkl"),
    )

    result = await service.process(
        FeedbackRequest(
            execution_log=sample_execution_log(safety_overridden=True),
            endpoint="/checkout",
        )
    )

    assert result.q_update.skipped is True
    assert result.q_update.reason == "safety_override"
    assert "RL_UPDATE_SKIPPED" in [event.type for event in publisher.events]
    assert registry.active_count() == 0


@pytest.mark.asyncio
async def test_feedback_loop_marks_metrics_unknown_on_missing_metrics(tmp_path: Path):
    publisher = InMemoryEventPublisher()
    registry = DecisionRegistry()
    registry.reserve("inc-feedback-1", "payment-service")
    service = FeedbackLoopService(
        config=FeedbackLoopConfig(enable_sleep=False),
        runtime=FakeDockerRuntime(containers={"verbatim-payment-1": "running"}),
        registry=registry,
        publisher=publisher,
        baseline_provider=DictBaselineProvider(
            {("payment-service", "/checkout"): {"error_rate_baseline": 0.008, "p95_latency_baseline_ms": 312.0}}
        ),
        severity_provider=DictSeverityProvider({"payment-service": 0.2}),
        recovery_provider=StaticRecoveryProvider(
            RecoveryMetrics(error_rate=None, p95_latency_ms=None, source="mock", issues=["latency_unknown", "error_rate_unknown"])
        ),
        learner=QTableLearner(load_path=tmp_path / "missing.pkl", checkpoint_path=tmp_path / "checkpoint.pkl"),
    )

    result = await service.process(FeedbackRequest(execution_log=sample_execution_log(), endpoint="/checkout"))

    assert result.phase2 is not None and result.phase2.result == "METRICS_UNKNOWN"
    assert result.outcome == "REMEDIATION_INEFFECTIVE"
    assert "PHASE2_SKIPPED" in [event.type for event in publisher.events]


@pytest.mark.asyncio
async def test_feedback_loop_emits_cascade_to_decision_and_executor(tmp_path: Path):
    publisher = InMemoryEventPublisher()
    registry = DecisionRegistry()
    registry.reserve("inc-feedback-1", "payment-service")
    stub_executor = StubExecutor()
    service = FeedbackLoopService(
        config=FeedbackLoopConfig(enable_sleep=False),
        runtime=FakeDockerRuntime(containers={"verbatim-payment-1": "running"}),
        registry=registry,
        publisher=publisher,
        baseline_provider=DictBaselineProvider(
            {("payment-service", "/checkout"): {"error_rate_baseline": 0.008, "p95_latency_baseline_ms": 312.0}}
        ),
        severity_provider=DictSeverityProvider({"payment-service": 0.0, "order-service": 0.7}),
        recovery_provider=StaticRecoveryProvider(RecoveryMetrics(error_rate=0.008, p95_latency_ms=300.0, source="mock")),
        learner=QTableLearner(load_path=tmp_path / "missing.pkl", checkpoint_path=tmp_path / "checkpoint.pkl"),
        decision_engine=StubDecisionEngine(),
        executor=stub_executor,
    )

    result = await service.process(
        FeedbackRequest(
            execution_log=sample_execution_log(cascade_secondary_pending=True),
            endpoint="/checkout",
            affected_services=["payment-service", "order-service"],
        )
    )

    assert result.outcome == "RECOVERED"
    assert result.cascade_status == "EMITTED_TO_DECISION"
    assert result.cascade_incident is not None
    assert result.cascade_incident["root_cause"] == "order-service"
    assert result.cascade_decision is not None
    assert result.cascade_execution_log is not None
    assert len(stub_executor.calls) == 1
    assert "CASCADE_DETECTED" in [event.type for event in publisher.events]
