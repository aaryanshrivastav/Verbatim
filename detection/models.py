"""Data models for anomaly detection.

Defines Pydantic models for events, incidents, and internal state.
All models are JSON-serializable for easy export.
"""

from enum import Enum
from typing import List, Optional
from datetime import datetime
from dataclasses import dataclass, field, asdict
from pydantic import BaseModel, Field


class AnomalyType(str, Enum):
    """Classification of anomaly by metric stream."""
    LATENCY_SPIKE = "latency_spike"
    ERROR_SPIKE = "error_spike"
    MIXED = "mixed"


class AnomalyEvent(BaseModel):
    """Single anomaly detection event.
    
    Triggered when a service's metric enters anomalous state.
    Attributes:
        service: Name of the affected service
        endpoint: HTTP endpoint that triggered anomaly
        anomaly_type: Classification (latency_spike, error_spike, or mixed)
        severity: Combined score [0, 1]
        timestamp: ISO 8601 timestamp of detection
        latency_score: Optional raw latency anomaly score
        error_score: Optional raw error rate anomaly score
    """
    service: str
    endpoint: str
    anomaly_type: AnomalyType
    severity: float = Field(..., ge=0, le=1)
    timestamp: datetime
    latency_score: Optional[float] = None
    error_score: Optional[float] = None
    
    class Config:
        use_enum_values = True


class IncidentAnomaly(BaseModel):
    """Single service's contribution to an incident."""
    service: str
    severity: float = Field(..., ge=0, le=1)
    anomaly_type: AnomalyType
    detected_at: datetime
    
    class Config:
        use_enum_values = True


class Incident(BaseModel):
    """Cluster of related anomalies for RCA handoff.
    
    Groups anomalies by endpoint and time window.
    Does NOT diagnose root cause; only clusters related anomalies.
    
    Attributes:
        incident_id: Unique incident identifier
        endpoint: Shared endpoint for this incident
        time_window_start: Start of clustering window
        time_window_end: End of clustering window
        anomalies: List of contributing services and their anomaly details
    """
    incident_id: str
    endpoint: str
    time_window_start: datetime
    time_window_end: datetime
    anomalies: List[IncidentAnomaly] = Field(default_factory=list)
    
    @property
    def max_severity(self) -> float:
        """Return max severity among contributing anomalies."""
        if not self.anomalies:
            return 0.0
        return max(a.severity for a in self.anomalies)
    
    @property
    def affected_services(self) -> List[str]:
        """Return list of distinct services in this incident."""
        return list(set(a.service for a in self.anomalies))


@dataclass
class MetricValue:
    """Single metric observation.
    
    Attributes:
        timestamp: Seconds since epoch
        value: The metric value
        labels: Dictionary of label keys/values
    """
    timestamp: float
    value: float
    labels: dict = field(default_factory=dict)


@dataclass
class StreamKey:
    """Unique identifier for a metric stream.
    
    Represents one (service, endpoint, metric_type) tuple.
    """
    service: str
    endpoint: str
    metric_type: str  # "p95_latency" or "error_rate"
    
    def __hash__(self):
        return hash((self.service, self.endpoint, self.metric_type))
    
    def __eq__(self, other):
        if not isinstance(other, StreamKey):
            return False
        return (self.service == other.service and 
                self.endpoint == other.endpoint and 
                self.metric_type == other.metric_type)


@dataclass
class StreamState:
    """Internal state for a single metric stream.
    
    Maintains rolling buffer, rolling statistics, and trigger state.
    """
    key: StreamKey
    buffer: List[float] = field(default_factory=list)  # Ring buffer values
    rolling_mean: float = 0.0
    rolling_std: float = 0.0
    is_anomalous: bool = False
    last_anomaly_emitted_at: Optional[float] = None  # For deduplication


@dataclass
class EndpointKey:
    """Unique identifier for endpoint + metric_type."""
    endpoint: str
    metric_type: str  # "p95_latency" or "error_rate"
    
    def __hash__(self):
        return hash((self.endpoint, self.metric_type))
    
    def __eq__(self, other):
        if not isinstance(other, EndpointKey):
            return False
        return self.endpoint == other.endpoint and self.metric_type == other.metric_type
