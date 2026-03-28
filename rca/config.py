"""Configuration for RCA pipeline."""

import os
from dataclasses import dataclass


@dataclass
class RCAConfig:
    """RCA pipeline configuration."""
    
    # External service endpoints
    jaeger_base_url: str = os.getenv("JAEGER_BASE_URL", "http://localhost:16686")
    prometheus_base_url: str = os.getenv("PROMETHEUS_BASE_URL", "http://localhost:9090")
    loki_base_url: str = os.getenv("LOKI_BASE_URL", "http://localhost:3100")
    
    # Trace query
    trace_query_limit: int = int(os.getenv("RCA_TRACE_QUERY_LIMIT", "20"))
    span_suspicious_multiplier: float = float(os.getenv("RCA_SPAN_SUSPICIOUS_K", "3.0"))
    baseline_window_seconds: int = int(os.getenv("RCA_BASELINE_WINDOW", "60"))
    
    # Candidate extraction
    trace_coverage_threshold: float = float(os.getenv("RCA_TRACE_COVERAGE_THRESHOLD", "0.3"))
    suspicious_ratio_threshold: float = float(os.getenv("RCA_SUSPICIOUS_RATIO_THRESHOLD", "0.2"))
    metrics_severity_threshold: float = float(os.getenv("RCA_METRICS_SEVERITY_THRESHOLD", "0.5"))
    
    # ML ranker
    ml_model_path: str = os.getenv("RCA_ML_MODEL_PATH", "rca/models/rca_model.pkl")
    fallback_weights: dict = None  # Will be set in __post_init__
    
    # Feature builder
    service_depth_map: dict = None  # Will be set in __post_init__
    database_services: set = None  # Will be set in __post_init__
    edge_services: set = None  # Will be set in __post_init__
    
    # State vector
    critical_severity_threshold: float = float(os.getenv("RCA_CRITICAL_SEVERITY", "0.8"))
    degraded_severity_threshold: float = float(os.getenv("RCA_DEGRADED_SEVERITY", "0.3"))
    
    # Confidence buckets
    confidence_high_threshold: float = float(os.getenv("RCA_CONFIDENCE_HIGH", "0.3"))
    confidence_medium_threshold: float = float(os.getenv("RCA_CONFIDENCE_MEDIUM", "0.15"))
    
    def __post_init__(self):
        """Initialize complex fields."""
        if self.fallback_weights is None:
            self.fallback_weights = {
                "metrics": 0.5,
                "traces": 0.4,
                "coverage": 0.1
            }
        
        if self.service_depth_map is None:
            self.service_depth_map = {
                "frontend": 0,
                "api-gateway": 1,
                "gateway": 1,
                "auth": 2,
                "catalog": 2,
                "checkout": 2,
                "order": 2,
                "orders": 2,
                "payment": 3,
                "payment-service": 3,
                "inventory": 2,
                "shipping": 2,
                "notification": 2,
                "orders-db": -1,
                "user-db": -1,
                "catalog-db": -1,
                "cache": -1,
            }
        
        if self.database_services is None:
            self.database_services = {s for s in self.service_depth_map 
                                     if "db" in s or s == "cache"}
        
        if self.edge_services is None:
            self.edge_services = {"frontend", "api-gateway", "gateway"}
    
    def get_service_depth(self, service: str) -> int:
        """Get depth for a service, default 2."""
        return self.service_depth_map.get(service, 2)
    
    def is_database(self, service: str) -> bool:
        """Check if service is database."""
        return service in self.database_services
    
    def is_edge(self, service: str) -> bool:
        """Check if service is edge (frontend/gateway)."""
        return service in self.edge_services
