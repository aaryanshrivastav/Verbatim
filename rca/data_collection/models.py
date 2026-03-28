"""Data models for anomaly detection."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from enum import Enum
import uuid


class AnomalyType(str, Enum):
    """Classification of anomaly."""
    LATENCY_SPIKE = "latency_spike"
    ERROR_SPIKE = "error_spike"
    MIXED = "mixed"


@dataclass
class StreamKey:
    """Unique identifier for a metric stream (service, endpoint, metric_type)."""
    service: str
    endpoint: str
    metric_type: str  # "latency", "error_rate", "request_rate"
    
    def __hash__(self):
        return hash((self.service, self.endpoint, self.metric_type))
    
    def __eq__(self, other):
        if not isinstance(other, StreamKey):
            return False
        return (self.service == other.service and
                self.endpoint == other.endpoint and
                self.metric_type == other.metric_type)


@dataclass
class DerivedMetrics:
    """Aggregated metrics for a service/endpoint at a point in time."""
    service: str
    endpoint: str
    p95_latency: float  # seconds, from histogram quantile
    error_rate: float   # [0, 1], errors / total requests
    request_rate: float  # requests per second
    timestamp: datetime


@dataclass
class AnomalyEvent:
    """A single anomaly detection event."""
    service: str
    endpoint: str
    anomaly_type: AnomalyType
    severity: float  # [0, 1]
    timestamp: datetime
    latency_score: float = 0.0  # [0, 1]
    error_score: float = 0.0    # [0, 1]
    
    def to_dict(self):
        return {
            "service": self.service,
            "endpoint": self.endpoint,
            "anomaly_type": self.anomaly_type.value,
            "severity": round(self.severity, 3),
            "timestamp": self.timestamp.isoformat(),
            "latency_score": round(self.latency_score, 3),
            "error_score": round(self.error_score, 3),
        }


@dataclass
class Incident:
    """An incident: clustered anomalies by endpoint and time window."""
    incident_id: str = field(default_factory=lambda: f"inc-{uuid.uuid4().hex[:8]}")
    endpoint: str = ""
    time_window_start: datetime = field(default_factory=datetime.utcnow)
    time_window_end: datetime = field(default_factory=datetime.utcnow)
    anomalies: List[AnomalyEvent] = field(default_factory=list)
    
    def add_anomaly(self, event: AnomalyEvent):
        """Add an anomaly event to this incident."""
        self.anomalies.append(event)
        # Update time window to encompass new event
        if event.timestamp < self.time_window_start:
            self.time_window_start = event.timestamp
        if event.timestamp > self.time_window_end:
            self.time_window_end = event.timestamp
    
    def to_dict(self):
        return {
            "incident_id": self.incident_id,
            "endpoint": self.endpoint,
            "time_window": {
                "start": self.time_window_start.isoformat(),
                "end": self.time_window_end.isoformat(),
            },
            "anomalies": [a.to_dict() for a in self.anomalies],
            "severity": self.max_severity(),
        }
    
    def max_severity(self) -> float:
        """Return the maximum severity across all anomalies in this incident."""
        if not self.anomalies:
            return 0.0
        return max(a.severity for a in self.anomalies)


@dataclass
class StreamState:
    """Internal state for a single metric stream."""
    key: StreamKey
    buffer_latency: "RingBuffer"  # imported at runtime
    buffer_error: "RingBuffer"
    mean_latency: float = 0.0
    std_latency: float = 0.0
    mean_error: float = 0.0
    std_error: float = 0.0
    last_event_time: Optional[datetime] = None
    last_event_cooldown_seconds: int = 30  # Deduplication cooldown
    
    def should_emit_duplicate_check(self, now: datetime) -> bool:
        """Check if enough time has passed to emit a new event (deduplication)."""
        if self.last_event_time is None:
            return True
        elapsed = (now - self.last_event_time).total_seconds()
        return elapsed >= self.last_event_cooldown_seconds
