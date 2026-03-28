"""Unit tests for the Decision Engine safety gate and registry."""

from datetime import datetime, timedelta, timezone

from decision_engine.models import RCAConfidence, RCAOutput
from decision_engine.registry import DecisionRegistry
from decision_engine.safety_gate import SafetyGate


def build_rca(incident_id: str = "inc-1", root_cause: str = "payment") -> RCAOutput:
    """Return a minimal valid RCA payload for safety testing."""
    return RCAOutput(
        incident_id=incident_id,
        root_cause=root_cause,
        confidence=RCAConfidence(value=0.9, bucket="high"),
        state_vector=[0, 0, 1, 0, 2, 1],
        original_severity=0.91,
        affected_services=["checkout", "frontend"],
    )


def test_safety_gate_blocks_cooldown():
    """A recent remediation should block another action on the same service."""
    registry = DecisionRegistry(cooldown_seconds=60)
    gate = SafetyGate(registry)
    now = datetime.now(timezone.utc)
    registry.mark_action_fired("payment", now - timedelta(seconds=20))

    result = gate.evaluate(build_rca(), now)

    assert result.blocked is True
    assert result.checks.cooldown_passed is False
    assert "cooldown" in result.reason


def test_safety_gate_blocks_duplicate_incident():
    """The same incident ID cannot be remediated twice at once."""
    registry = DecisionRegistry()
    gate = SafetyGate(registry)
    now = datetime.now(timezone.utc)
    registry.reserve("inc-1", "payment")

    result = gate.evaluate(build_rca(), now)

    assert result.blocked is True
    assert result.checks.dedup_passed is False


def test_safety_gate_blocks_service_already_in_flight():
    """A service-level in-flight lock prevents repeated actions under new IDs."""
    registry = DecisionRegistry()
    gate = SafetyGate(registry)
    now = datetime.now(timezone.utc)
    registry.reserve("inc-older", "payment")

    result = gate.evaluate(build_rca(incident_id="inc-new"), now)

    assert result.blocked is True
    assert result.checks.service_passed is False
