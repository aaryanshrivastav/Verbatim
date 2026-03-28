"""Pydantic models shared across Decision Engine runtime modules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class RCAConfidence(BaseModel):
    """Confidence emitted by the RCA module."""

    value: float = Field(ge=0.0, le=1.0)
    bucket: str


class RCACandidate(BaseModel):
    """Candidate root-cause ranking from RCA."""

    service: str
    probability: float = Field(ge=0.0, le=1.0)


class RCAOutput(BaseModel):
    """Validated RCA payload consumed by the Decision Engine."""

    model_config = ConfigDict(extra="ignore")

    incident_id: str
    endpoint: Optional[str] = None
    root_cause: str
    confidence: RCAConfidence
    top_candidates: List[RCACandidate] = Field(default_factory=list)
    affected_services: List[str] = Field(default_factory=list)
    state_vector: List[int] = Field(min_length=6, max_length=6)
    original_severity: float = Field(ge=0.0, le=1.0)
    time_window: List[str] = Field(default_factory=list)
    incident_started_at: Optional[datetime] = None

    @field_validator("state_vector")
    @classmethod
    def validate_state_values(cls, values: List[int]) -> List[int]:
        """Allow only the three discrete health states used by the RL agent."""
        if any(value not in (0, 1, 2) for value in values):
            raise ValueError("state_vector values must be 0, 1, or 2")
        return values


class SafetyChecks(BaseModel):
    """Outcome of each safety check."""

    cooldown_passed: bool
    global_lock_passed: bool
    dedup_passed: bool
    service_passed: bool = True


class SafetyEvaluation(BaseModel):
    """Result from the safety gate before action selection."""

    blocked: bool
    reason: Optional[str] = None
    checks: SafetyChecks


class PolicySelection(BaseModel):
    """Policy output before it is wrapped into a decision contract."""

    action_id: int
    action_type: str
    q_value: float
    all_q_values: Dict[str, float]
    q_table_hit: bool
    masked_actions: List[str] = Field(default_factory=list)
    defaulted: bool = False
    policy_source: str = "q_table"
    selection_mode: str = "argmax"


class DecisionAction(BaseModel):
    """Action contract passed downstream to the Remediation Executor."""

    service: str
    action_type: str
    action_id: int
    source: str = "rl_agent"
    q_value: float
    all_q_values: Dict[str, float]


class ConfidenceLog(BaseModel):
    """Display-oriented confidence information derived from RCA."""

    rca_confidence: float = Field(ge=0.0, le=1.0)
    tier: str
    dashboard_color: str


class DecisionReasoning(BaseModel):
    """Compact explainability payload for dashboard and audit logs."""

    policy_source: str
    selection_mode: str
    q_table_hit: bool
    masked_actions: List[str] = Field(default_factory=list)
    defaulted: bool = False


class DecisionOutput(BaseModel):
    """Successful decision output emitted by Component 4."""

    incident_id: str
    decision_timestamp: datetime
    decision_latency_ms: int
    action: DecisionAction
    confidence_log: ConfidenceLog
    safety_checks: SafetyChecks
    state_vector: List[int] = Field(min_length=6, max_length=6)
    original_severity: float = Field(ge=0.0, le=1.0)
    rollback_watch: bool
    cascade_secondary_pending: bool
    safety_overridden: bool = False
    reasoning: DecisionReasoning


class DecisionBlockedOutput(BaseModel):
    """Blocked decision output when safety constraints stop execution."""

    decision: str = "BLOCKED"
    incident_id: str
    decision_timestamp: datetime
    decision_latency_ms: int
    root_cause: str
    reason: str
    safety_checks: SafetyChecks


class DecisionSkippedOutput(BaseModel):
    """Skipped decision output for invalid or non-actionable RCA input."""

    decision: str = "SKIPPED"
    incident_id: Optional[str] = None
    decision_timestamp: datetime
    decision_latency_ms: int
    reason: str
    errors: List[str] = Field(default_factory=list)


class DashboardEvent(BaseModel):
    """Generic event published to the dashboard bus."""

    stream: str
    type: str
    incident_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=utc_now)
    timestamp_relative: Optional[float] = None
    data: Dict[str, object] = Field(default_factory=dict)
