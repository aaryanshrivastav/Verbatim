"""Contracts for queue input and execution output."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from decision_engine.models import DecisionOutput


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class ExecutorRequest(BaseModel):
    """Queue entry consumed by the executor worker."""

    model_config = ConfigDict(extra="ignore")

    incident_id: str
    decision_timestamp: datetime
    action: Dict[str, object]
    confidence_log: Dict[str, object]
    state_vector: list[int]
    original_severity: float
    rollback_watch: bool
    cascade_secondary_pending: bool
    safety_overridden: bool = False
    incident_started_at: Optional[datetime] = None
    detection_timestamp: Optional[datetime] = None

    @classmethod
    def from_decision_output(
        cls,
        decision: DecisionOutput,
        incident_started_at: Optional[datetime] = None,
        detection_timestamp: Optional[datetime] = None,
    ) -> "ExecutorRequest":
        """Create an executor request from a validated Decision output."""
        return cls(
            incident_id=decision.incident_id,
            decision_timestamp=decision.decision_timestamp,
            action=decision.action.model_dump(),
            confidence_log=decision.confidence_log.model_dump(),
            state_vector=decision.state_vector,
            original_severity=decision.original_severity,
            rollback_watch=decision.rollback_watch,
            cascade_secondary_pending=decision.cascade_secondary_pending,
            safety_overridden=decision.safety_overridden,
            incident_started_at=incident_started_at,
            detection_timestamp=detection_timestamp,
        )

    @property
    def service(self) -> str:
        """Return the requested target service."""
        return str(self.action["service"])

    @property
    def requested_action_type(self) -> str:
        """Return the requested action label."""
        return str(self.action["action_type"])

    @property
    def requested_action_id(self) -> int:
        """Return the requested action identifier."""
        return int(self.action["action_id"])


class ExecutionLog(BaseModel):
    """Execution log emitted downstream to Feedback Loop."""

    incident_id: str
    service: str
    container_name: Optional[str] = None
    compose_service_name: Optional[str] = None
    action_type: str
    action_id: int
    requested_action_type: str
    requested_action_id: int
    source: str
    q_value: float
    all_q_values: Dict[str, float]
    state_vector: list[int]
    original_severity: float
    confidence_bucket: str
    execution_start: datetime = Field(default_factory=utc_now)
    execution_end: datetime = Field(default_factory=utc_now)
    api_latency_ms: int = 0
    pipeline_elapsed_s: Optional[float] = None
    api_status: str
    docker_response: str
    rollback_watch: bool
    cascade_secondary_pending: bool
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    safety_overridden: bool = False
    detection_timestamp: Optional[datetime] = None
