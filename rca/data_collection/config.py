"""Configuration management for anomaly detection.

Loads configuration from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass


@dataclass
class DetectionConfig:
    """Configuration for the anomaly detector."""
    
    # Prometheus connection
    prometheus_base_url: str = os.getenv(
        "PROMETHEUS_BASE_URL",
        "http://localhost:9090"
    )
    
    # Anomaly thresholds (0.0 - 1.0)
    latency_threshold: float = float(os.getenv("L_THRESH", "0.5"))
    error_threshold: float = float(os.getenv("E_THRESH", "0.5"))
    severity_threshold: float = float(os.getenv("S_SEVERE", "0.8"))
    
    # Ring buffer and window sizes
    window_size: int = int(os.getenv("WINDOW_SIZE", "60"))  # 60 one-second samples
    z_max: float = float(os.getenv("Z_MAX", "3.0"))
    
    # Warm-up period (seconds)
    warmup_seconds: int = int(os.getenv("WARMUP_SECONDS", "600"))  # 10 minutes
    
    # Incident clustering window (seconds)
    cluster_window_seconds: int = int(os.getenv("CLUSTER_WINDOW_SECONDS", "10"))
    
    # Detection poll interval (seconds)
    poll_interval_seconds: int = int(os.getenv("POLL_INTERVAL_SECONDS", "1"))
    
    # Severity score weights
    latency_weight: float = 0.6
    error_weight: float = 0.4
    
    # Metric name configuration
    latency_metric_name: str = "request_latency_seconds"
    request_count_metric_name: str = "request_count_total"
    error_count_metric_name: str = "error_count_total"
    
    def validate(self):
        """Validate configuration values."""
        if self.window_size <= 0:
            raise ValueError("window_size must be positive")
        if not (0.0 <= self.latency_threshold <= 1.0):
            raise ValueError("latency_threshold must be in [0, 1]")
        if not (0.0 <= self.error_threshold <= 1.0):
            raise ValueError("error_threshold must be in [0, 1]")
        if not (0.0 <= self.severity_threshold <= 1.0):
            raise ValueError("severity_threshold must be in [0, 1]")
        if self.z_max <= 0:
            raise ValueError("z_max must be positive")
        if self.warmup_seconds < 0:
            raise ValueError("warmup_seconds must be non-negative")
        if self.cluster_window_seconds <= 0:
            raise ValueError("cluster_window_seconds must be positive")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if not (0.0 <= self.latency_weight <= 1.0):
            raise ValueError("latency_weight must be in [0, 1]")
        if not (0.0 <= self.error_weight <= 1.0):
            raise ValueError("error_weight must be in [0, 1]")
        
        # Weights should sum to approximately 1.0
        if abs(self.latency_weight + self.error_weight - 1.0) > 0.01:
            raise ValueError("latency_weight + error_weight should sum to ~1.0")
