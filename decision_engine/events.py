"""Dashboard event publisher utilities for the Decision Engine."""

from __future__ import annotations

import asyncio
from typing import List, Optional, Protocol

from decision_engine.models import (
    DashboardEvent,
    DecisionBlockedOutput,
    DecisionOutput,
    DecisionSkippedOutput,
)


class EventPublisher(Protocol):
    """Publishing contract used by Decision Engine runtime code."""

    def publish(self, event: DashboardEvent) -> None:
        """Publish a dashboard event."""


class InMemoryEventPublisher:
    """Simple publisher for tests and local development."""

    def __init__(self) -> None:
        self.events: List[DashboardEvent] = []

    def publish(self, event: DashboardEvent) -> None:
        self.events.append(event)


class AsyncQueueEventPublisher:
    """Queue-backed publisher that fits the planned FastAPI event bus."""

    def __init__(self, queue: "asyncio.Queue[DashboardEvent]") -> None:
        self.queue = queue

    def publish(self, event: DashboardEvent) -> None:
        self.queue.put_nowait(event)


def build_decision_event(
    decision: DecisionOutput,
    timestamp_relative: Optional[float],
) -> DashboardEvent:
    """Build the incident-timeline event for a successful decision."""
    return DashboardEvent(
        stream="incidents",
        type="DECISION_MADE",
        incident_id=decision.incident_id,
        timestamp_relative=timestamp_relative,
        data={
            "action": decision.action.action_type,
            "service": decision.action.service,
            "q_value": decision.action.q_value,
            "confidence": decision.confidence_log.tier,
            "color": decision.confidence_log.dashboard_color,
            "rl_state": decision.state_vector,
            "decision_latency_ms": decision.decision_latency_ms,
            "rollback_watch": decision.rollback_watch,
        },
    )


def build_rl_event(
    decision: DecisionOutput,
    timestamp_relative: Optional[float],
) -> DashboardEvent:
    """Build the RL widget update event for the chosen action."""
    return DashboardEvent(
        stream="rl",
        type="RL_DECISION",
        incident_id=decision.incident_id,
        timestamp_relative=timestamp_relative,
        data={
            "state": decision.state_vector,
            "q_values": decision.action.all_q_values,
            "chosen_action": decision.action.action_type,
            "chosen_q": decision.action.q_value,
            "q_table_hit": decision.reasoning.q_table_hit,
            "defaulted": decision.reasoning.defaulted,
            "masked_actions": decision.reasoning.masked_actions,
        },
    )


def build_blocked_event(
    blocked: DecisionBlockedOutput,
    timestamp_relative: Optional[float],
) -> DashboardEvent:
    """Build the incident-timeline event for a safety-blocked decision."""
    return DashboardEvent(
        stream="incidents",
        type="DECISION_BLOCKED",
        incident_id=blocked.incident_id,
        timestamp_relative=timestamp_relative,
        data={
            "reason": blocked.reason,
            "service": blocked.root_cause,
            "decision_latency_ms": blocked.decision_latency_ms,
        },
    )


def build_skipped_event(skipped: DecisionSkippedOutput) -> DashboardEvent:
    """Build an event for invalid or non-actionable decision inputs."""
    return DashboardEvent(
        stream="incidents",
        type="DECISION_SKIPPED",
        incident_id=skipped.incident_id,
        data={
            "reason": skipped.reason,
            "errors": skipped.errors,
            "decision_latency_ms": skipped.decision_latency_ms,
        },
    )
