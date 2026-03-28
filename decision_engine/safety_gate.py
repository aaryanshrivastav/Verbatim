"""Safety gate for the Decision Engine."""

from __future__ import annotations

from datetime import datetime

from decision_engine.models import RCAOutput, SafetyChecks, SafetyEvaluation
from decision_engine.registry import DecisionRegistry


class SafetyGate:
    """Runs safety checks in constant time before RL inference."""

    def __init__(self, registry: DecisionRegistry) -> None:
        self.registry = registry

    def evaluate(self, rca_output: RCAOutput, now: datetime) -> SafetyEvaluation:
        """Return pass/fail plus per-check visibility for dashboard rendering."""
        cooldown_remaining = self.registry.cooldown_remaining(rca_output.root_cause, now)
        checks = SafetyChecks(
            cooldown_passed=cooldown_remaining <= 0,
            global_lock_passed=self.registry.active_count() < self.registry.max_in_flight,
            dedup_passed=not self.registry.is_incident_active(rca_output.incident_id),
            service_passed=not self.registry.is_service_active(rca_output.root_cause),
        )

        if not checks.cooldown_passed:
            return SafetyEvaluation(
                blocked=True,
                reason=f"cooldown: {cooldown_remaining:.1f}s remaining",
                checks=checks,
            )
        if not checks.global_lock_passed:
            return SafetyEvaluation(
                blocked=True,
                reason="global lock: 2 remediations already in flight",
                checks=checks,
            )
        if not checks.dedup_passed:
            return SafetyEvaluation(
                blocked=True,
                reason="duplicate: incident already being remediated",
                checks=checks,
            )
        if not checks.service_passed:
            return SafetyEvaluation(
                blocked=True,
                reason="service already being remediated",
                checks=checks,
            )

        return SafetyEvaluation(blocked=False, checks=checks)
