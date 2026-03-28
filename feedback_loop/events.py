"""Dashboard event builders for Component 6."""

from __future__ import annotations

from typing import Optional

from decision_engine.models import DashboardEvent
from feedback_loop.models import ClosureRecord, Phase1Result, Phase2Result, QUpdateResult


def build_phase1_event(incident_id: str, phase1: Phase1Result, timestamp_relative: Optional[float]) -> DashboardEvent:
    event_type = "PHASE1_CONFIRMED" if phase1.result == "PROVISIONALLY_RECOVERED" else "PHASE1_FAILED"
    dashboard_state = "amber" if phase1.result == "PROVISIONALLY_RECOVERED" else "red"
    return DashboardEvent(
        stream="incidents",
        type=event_type,
        incident_id=incident_id,
        timestamp_relative=timestamp_relative,
        data={
            "container_status": phase1.container_status,
            "result": phase1.result,
            "dashboard_state": dashboard_state,
        },
    )


def build_phase2_event(incident_id: str, phase2: Phase2Result, timestamp_relative: Optional[float]) -> DashboardEvent:
    event_type_map = {
        "CONFIRMED_RECOVERED": "PHASE2_CONFIRMED",
        "METRICS_DEGRADED": "PHASE2_FAILED",
        "METRICS_UNKNOWN": "PHASE2_SKIPPED",
    }
    dashboard_state = {
        "CONFIRMED_RECOVERED": "green",
        "METRICS_DEGRADED": "red",
        "METRICS_UNKNOWN": "amber",
    }[phase2.result]
    return DashboardEvent(
        stream="incidents",
        type=event_type_map[phase2.result],
        incident_id=incident_id,
        timestamp_relative=timestamp_relative,
        data={
            "result": phase2.result,
            "current_error_rate": phase2.current_error_rate,
            "threshold_error_rate": phase2.threshold_error_rate,
            "current_p95_latency_ms": phase2.current_p95_latency_ms,
            "threshold_p95_latency_ms": phase2.threshold_p95_latency_ms,
            "failure_reason": phase2.failure_reason,
            "dashboard_state": dashboard_state,
        },
    )


def build_effectiveness_event(
    incident_id: str,
    outcome: str,
    timestamp_relative: Optional[float],
    reason: Optional[str],
    q_shift: Optional[float],
) -> DashboardEvent:
    event_type = "REMEDIATION_EFFECTIVE" if outcome == "RECOVERED" else "REMEDIATION_INEFFECTIVE"
    return DashboardEvent(
        stream="incidents",
        type=event_type,
        incident_id=incident_id,
        timestamp_relative=timestamp_relative,
        data={
            "reason": reason,
            "dashboard_state": "green" if outcome == "RECOVERED" else "red",
            "rl_learned": q_shift is not None,
            "q_shift": q_shift,
        },
    )


def build_rl_updated_event(incident_id: str, update: QUpdateResult, timestamp_relative: Optional[float]) -> DashboardEvent:
    return DashboardEvent(
        stream="rl",
        type="RL_Q_UPDATED",
        incident_id=incident_id,
        timestamp_relative=timestamp_relative,
        data={
            "state": update.state,
            "action_id": update.action_id,
            "action_type": update.action_type,
            "reward": update.reward,
            "reward_breakdown": update.reward_breakdown.model_dump() if update.reward_breakdown else None,
            "q_before": update.q_before,
            "q_after": update.q_after,
            "q_shift": update.q_shift,
            "all_q_values_updated": update.all_q_values_updated,
            "episodes_live": update.episodes_live,
            "q_table_size": update.q_table_size,
            "s_prime": update.s_prime,
            "checkpoint_saved": update.checkpoint_saved,
        },
    )


def build_rl_skipped_event(incident_id: str, update: QUpdateResult, timestamp_relative: Optional[float]) -> DashboardEvent:
    return DashboardEvent(
        stream="rl",
        type="RL_UPDATE_SKIPPED",
        incident_id=incident_id,
        timestamp_relative=timestamp_relative,
        data={
            "reason": update.reason,
            "episodes_live": update.episodes_live,
            "q_table_size": update.q_table_size,
        },
    )


def build_cascade_event(
    incident_id: str,
    event_type: str,
    timestamp_relative: Optional[float],
    data: dict,
) -> DashboardEvent:
    return DashboardEvent(
        stream="incidents",
        type=event_type,
        incident_id=incident_id,
        timestamp_relative=timestamp_relative,
        data=data,
    )


def build_closure_event(closure: ClosureRecord) -> DashboardEvent:
    return DashboardEvent(
        stream="incidents",
        type="INCIDENT_CLOSED",
        incident_id=closure.incident_id,
        timestamp_relative=closure.end_to_end_latency_s,
        data={
            "outcome": closure.outcome,
            "end_to_end_latency_s": closure.end_to_end_latency_s,
            "sla_met": bool(closure.end_to_end_latency_s is not None and closure.end_to_end_latency_s < 15.0),
            "episodes_live": closure.episodes_trained_live,
            "cascade_status": closure.cascade_status,
        },
    )
