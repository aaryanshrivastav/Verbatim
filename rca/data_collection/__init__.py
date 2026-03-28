"""
Data Collection: Anomaly Detection Layer.

This module provides metrics-only anomaly detection for microservices.
It consumes Prometheus metrics and emits AnomalyEvent and Incident objects.

Key Components:
  - config: Configuration management with env var loading
  - models: Pydantic data models (StreamKey, AnomalyEvent, Incident, etc.)
  - ring_buffer: Fixed-size circular buffer for metric windows
  - rolling_stats: Online mean/std computation
  - prometheus_client: Prometheus HTTP API client
  - derived_metrics: Raw metric aggregation → p95, error_rate, request_rate
  - scorer: Z-score normalization and severity computation
  - detector: Main detection orchestrator (per-tick anomaly scoring)
  - incident_cluster: Incident grouping by endpoint and time window
  - main: CLI entry point and orchestration loop
"""

from .config import DetectionConfig
from .models import (
    StreamKey,
    DerivedMetrics,
    AnomalyEvent,
    AnomalyType,
    Incident,
    StreamState,
)
from .detector import AnomalyDetector
from .incident_cluster import IncidentCluster

__all__ = [
    "DetectionConfig",
    "StreamKey",
    "DerivedMetrics",
    "AnomalyEvent",
    "AnomalyType",
    "Incident",
    "StreamState",
    "AnomalyDetector",
    "IncidentCluster",
]
