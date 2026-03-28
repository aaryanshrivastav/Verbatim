"""Top-level orchestration service for Component 4: Decision Engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from pydantic import ValidationError

from decision_engine.events import (
    EventPublisher,
    InMemoryEventPublisher,
    build_blocked_event,
    build_decision_event,
    build_rl_event,
    build_skipped_event,
)
from decision_engine.models import (
    ConfidenceLog,
    DecisionAction,
    DecisionBlockedOutput,
    DecisionOutput,
    DecisionReasoning,
    DecisionSkippedOutput,
    RCAOutput,
)
from decision_engine.policy import PolicyConfig, QTablePolicy
from decision_engine.registry import DecisionRegistry
from decision_engine.safety_gate import SafetyGate


@dataclass
class DecisionEngineConfig:
    """Configuration bundle for the runtime Decision Engine."""

    q_table_path: Optional[str | Path] = None
    cooldown_seconds: int = 60
    max_in_flight: int = 2
    snapshot_path: Optional[str | Path] = None
    scalable_services: Optional[set[str]] = None
    mask_scale_down: bool = True
    low_confidence_threshold: float = 0.4
    medium_confidence_threshold: float = 0.7
    state_size: int = 6
    db_services: set[str] = field(default_factory=set)


class DecisionEngine:
    """Coordinates validation, safety checks, RL inference, and event output."""

    def __init__(
        self,
        config: Optional[DecisionEngineConfig] = None,
        registry: Optional[DecisionRegistry] = None,
        policy: Optional[QTablePolicy] = None,
        publisher: Optional[EventPublisher] = None,
    ) -> None:
        self.config = config or DecisionEngineConfig()
        self.registry = registry or DecisionRegistry(
            cooldown_seconds=self.config.cooldown_seconds,
            max_in_flight=self.config.max_in_flight,
            snapshot_path=self.config.snapshot_path,
        )
        self.registry.load_snapshot()
        self.policy = policy or QTablePolicy(
            PolicyConfig(
                q_table_path=self.config.q_table_path,
                state_size=self.config.state_size,
                scalable_services=self.config.scalable_services,
                mask_scale_down=self.config.mask_scale_down,
                db_services=set(self.config.db_services) or {"postgres", "redis", "mysql", "mongodb", "orders-db", "db"},
            )
        )
        self.publisher = publisher or InMemoryEventPublisher()
        self.safety_gate = SafetyGate(self.registry)

    def process(
        self,
        rca_input: Union[RCAOutput, dict],
    ) -> Union[DecisionOutput, DecisionBlockedOutput, DecisionSkippedOutput]:
        """Transform RCA output into a safe remediation decision."""
        start = time.perf_counter()
        now = self._utc_now()

        try:
            rca_output = (
                rca_input
                if isinstance(rca_input, RCAOutput)
                else RCAOutput.model_validate(rca_input)
            )
        except ValidationError as exc:
            result = DecisionSkippedOutput(
                incident_id=rca_input.get("incident_id") if isinstance(rca_input, dict) else None,
                decision_timestamp=now,
                decision_latency_ms=self._latency_ms(start),
                reason="invalid_rca_input",
                errors=[error["msg"] for error in exc.errors()],
            )
            self.publisher.publish(build_skipped_event(result))
            return result

        if all(value == 0 for value in rca_output.state_vector) and rca_output.original_severity < 0.3:
            result = DecisionSkippedOutput(
                incident_id=rca_output.incident_id,
                decision_timestamp=now,
                decision_latency_ms=self._latency_ms(start),
                reason="non_actionable_state_vector",
                errors=["state_vector is all zeros while severity is below action threshold"],
            )
            self.publisher.publish(build_skipped_event(result))
            return result

        safety_result = self.safety_gate.evaluate(rca_output, now)
        if safety_result.blocked:
            result = DecisionBlockedOutput(
                incident_id=rca_output.incident_id,
                decision_timestamp=now,
                decision_latency_ms=self._latency_ms(start),
                root_cause=rca_output.root_cause,
                reason=safety_result.reason or "blocked",
                safety_checks=safety_result.checks,
            )
            self.publisher.publish(
                build_blocked_event(result, self._relative_timestamp(rca_output, now))
            )
            return result

        selection = self.policy.select_action(
            state_vector=rca_output.state_vector,
            service=rca_output.root_cause,
        )
        confidence_log, rollback_watch = self._build_confidence(rca_output.confidence.value)
        self.registry.reserve(rca_output.incident_id, rca_output.root_cause)

        result = DecisionOutput(
            incident_id=rca_output.incident_id,
            decision_timestamp=now,
            decision_latency_ms=self._latency_ms(start),
            action=DecisionAction(
                service=rca_output.root_cause,
                action_type=selection.action_type,
                action_id=selection.action_id,
                q_value=selection.q_value,
                all_q_values=selection.all_q_values,
            ),
            confidence_log=confidence_log,
            safety_checks=safety_result.checks,
            state_vector=rca_output.state_vector,
            original_severity=rca_output.original_severity,
            rollback_watch=rollback_watch,
            cascade_secondary_pending=len(rca_output.affected_services) >= 2,
            reasoning=DecisionReasoning(
                policy_source=selection.policy_source,
                selection_mode=selection.selection_mode,
                q_table_hit=selection.q_table_hit,
                masked_actions=selection.masked_actions,
                defaulted=selection.defaulted,
            ),
        )

        relative_timestamp = self._relative_timestamp(rca_output, now)
        self.publisher.publish(build_decision_event(result, relative_timestamp))
        self.publisher.publish(build_rl_event(result, relative_timestamp))
        return result

    def mark_action_fired(self, service: str, when: Optional[datetime] = None) -> None:
        """Start cooldown after the executor confirms action dispatch."""
        self.registry.mark_action_fired(service, when or self._utc_now())

    def release_incident(self, incident_id: str, service: str) -> None:
        """Release in-flight slots once Feedback Loop closes the incident."""
        self.registry.release(incident_id, service)

    @staticmethod
    def _build_confidence(confidence_value: float) -> tuple[ConfidenceLog, bool]:
        """Map RCA confidence to dashboard tier and rollback policy."""
        if confidence_value >= 0.7:
            return (
                ConfidenceLog(
                    rca_confidence=confidence_value,
                    tier="HIGH",
                    dashboard_color="green",
                ),
                False,
            )
        if confidence_value >= 0.4:
            return (
                ConfidenceLog(
                    rca_confidence=confidence_value,
                    tier="MEDIUM",
                    dashboard_color="amber",
                ),
                False,
            )
        return (
            ConfidenceLog(
                rca_confidence=confidence_value,
                tier="LOW",
                dashboard_color="red",
            ),
            True,
        )

    @staticmethod
    def _latency_ms(start: float) -> int:
        """Compute elapsed decision latency in milliseconds."""
        return int(round((time.perf_counter() - start) * 1000))

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _relative_timestamp(rca_output: RCAOutput, now: datetime) -> Optional[float]:
        """Return seconds since incident start when available."""
        if rca_output.incident_started_at is None:
            return None
        return round((now - rca_output.incident_started_at).total_seconds(), 2)
