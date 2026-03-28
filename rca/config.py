"""Configuration for RCA pipeline."""

import os
from dataclasses import dataclass
from typing import Optional


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
    allow_synthetic_trace_fallback: bool = os.getenv("RCA_ALLOW_SYNTHETIC_TRACE_FALLBACK", "false").lower() == "true"
    
    # Candidate extraction
    trace_coverage_threshold: float = float(os.getenv("RCA_TRACE_COVERAGE_THRESHOLD", "0.3"))
    suspicious_ratio_threshold: float = float(os.getenv("RCA_SUSPICIOUS_RATIO_THRESHOLD", "0.2"))
    metrics_severity_threshold: float = float(os.getenv("RCA_METRICS_SEVERITY_THRESHOLD", "0.5"))
    
    # ML ranker
    ml_model_path: str = os.getenv("RCA_ML_MODEL_PATH", "models/ml_ranker_logistic_regression.pkl")
    fallback_weights: dict = None  # Will be set in __post_init__
    
    # Feature builder
    service_depth_map: dict = None  # Will be set in __post_init__
    database_services: set = None  # Will be set in __post_init__
    edge_services: set = None  # Will be set in __post_init__
    service_aliases: dict = None  # Will be set in __post_init__
    state_slots: tuple = None  # Will be set in __post_init__
    
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
                "gateway": 1,
                "auth": 2,
                "catalog": 2,
                "order": 2,
                "payment": 3,
                "db": -1,
            }

        if self.service_aliases is None:
            self.service_aliases = {
                "frontend": "gateway",
                "main-app": "gateway",
                "microservices-demo": "gateway",
                "api-gateway": "gateway",
                "gateway-service": "gateway",
                "gateway": "gateway",
                "auth-service": "auth",
                "auth": "auth",
                "catalog-service": "catalog",
                "catalog": "catalog",
                "order-service": "order",
                "orderservice": "order",
                "orders": "order",
                "checkout": "order",
                "checkoutservice": "order",
                "order": "order",
                "payment-service": "payment",
                "paymentservice": "payment",
                "payment": "payment",
                "postgres": "db",
                "orders-db": "db",
                "user-db": "db",
                "catalog-db": "db",
                "db": "db",
                "redis": "db",
                "cache": "db",
            }

        if self.state_slots is None:
            self.state_slots = ("gateway", "auth", "catalog", "order", "payment", "db")
        
        if self.database_services is None:
            self.database_services = {"db"}
        
        if self.edge_services is None:
            self.edge_services = {"gateway"}
    
    def get_service_depth(self, service: str) -> int:
        """Get depth for a service, default 2."""
        return self.service_depth_map.get(self.normalize_service_name(service), 2)
    
    def is_database(self, service: str) -> bool:
        """Check if service is database."""
        return self.normalize_service_name(service) in self.database_services
    
    def is_edge(self, service: str) -> bool:
        """Check if service is edge (frontend/gateway)."""
        return self.normalize_service_name(service) in self.edge_services

    def normalize_service_name(self, service: Optional[str]) -> str:
        """Map concrete runtime names into RCA canonical names."""
        if not service:
            return ""
        return self.service_aliases.get(service, service)

    def state_slot_for(self, service: Optional[str]) -> Optional[str]:
        """Map a service into one of the fixed RL state-vector slots."""
        normalized = self.normalize_service_name(service)
        return normalized if normalized in self.state_slots else None
