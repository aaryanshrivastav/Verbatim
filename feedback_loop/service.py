"""Top-level orchestration service for Component 6: Feedback Loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Optional, Sequence

from decision_engine.events import EventPublisher, InMemoryEventPublisher
from decision_engine.models import DecisionBlockedOutput, DecisionOutput
from decision_engine.registry import DecisionRegistry
from feedback_loop.cascade import CascadeBuilder, CascadeConfig
from feedback_loop.events import (
    build_cascade_event,
    build_closure_event,
    build_effectiveness_event,
    build_phase1_event,
    build_phase2_event,
    build_rl_skipped_event,
    build_rl_updated_event,
)
from feedback_loop.models import (
    ClosureRecord,
    FeedbackRequest,
    FeedbackResult,
    Phase1Result,
    Phase2Result,
    QUpdateResult,
    RewardBreakdown,
)
from feedback_loop.prometheus import PrometheusRecoveryProvider
from feedback_loop.q_learning import QTableLearner
from feedback_loop.stores import BaselineProvider, DictBaselineProvider, DictSeverityProvider, SeverityProvider
from remediation_executor.catalog import ServiceCatalog, build_default_catalog
from remediation_executor.models import ExecutionLog, ExecutorRequest
from remediation_executor.runtime import ContainerNotFoundError, DockerRuntime, RuntimeErrorBase, SubprocessDockerRuntime
from remediation_executor.service import RemediationExecutor


@dataclass
class FeedbackLoopConfig:
    """Configuration bundle for the Feedback Loop."""

    phase1_delay_seconds: float = 2.0
    phase2_delay_seconds: float = 2.0
    restarting_grace_seconds: float = 1.0
    enable_sleep: bool = True
    default_error_rate_baseline: float = 0.05
    default_p95_latency_ms: float = 500.0
    q_table_path: str | Path = Path("decision_engine") / "artifacts" / "q_table.pkl"
    q_table_checkpoint_path: str | Path = Path("feedback_loop") / "artifacts" / "q_table_checkpoint.pkl"
    save_every_updates: int = 5
    state_slots: Sequence[str] = (
        "gateway",
        "auth",
        "catalog",
        "order",
        "payment",
        "db",
    )
    service_aliases: Mapping[str, str] = field(
        default_factory=lambda: {
            "gateway-service": "gateway",
            "gateway": "gateway",
            "auth-service": "auth",
            "auth": "auth",
            "catalog-service": "catalog",
            "catalog": "catalog",
            "order-service": "order",
            "order": "order",
            "checkoutservice": "order",
            "payment-service": "payment",
            "payment": "payment",
            "postgres": "db",
            "redis": "db",
            "orders-db": "db",
            "db": "db",
            "microservices-demo": "gateway",
        }
    )


class FeedbackLoopService:
    """Verifies remediation outcomes, updates RL state, and closes incidents."""

    def __init__(
        self,
        config: Optional[FeedbackLoopConfig] = None,
        catalog: Optional[ServiceCatalog] = None,
        runtime: Optional[DockerRuntime] = None,
        registry: Optional[DecisionRegistry] = None,
        publisher: Optional[EventPublisher] = None,
        baseline_provider: Optional[BaselineProvider] = None,
        severity_provider: Optional[SeverityProvider] = None,
        recovery_provider: Optional[PrometheusRecoveryProvider] = None,
        learner: Optional[QTableLearner] = None,
        cascade_builder: Optional[CascadeBuilder] = None,
        decision_engine=None,
        executor: Optional[RemediationExecutor] = None,
    ) -> None:
        self.config = config or FeedbackLoopConfig()
        self.catalog = catalog or build_default_catalog()
        self.runtime = runtime or SubprocessDockerRuntime()
        self.registry = registry or DecisionRegistry()
        self.publisher = publisher or InMemoryEventPublisher()
        self.baseline_provider = baseline_provider or DictBaselineProvider(
            default_error_rate=self.config.default_error_rate_baseline,
            default_p95_latency_ms=self.config.default_p95_latency_ms,
        )
        self.severity_provider = severity_provider or DictSeverityProvider()
        self.recovery_provider = recovery_provider or PrometheusRecoveryProvider()
        self.learner = learner or QTableLearner(
            load_path=self.config.q_table_path,
            checkpoint_path=self.config.q_table_checkpoint_path,
            save_every_updates=self.config.save_every_updates,
        )
        self.cascade_builder = cascade_builder or CascadeBuilder(
            CascadeConfig(
                state_slots=self.config.state_slots,
                service_aliases=dict(self.config.service_aliases),
            )
        )
        self.decision_engine = decision_engine
        self.executor = executor

    async def process(self, request: FeedbackRequest | ExecutionLog | Mapping[str, object]) -> FeedbackResult:
        """Run the full feedback loop for one execution log."""
        feedback_request = self._coerce_request(request)
        log = feedback_request.execution_log
        target = self.catalog.resolve(log.service)
        events = []

        phase1 = await self._run_phase1(log, target.container_name)
        event = build_phase1_event(log.incident_id, phase1, self._relative_seconds(log, phase1.checked_at))
        self.publisher.publish(event)
        events.append(event)

        phase2 = None
        recovery_confirmed = False
        failure_reason = f"container status {phase1.container_status}" if phase1.result != "PROVISIONALLY_RECOVERED" else None
        if phase1.result == "PROVISIONALLY_RECOVERED":
            phase2 = await self._run_phase2(feedback_request)
            event = build_phase2_event(log.incident_id, phase2, self._relative_seconds(log, phase2.checked_at))
            self.publisher.publish(event)
            events.append(event)
            recovery_confirmed = phase2.result == "CONFIRMED_RECOVERED"
            failure_reason = phase2.failure_reason

        reward, reward_breakdown = self._compute_reward(log, phase1, phase2)
        s_prime = self.severity_provider.state_vector(self.config.state_slots, self.config.service_aliases)
        q_update = self._run_q_update(log, reward, reward_breakdown, s_prime)
        event = (
            build_rl_skipped_event(log.incident_id, q_update, self._relative_seconds(log, self._latest_timestamp(phase1, phase2)))
            if q_update.skipped
            else build_rl_updated_event(log.incident_id, q_update, self._relative_seconds(log, self._latest_timestamp(phase1, phase2)))
        )
        self.publisher.publish(event)
        events.append(event)

        outcome = "RECOVERED" if recovery_confirmed else "REMEDIATION_INEFFECTIVE"
        event = build_effectiveness_event(
            log.incident_id,
            outcome,
            self._relative_seconds(log, self._latest_timestamp(phase1, phase2)),
            failure_reason,
            q_update.q_shift,
        )
        self.publisher.publish(event)
        events.append(event)

        cascade_status, cascade_incident, cascade_decision, cascade_execution_log, cascade_events = await self._handle_cascade(
            feedback_request,
            recovery_confirmed,
        )
        for cascade_event in cascade_events:
            self.publisher.publish(cascade_event)
            events.append(cascade_event)

        end_moment = self._latest_timestamp(phase1, phase2)
        closure = self._build_closure(log, outcome, cascade_status, q_update, end_moment)
        self.registry.release(log.incident_id, log.service)
        event = build_closure_event(closure)
        self.publisher.publish(event)
        events.append(event)

        return FeedbackResult(
            incident_id=log.incident_id,
            service=log.service,
            outcome=outcome,
            phase1=phase1,
            phase2=phase2,
            recovery_confirmed=recovery_confirmed,
            reward=reward,
            reward_breakdown=reward_breakdown,
            q_update=q_update,
            cascade_status=cascade_status,
            cascade_incident=cascade_incident,
            cascade_decision=cascade_decision,
            cascade_execution_log=cascade_execution_log,
            closure=closure,
            events=events,
        )

    async def _run_phase1(self, log: ExecutionLog, container_name: str) -> Phase1Result:
        await self._sleep_until(log.execution_end + timedelta(seconds=self.config.phase1_delay_seconds))
        try:
            status = self.runtime.inspect_container(container_name).status
        except (ContainerNotFoundError, RuntimeErrorBase):
            return Phase1Result(result="CONTAINER_FAILED", container_status="missing", checked_at=self._utc_now())

        if status == "restarting":
            await self._sleep_for(self.config.restarting_grace_seconds)
            try:
                status = self.runtime.inspect_container(container_name).status
            except (ContainerNotFoundError, RuntimeErrorBase):
                status = "missing"

        result = "PROVISIONALLY_RECOVERED" if status == "running" else "CONTAINER_FAILED"
        return Phase1Result(result=result, container_status=status, checked_at=self._utc_now())

    async def _run_phase2(self, request: FeedbackRequest) -> Phase2Result:
        log = request.execution_log
        await self._sleep_until(
            log.execution_end + timedelta(seconds=self.config.phase1_delay_seconds + self.config.phase2_delay_seconds)
        )

        baseline = self.baseline_provider.get_baseline(log.service, request.endpoint)
        metrics = self.recovery_provider.get_recovery_metrics(log.service, request.endpoint)
        checked_at = self._utc_now()

        threshold_error = round(baseline.error_rate_baseline * 1.2, 6)
        threshold_latency = round(baseline.p95_latency_baseline_ms * 1.5, 3)

        if metrics.error_rate is None or metrics.p95_latency_ms is None:
            return Phase2Result(
                result="METRICS_UNKNOWN",
                checked_at=checked_at,
                current_error_rate=metrics.error_rate,
                threshold_error_rate=threshold_error,
                current_p95_latency_ms=metrics.p95_latency_ms,
                threshold_p95_latency_ms=threshold_latency,
                failure_reason=", ".join(metrics.issues) if metrics.issues else "metrics unavailable",
                baseline_source=baseline.source,
                metrics_source=metrics.source,
            )

        error_ok = metrics.error_rate < threshold_error
        latency_ok = metrics.p95_latency_ms < threshold_latency
        if error_ok and latency_ok:
            return Phase2Result(
                result="CONFIRMED_RECOVERED",
                checked_at=checked_at,
                current_error_rate=round(metrics.error_rate, 6),
                threshold_error_rate=threshold_error,
                current_p95_latency_ms=round(metrics.p95_latency_ms, 3),
                threshold_p95_latency_ms=threshold_latency,
                baseline_source=baseline.source,
                metrics_source=metrics.source,
            )

        reasons = []
        if not error_ok:
            reasons.append(f"error_rate still {metrics.error_rate:.4f}, threshold {threshold_error:.4f}")
        if not latency_ok:
            reasons.append(f"p95 latency still {metrics.p95_latency_ms:.1f}ms, threshold {threshold_latency:.1f}ms")
        return Phase2Result(
            result="METRICS_DEGRADED",
            checked_at=checked_at,
            current_error_rate=round(metrics.error_rate, 6),
            threshold_error_rate=threshold_error,
            current_p95_latency_ms=round(metrics.p95_latency_ms, 3),
            threshold_p95_latency_ms=threshold_latency,
            failure_reason="; ".join(reasons),
            baseline_source=baseline.source,
            metrics_source=metrics.source,
        )

    def _compute_reward(
        self,
        log: ExecutionLog,
        phase1: Phase1Result,
        phase2: Optional[Phase2Result],
    ) -> tuple[float, RewardBreakdown]:
        if log.api_status != "success":
            base = -1.0
        elif phase1.result != "PROVISIONALLY_RECOVERED":
            base = -0.5
        elif phase2 is None:
            base = -0.5
        elif phase2.result == "CONFIRMED_RECOVERED":
            base = 1.5
        elif phase2.result == "METRICS_UNKNOWN":
            base = -0.3
        else:
            base = -0.5

        recovery_time_seconds = max(0.0, (self._latest_timestamp(phase1, phase2) - log.execution_end).total_seconds())
        severity_bonus = log.original_severity * 0.5
        time_penalty = -0.02 * recovery_time_seconds
        fallback_penalty = -0.3 if log.fallback_used else 0.0
        reward = max(-2.0, min(2.0, base + severity_bonus + time_penalty + fallback_penalty))

        return round(reward, 4), RewardBreakdown(
            base=round(base, 4),
            severity_bonus=round(severity_bonus, 4),
            time_penalty=round(time_penalty, 4),
            fallback_penalty=round(fallback_penalty, 4),
        )

    def _run_q_update(
        self,
        log: ExecutionLog,
        reward: float,
        reward_breakdown: RewardBreakdown,
        s_prime: Sequence[int],
    ) -> QUpdateResult:
        if log.safety_overridden:
            return QUpdateResult(
                skipped=True,
                reason="safety_override",
                episodes_live=self.learner.episodes_live,
                q_table_size=self.learner.q_table_size,
            )

        update = self.learner.update(log.state_vector, log.action_id, reward, s_prime)
        return QUpdateResult(
            skipped=False,
            state=log.state_vector,
            action_id=log.action_id,
            action_type=log.action_type,
            reward=reward,
            reward_breakdown=reward_breakdown,
            q_before=float(update["q_before"]),
            q_after=float(update["q_after"]),
            q_shift=float(update["q_shift"]),
            all_q_values_updated=dict(update["all_q_values_updated"]),
            episodes_live=int(update["episodes_live"]),
            q_table_size=int(update["q_table_size"]),
            s_prime=list(s_prime),
            checkpoint_saved=bool(update["checkpoint_saved"]),
        )

    async def _handle_cascade(
        self,
        request: FeedbackRequest,
        recovery_confirmed: bool,
    ) -> tuple[str, Optional[dict], Optional[dict], Optional[dict], list]:
        log = request.execution_log
        events = []
        if not log.cascade_secondary_pending:
            return "NOT_REQUESTED", None, None, None, events

        if not recovery_confirmed:
            events.append(
                build_cascade_event(
                    log.incident_id,
                    "CASCADE_SUPPRESSED",
                    self._relative_seconds(log, self._utc_now()),
                    {"message": "primary remediation failed"},
                )
            )
            return "SUPPRESSED", None, None, None, events

        if not request.affected_services:
            events.append(
                build_cascade_event(
                    log.incident_id,
                    "CASCADE_SUPPRESSED",
                    self._relative_seconds(log, self._utc_now()),
                    {"message": "cascade context unavailable"},
                )
            )
            return "SUPPRESSED_NO_CONTEXT", None, None, None, events

        cascade_incident = self.cascade_builder.build(request, self.severity_provider)
        if cascade_incident is None:
            events.append(
                build_cascade_event(
                    log.incident_id,
                    "CASCADE_SELF_HEALED",
                    self._relative_seconds(log, self._utc_now()),
                    {"message": "secondary services recovered after primary fix"},
                )
            )
            return "SELF_HEALED", None, None, None, events

        events.append(
            build_cascade_event(
                cascade_incident.incident_id,
                "CASCADE_DETECTED",
                self._relative_seconds(log, self._utc_now()),
                {
                    "secondary_service": cascade_incident.root_cause,
                    "severity": cascade_incident.original_severity,
                    "action": "emitting to Decision",
                },
            )
        )

        cascade_decision_payload = None
        cascade_execution_payload = None
        if self.decision_engine is not None:
            decision = self.decision_engine.process(cascade_incident)
            cascade_decision_payload = decision.model_dump(mode="json")
            if isinstance(decision, DecisionOutput) and self.executor is not None:
                executor_request = ExecutorRequest.from_decision_output(
                    decision,
                    incident_started_at=cascade_incident.incident_started_at,
                    detection_timestamp=cascade_incident.incident_started_at,
                )
                cascade_execution = await self.executor.execute(executor_request)
                cascade_execution_payload = cascade_execution.model_dump(mode="json")
            elif isinstance(decision, DecisionBlockedOutput):
                return "DECISION_BLOCKED", cascade_incident.model_dump(mode="json"), cascade_decision_payload, None, events

        return "EMITTED_TO_DECISION", cascade_incident.model_dump(mode="json"), cascade_decision_payload, cascade_execution_payload, events

    def _build_closure(
        self,
        log: ExecutionLog,
        outcome: str,
        cascade_status: str,
        q_update: QUpdateResult,
        end_time: datetime,
    ) -> ClosureRecord:
        end_to_end_latency = self._relative_seconds(log, end_time)
        return ClosureRecord(
            incident_id=log.incident_id,
            outcome=outcome,
            cascade_status=cascade_status,
            timeline={
                "action_fired": log.pipeline_elapsed_s,
                "phase1_confirmed": self._relative_seconds(log, end_time if q_update.reason == "phase1_only" else end_time),
                "phase2_confirmed": end_to_end_latency,
                "primary_closed": end_to_end_latency,
            },
            end_to_end_latency_s=end_to_end_latency,
            rl_q_shift=q_update.q_shift,
            episodes_trained_live=q_update.episodes_live,
            bellman_update={
                "alpha": self.learner.alpha,
                "gamma": self.learner.gamma,
                "reward": q_update.reward,
                "q_before": q_update.q_before,
                "q_after": q_update.q_after,
            },
        )

    @staticmethod
    def _coerce_request(request: FeedbackRequest | ExecutionLog | Mapping[str, object]) -> FeedbackRequest:
        if isinstance(request, FeedbackRequest):
            return request
        if isinstance(request, ExecutionLog):
            return FeedbackRequest(execution_log=request)
        return FeedbackRequest.model_validate(request)

    async def _sleep_until(self, target: datetime) -> None:
        if not self.config.enable_sleep:
            return
        remaining = (target - self._utc_now()).total_seconds()
        if remaining > 0:
            await asyncio.sleep(remaining)

    async def _sleep_for(self, seconds: float) -> None:
        if self.config.enable_sleep and seconds > 0:
            await asyncio.sleep(seconds)

    @staticmethod
    def _relative_seconds(log: ExecutionLog, when: datetime) -> Optional[float]:
        if log.detection_timestamp is None:
            return None
        return round((when - log.detection_timestamp).total_seconds(), 2)

    @staticmethod
    def _latest_timestamp(phase1: Phase1Result, phase2: Optional[Phase2Result]) -> datetime:
        return phase2.checked_at if phase2 is not None else phase1.checked_at

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)
