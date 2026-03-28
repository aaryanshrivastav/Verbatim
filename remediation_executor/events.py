"""SSE event builders for the Remediation Executor."""

from __future__ import annotations

from typing import Optional

from decision_engine.models import DashboardEvent
from remediation_executor.models import ExecutionLog, ExecutorRequest


def build_action_fired_event(log: ExecutionLog, timestamp_relative: Optional[float]) -> DashboardEvent:
    """Build the timeline event for a successful Docker action."""
    return DashboardEvent(
        stream="incidents",
        type="ACTION_FIRED",
        incident_id=log.incident_id,
        timestamp_relative=timestamp_relative,
        data={
            "service": log.service,
            "action": f"{log.action_type} {log.container_name or log.compose_service_name}",
            "api_latency_ms": log.api_latency_ms,
            "pipeline_elapsed_s": log.pipeline_elapsed_s,
            "q_value": log.q_value,
            "fallback_used": log.fallback_used,
        },
    )


def build_execution_failed_event(log: ExecutionLog, timestamp_relative: Optional[float]) -> DashboardEvent:
    """Build the timeline event for a failed executor action."""
    return DashboardEvent(
        stream="incidents",
        type="EXECUTION_FAILED",
        incident_id=log.incident_id,
        timestamp_relative=timestamp_relative,
        data={
            "service": log.service,
            "action": log.action_type,
            "reason": log.docker_response,
            "pipeline_elapsed_s": log.pipeline_elapsed_s,
        },
    )


def build_fallback_event(log: ExecutionLog, timestamp_relative: Optional[float]) -> DashboardEvent:
    """Build the timeline event for executor fallback usage."""
    return DashboardEvent(
        stream="incidents",
        type="FALLBACK_USED",
        incident_id=log.incident_id,
        timestamp_relative=timestamp_relative,
        data={
            "requested_action": log.requested_action_type,
            "fallback_action": log.action_type,
            "reason": log.fallback_reason,
            "service": log.service,
        },
    )


def build_queue_overflow_event(dropped: ExecutorRequest) -> DashboardEvent:
    """Build an event for queue overflow when the oldest item is dropped."""
    return DashboardEvent(
        stream="incidents",
        type="EXECUTOR_QUEUE_OVERFLOW",
        incident_id=dropped.incident_id,
        data={
            "service": dropped.service,
            "dropped_action": dropped.requested_action_type,
            "reason": "queue overflow, dropped oldest action",
        },
    )


def build_cooldown_race_blocked_event(log: ExecutionLog, timestamp_relative: Optional[float]) -> DashboardEvent:
    """Build an event for a race caught by the executor cooldown double-check."""
    return DashboardEvent(
        stream="incidents",
        type="COOLDOWN_RACE_BLOCKED",
        incident_id=log.incident_id,
        timestamp_relative=timestamp_relative,
        data={
            "service": log.service,
            "reason": log.docker_response,
            "pipeline_elapsed_s": log.pipeline_elapsed_s,
        },
    )
