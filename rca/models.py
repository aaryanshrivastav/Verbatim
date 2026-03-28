"""Data models for RCA pipeline.

Incident, candidates, features, and final RCA output.
"""

from enum import Enum
from typing import List, Optional, Dict
from datetime import datetime
from dataclasses import dataclass, field
from pydantic import BaseModel, Field


class ConfidenceBucket(str, Enum):
    """Confidence level for root cause prediction."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class AnomalyDetail:
    """Single service's contribution to incident (from Detection)."""
    service: str
    severity: float  # [0, 1]
    anomaly_type: str  # "latency_spike", "error_spike", "mixed"


@dataclass
class Incident:
    """RCA input: incident from detection system."""
    incident_id: str
    endpoint: str
    time_window_start: datetime
    time_window_end: datetime
    anomalies: List[AnomalyDetail] = field(default_factory=list)
    
    def get_anomaly_severity(self, service: str) -> Optional[float]:
        """Get severity for a service, or None."""
        for anom in self.anomalies:
            if anom.service == service:
                return anom.severity
        return None
    
    def get_max_severity(self) -> float:
        """Get max severity among all anomalies."""
        return max((a.severity for a in self.anomalies), default=0.0)


@dataclass
class TraceMetrics:
    """Metrics per service from trace graph."""
    service: str
    span_count: int
    suspicious_count: int
    trace_coverage: float  # fraction of traces containing this service
    suspicious_span_ratio: float  # suspicious_count / span_count
    
    @property
    def appears_in_traces(self) -> float:
        """Alias for trace_coverage."""
        return self.trace_coverage


@dataclass
class FeatureVector:
    """Feature vector for ML ranking."""
    service: str
    m: float  # metrics_severity
    t: float  # suspicious_span_ratio
    c: float  # trace_coverage
    depth: int  # hop distance (0=frontend, 1=gateway, 2+=service, -1=db)
    is_db: int  # 1 if database, 0 otherwise
    is_edge: int  # 1 if frontend/gateway, 0 otherwise
    
    def to_array(self) -> List[float]:
        """Convert to feature array for ML model."""
        return [float(self.m), float(self.t), float(self.c), 
                float(self.depth), float(self.is_db), float(self.is_edge)]


@dataclass
class Candidate:
    """Candidate root cause service."""
    service: str
    trace_metrics: TraceMetrics
    feature_vector: FeatureVector
    probability: Optional[float] = None  # Set by ranker
    fallback_score: Optional[float] = None  # Fallback if model fails


class Confidence(BaseModel):
    """Confidence in root cause prediction."""
    value: float = Field(..., ge=0.0, le=1.0)
    bucket: ConfidenceBucket


class CandidatePrediction(BaseModel):
    """Single candidate in predictions."""
    service: str
    probability: float = Field(..., ge=0.0, le=1.0)


class Evidence(BaseModel):
    """Evidence for root cause."""
    metrics: List[str] = Field(default_factory=list)
    traces: List[str] = Field(default_factory=list)
    logs: List[str] = Field(default_factory=list)


class RCAOutput(BaseModel):
    """Final RCA output contract."""
    incident_id: str
    endpoint: str
    root_cause: str
    confidence: Confidence
    top_candidates: List[CandidatePrediction]
    affected_services: List[str]
    state_vector: List[int]  # 6 elements
    original_severity: float
    time_window: List[str]  # ISO 8601 strings
    evidence: Evidence
    
    class Config:
        use_enum_values = True
