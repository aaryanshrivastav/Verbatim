"""Anomaly detection module.

Provides production-ready per-service anomaly detection
using Prometheus metrics only.

Components:
    - config: Configuration from environment variables
    - models: Pydantic models for events and incidents
    - ring_buffer: Fixed-size circular buffer for streaming values
    - rolling_stats: Online mean/std computation
    - prometheus_client: HTTP client for fetching metrics
    - derived_metrics: Computes p95_latency, error_rate, request_rate
    - scorer: Z-score based anomaly scoring
    - detector: Main detection engine
    - incident_cluster: Clusters anomalies into incidents
    - service: HTTP service interface
    - main: Entry point for standalone execution
"""

from detection.config import DetectionConfig
from detection.models import (
    AnomalyEvent, AnomalyType, Incident, IncidentAnomaly
)
from detection.detector import AnomalyDetector
from detection.service import DetectionService

__version__ = "1.0.0"
__all__ = [
    "DetectionConfig",
    "AnomalyEvent",
    "AnomalyType",
    "Incident",
    "IncidentAnomaly",
    "AnomalyDetector",
    "DetectionService",
]
