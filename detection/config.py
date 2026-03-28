"""Configuration for the anomaly detection module.

Loads settings from environment variables with sensible defaults.
All thresholds and parameters can be tuned without code changes.
"""

import os
from dataclasses import dataclass


@dataclass
class DetectionConfig:
    """Configuration for anomaly detection engine."""
    
    # Prometheus connection
    prometheus_base_url: str = "http://localhost:9090"
    
    # Thresholds for anomaly triggers
    latency_threshold: float = 0.5        # L_thresh: trigger if latency_score >= 0.5
    error_threshold: float = 0.5          # E_thresh: trigger if error_score >= 0.5
    severity_threshold: float = 0.8       # S_severe: trigger if severity >= 0.8
    
    # Statistical parameters
    window_size: int = 60                 # W: rolling window (seconds)
    z_max: float = 3.0                    # Z_max: z-score clipping value
    
    # Timing
    warmup_seconds: int = 600             # First 10 minutes: baseline only, no alerts
    cluster_window_seconds: int = 10      # Incident clustering window
    poll_interval_seconds: int = 1        # Detection loop interval
    
    # Severity weights (must sum to 1.0)
    latency_weight: float = 0.6           # Weight for latency_score in severity
    error_weight: float = 0.4             # Weight for error_score in severity
    
    # Prometheus metric names (isolate in one place for easy reconfiguration)
    # Histogram metric for request latency (quantile extracted by detector)
    latency_metric_name: str = "http_request_duration_seconds"
    
    # Counter metric for total requests
    request_count_metric_name: str = "http_request_total"
    
    # Counter metric for errors
    error_count_metric_name: str = "http_request_duration_seconds"  # derived from request_duration_seconds with status code
    
    # Filters for metrics (label names for consistency)
    service_label: str = "service_name"
    endpoint_label: str = "http_route"
    status_label: str = "http_status_code"
    
    # Deduplication: avoid alert spam for steady-state anomalies
    # If an anomaly state doesn't change, suppress re-emission for this many seconds
    dedup_cooldown_seconds: int = 30
    
    @classmethod
    def from_env(cls) -> "DetectionConfig":
        """Load config from environment variables."""
        return cls(
            prometheus_base_url=os.getenv("PROMETHEUS_BASE_URL", cls.prometheus_base_url),
            latency_threshold=float(os.getenv("L_THRESH", cls.latency_threshold)),
            error_threshold=float(os.getenv("E_THRESH", cls.error_threshold)),
            severity_threshold=float(os.getenv("S_SEVERE", cls.severity_threshold)),
            window_size=int(os.getenv("WINDOW_SIZE", cls.window_size)),
            z_max=float(os.getenv("Z_MAX", cls.z_max)),
            warmup_seconds=int(os.getenv("WARMUP_SECONDS", cls.warmup_seconds)),
            cluster_window_seconds=int(os.getenv("CLUSTER_WINDOW_SECONDS", cls.cluster_window_seconds)),
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", cls.poll_interval_seconds)),
            latency_weight=float(os.getenv("LATENCY_WEIGHT", cls.latency_weight)),
            error_weight=float(os.getenv("ERROR_WEIGHT", cls.error_weight)),
            dedup_cooldown_seconds=int(os.getenv("DEDUP_COOLDOWN_SECONDS", cls.dedup_cooldown_seconds)),
        )
