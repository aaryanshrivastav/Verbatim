"""Pydantic contracts for the Feedback Loop."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from decision_engine.models import DashboardEvent
from remediation_executor.models import ExecutionLog


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class FeedbackRequest(BaseModel):
    """Input envelope consumed by the Feedback Loop."""

    model_config = ConfigDict(extra="ignore")

    execution_log: ExecutionLog
    endpoint: Optional[str] = None
    affected_services: List[str] = Field(default_factory=list)
    parent_incident_id: Optional[str] = None


class BaselineRecord(BaseModel):
    """Baseline thresholds used for recovery confirmation."""

    service: str
    endpoint: Optional[str] = None
    error_rate_baseline: float = Field(ge=0.0)
    p95_latency_baseline_ms: float = Field(ge=0.0)
    source: str = "default"
    used_default: bool = False


class RecoveryMetrics(BaseModel):
    """Current metrics fetched for a service after remediation."""

    error_rate: Optional[float] = Field(default=None, ge=0.0)
    p95_latency_ms: Optional[float] = Field(default=None, ge=0.0)
    source: str = "unknown"
    issues: List[str] = Field(default_factory=list)


class Phase1Result(BaseModel):
    """Outcome of the Docker/container verification step."""

    result: str
    container_status: str
    checked_at: datetime


class Phase2Result(BaseModel):
    """Outcome of the metrics verification step."""

    result: str
    checked_at: datetime
    current_error_rate: Optional[float] = Field(default=None, ge=0.0)
    threshold_error_rate: Optional[float] = Field(default=None, ge=0.0)
    current_p95_latency_ms: Optional[float] = Field(default=None, ge=0.0)
    threshold_p95_latency_ms: Optional[float] = Field(default=None, ge=0.0)
    failure_reason: Optional[str] = None
    baseline_source: str = "default"
    metrics_source: str = "unknown"


class RewardBreakdown(BaseModel):
    """Breakdown of the Bellman reward calculation."""

    base: float
    severity_bonus: float
    time_penalty: float
    fallback_penalty: float


class QUpdateResult(BaseModel):
    """Result of the live Bellman update."""

    skipped: bool = False
    reason: Optional[str] = None
    state: List[int] = Field(default_factory=list)
    action_id: Optional[int] = None
    action_type: Optional[str] = None
    reward: Optional[float] = None
    reward_breakdown: Optional[RewardBreakdown] = None
    q_before: Optional[float] = None
    q_after: Optional[float] = None
    q_shift: Optional[float] = None
    all_q_values_updated: Dict[str, float] = Field(default_factory=dict)
    episodes_live: int = 0
    q_table_size: int = 0
    s_prime: List[int] = Field(default_factory=list)
    checkpoint_saved: bool = False


class ClosureRecord(BaseModel):
    """Final closure summary for one incident lifecycle."""

    incident_id: str
    status: str = "PRIMARY_CLOSED"
    outcome: str
    cascade_status: str
    timeline: Dict[str, Optional[float]] = Field(default_factory=dict)
    end_to_end_latency_s: Optional[float] = None
    rl_q_shift: Optional[float] = None
    episodes_trained_live: int = 0
    bellman_update: Dict[str, Optional[float]] = Field(default_factory=dict)


class FeedbackResult(BaseModel):
    """End-to-end result emitted by the Feedback Loop."""

    incident_id: str
    service: str
    outcome: str
    phase1: Phase1Result
    phase2: Optional[Phase2Result] = None
    recovery_confirmed: bool = False
    reward: float
    reward_breakdown: RewardBreakdown
    q_update: QUpdateResult
    cascade_status: str
    cascade_incident: Optional[Dict[str, object]] = None
    cascade_decision: Optional[Dict[str, object]] = None
    cascade_execution_log: Optional[Dict[str, object]] = None
    closure: ClosureRecord
    events: List[DashboardEvent] = Field(default_factory=list)
