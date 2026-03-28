"""Synthetic failure scenario generator.

Generates realistic time-series data for 7 failure types with edge cases:
1. DB failure (shared dependency)
2. Redis failure (cache layer)
3. API Gateway DDoS
4. Auth service overload
5. Payment timeout (deep chain)
6. SQL injection / hidden root cause
7. Retry storm (cascading failure)

Each scenario produces multiple "shapes" (slow ramp, sudden spike, partial, intermittent, etc.)
to train the ML model on diverse patterns.
"""

import math
import random
from typing import Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum


class FailureType(Enum):
    """7 failure types."""
    DB_FAILURE = "db_failure"
    REDIS_FAILURE = "redis_failure"
    GATEWAY_DDOS = "gateway_ddos"
    AUTH_OVERLOAD = "auth_overload"
    PAYMENT_TIMEOUT = "payment_timeout"
    SQL_INJECTION = "sql_injection"
    RETRY_STORM = "retry_storm"


class FailureShape(Enum):
    """How the failure manifests (edge cases)."""
    SLOW_RAMP = "slow_ramp"              # Gradual increase over 30s
    SUDDEN_SPIKE = "sudden_spike"        # Immediate jump
    PARTIAL = "partial"                  # Only affects subset of traffic
    INTERMITTENT = "intermittent"        # Flapping on/off every 5-10s
    CASCADED = "cascaded"                # Cascades through dependency chain
    BIMODAL = "bimodal"                  # Two populations (fast+slow)
    SLOW_INJECTION = "slow_injection"    # Gradually escalating
    RETRY_AMPLIFIED = "retry_amplified"  # Request rate amplified by retries


@dataclass
class MetricSnapshot:
    """Single point-in-time metric values for a service/endpoint."""
    service: str
    endpoint: str
    timestamp: int  # seconds since incident start
    
    # Latency metrics (ms)
    p95_latency: float
    
    # Error metrics
    error_rate: float  # [0, 1]
    request_rate: float  # requests per second
    
    # Service-specific
    db_query_latency_p95: float = 0.0  # for DB service
    cache_hit_ratio: float = 1.0       # for Redis
    connections_active: int = 0         # for DB


@dataclass
class FailureScenario:
    """Complete failure scenario with all service metrics over time."""
    failure_type: FailureType
    failure_shape: FailureShape
    scenario_id: str
    
    # Affected services and root cause
    affected_services: List[str]  # Services affected by failure
    root_cause_service: str        # Primary root cause
    affected_endpoints: List[str]  # Endpoints affected
    
    # Time series: service -> endpoint -> timestamp -> metrics
    metrics: Dict[str, Dict[str, List[MetricSnapshot]]]
    
    # Metadata
    intensity: float  # [0.5, 1.0] how severe
    start_time: int  # seconds (absolute)
    duration: int    # seconds


class ScenarioGenerator:
    """Generates synthetic failure scenarios."""
    
    # Service dependency graph: service -> [dependencies]
    DEPENDENCY_GRAPH = {
        "gateway": [],
        "frontend": ["gateway"],
        "auth-service": ["gateway"],
        "catalog-service": ["gateway", "db"],
        "order-service": ["gateway", "auth-service", "payment-service", "db"],
        "payment-service": ["gateway", "db", "redis"],
        "db": [],
        "redis": [],
    }
    
    # Endpoints per service
    ENDPOINTS_BY_SERVICE = {
        "gateway": ["/api/orders/create", "/api/auth/login", "/api/catalog/search", "/api/payment/checkout"],
        "auth-service": ["/api/auth/login", "/api/auth/validate", "/api/auth/logout"],
        "catalog-service": ["/api/catalog/search", "/api/catalog/products"],
        "order-service": ["/api/orders/create", "/api/orders/list", "/api/orders/cancel"],
        "payment-service": ["/api/payment/charge", "/api/payment/refund", "/api/payment/checkout"],
        "db": ["query"],
        "redis": ["get", "set"],
    }
    
    def __init__(self, seed: int = 42):
        random.seed(seed)
        self.scenario_counter = 0
    
    def generate_db_failure(self, shape: FailureShape, intensity: float = 0.8) -> FailureScenario:
        """Generate DB failure scenario.
        
        Root cause: DB service
        Affected: All services that depend on DB (catalog, order, payment, auth)
        """
        scenario_id = f"db_{shape.value}_{self.scenario_counter}"
        self.scenario_counter += 1
        
        affected_services = ["db", "catalog-service", "order-service", "payment-service", "auth-service"]
        root_cause = "db"
        
        metrics = {}
        
        if shape == FailureShape.SLOW_RAMP:
            # DB latency gradually increases from baseline to high
            metrics = self._generate_slow_ramp_metrics(affected_services, intensity)
        elif shape == FailureShape.SUDDEN_SPIKE:
            # DB latency jumps immediately to high
            metrics = self._generate_sudden_spike_metrics(affected_services, intensity)
        elif shape == FailureShape.PARTIAL:
            # Only one DB replica down; services see bimodal latency
            metrics = self._generate_partial_failure_metrics(affected_services, intensity)
        elif shape == FailureShape.INTERMITTENT:
            # DB flaps every 5-10 seconds
            metrics = self._generate_intermittent_metrics(affected_services, intensity)
        elif shape == FailureShape.CASCADED:
            # Redis off -> DB overloaded -> cache miss cascade
            metrics = self._generate_cascaded_metrics(affected_services, intensity)
        
        return FailureScenario(
            failure_type=FailureType.DB_FAILURE,
            failure_shape=shape,
            scenario_id=scenario_id,
            affected_services=affected_services,
            root_cause_service=root_cause,
            affected_endpoints=self.ENDPOINTS_BY_SERVICE.get(root_cause, []),
            metrics=metrics,
            intensity=intensity,
            start_time=random.randint(100, 1000),
            duration=60,
        )
    
    def generate_redis_failure(self, shape: FailureShape, intensity: float = 0.75) -> FailureScenario:
        """Generate Redis (cache) failure scenario.
        
        Root cause: Redis
        Affected: Services that use cache (catalog, auth, payment)
        """
        scenario_id = f"redis_{shape.value}_{self.scenario_counter}"
        self.scenario_counter += 1
        
        affected_services = ["redis", "catalog-service", "auth-service", "payment-service"]
        root_cause = "redis"
        
        metrics = {}
        
        if shape == FailureShape.SLOW_RAMP:
            metrics = self._generate_slow_ramp_metrics(affected_services, intensity)
        elif shape == FailureShape.SUDDEN_SPIKE:
            metrics = self._generate_sudden_spike_metrics(affected_services, intensity)
        elif shape == FailureShape.PARTIAL:
            metrics = self._generate_partial_failure_metrics(affected_services, intensity)
        elif shape == FailureShape.INTERMITTENT:
            metrics = self._generate_intermittent_metrics(affected_services, intensity)
        
        return FailureScenario(
            failure_type=FailureType.REDIS_FAILURE,
            failure_shape=shape,
            scenario_id=scenario_id,
            affected_services=affected_services,
            root_cause_service=root_cause,
            affected_endpoints=self.ENDPOINTS_BY_SERVICE.get(root_cause, []),
            metrics=metrics,
            intensity=intensity,
            start_time=random.randint(100, 1000),
            duration=60,
        )
    
    def generate_gateway_ddos(self, shape: FailureShape, intensity: float = 0.8) -> FailureScenario:
        """Generate gateway DDoS scenario.
        
        Root cause: Gateway saturation
        Affected: Gateway + downstream services
        """
        scenario_id = f"gateway_ddos_{shape.value}_{self.scenario_counter}"
        self.scenario_counter += 1
        
        affected_services = ["gateway", "catalog-service", "order-service", "payment-service"]
        root_cause = "gateway"
        
        metrics = {}
        
        if shape == FailureShape.SUDDEN_SPIKE:
            metrics = self._generate_sudden_spike_metrics(affected_services, intensity)
        elif shape == FailureShape.SLOW_RAMP:
            metrics = self._generate_slow_ramp_metrics(affected_services, intensity)
        elif shape == FailureShape.PARTIAL:
            # Only /checkout endpoint is saturated
            metrics = self._generate_partial_failure_metrics(affected_services, intensity)
        
        return FailureScenario(
            failure_type=FailureType.GATEWAY_DDOS,
            failure_shape=shape,
            scenario_id=scenario_id,
            affected_services=affected_services,
            root_cause_service=root_cause,
            affected_endpoints=["/api/payment/checkout"],
            metrics=metrics,
            intensity=intensity,
            start_time=random.randint(100, 1000),
            duration=60,
        )
    
    def generate_auth_overload(self, shape: FailureShape, intensity: float = 0.7) -> FailureScenario:
        """Generate auth service overload.
        
        Root cause: Auth service
        Affected: Auth + services that depend on auth (order)
        """
        scenario_id = f"auth_{shape.value}_{self.scenario_counter}"
        self.scenario_counter += 1
        
        affected_services = ["auth-service", "order-service", "gateway"]
        root_cause = "auth-service"
        
        metrics = self._generate_slow_ramp_metrics(affected_services, intensity)
        
        return FailureScenario(
            failure_type=FailureType.AUTH_OVERLOAD,
            failure_shape=shape,
            scenario_id=scenario_id,
            affected_services=affected_services,
            root_cause_service=root_cause,
            affected_endpoints=self.ENDPOINTS_BY_SERVICE.get(root_cause, []),
            metrics=metrics,
            intensity=intensity,
            start_time=random.randint(100, 1000),
            duration=60,
        )
    
    def generate_payment_timeout(self, shape: FailureShape, intensity: float = 0.85) -> FailureScenario:
        """Generate payment timeout (deep chain).
        
        Root cause: Payment service
        Affected: Payment + order + gateway
        """
        scenario_id = f"payment_{shape.value}_{self.scenario_counter}"
        self.scenario_counter += 1
        
        affected_services = ["payment-service", "order-service", "gateway"]
        root_cause = "payment-service"
        
        if shape == FailureShape.CASCADED:
            metrics = self._generate_cascaded_metrics(affected_services, intensity)
        else:
            metrics = self._generate_sudden_spike_metrics(affected_services, intensity)
        
        return FailureScenario(
            failure_type=FailureType.PAYMENT_TIMEOUT,
            failure_shape=shape,
            scenario_id=scenario_id,
            affected_services=affected_services,
            root_cause_service=root_cause,
            affected_endpoints=["/api/payment/checkout", "/api/orders/create"],
            metrics=metrics,
            intensity=intensity,
            start_time=random.randint(100, 1000),
            duration=60,
        )
    
    def generate_sql_injection(self, shape: FailureShape, intensity: float = 0.65) -> FailureScenario:
        """Generate SQL injection / hidden root cause.
        
        Root cause: Malicious query (appears as DB latency + specific endpoint error)
        Affected: DB + particular endpoint
        """
        scenario_id = f"sqli_{shape.value}_{self.scenario_counter}"
        self.scenario_counter += 1
        
        affected_services = ["db", "auth-service", "catalog-service"]
        root_cause = "db"  # Root cause is DB (via malicious query)
        
        if shape == FailureShape.SLOW_INJECTION:
            metrics = self._generate_slow_injection_metrics(affected_services, intensity)
        else:
            metrics = self._generate_slow_ramp_metrics(affected_services, intensity)
        
        return FailureScenario(
            failure_type=FailureType.SQL_INJECTION,
            failure_shape=shape,
            scenario_id=scenario_id,
            affected_services=affected_services,
            root_cause_service=root_cause,
            affected_endpoints=["/api/auth/login", "/api/catalog/search"],
            metrics=metrics,
            intensity=intensity,
            start_time=random.randint(100, 1000),
            duration=60,
        )
    
    def generate_retry_storm(self, shape: FailureShape, intensity: float = 0.9) -> FailureScenario:
        """Generate retry storm (cascading failure).
        
        Root cause: Initial failure in one service triggers retry amplification
        Affected: All services in chain
        """
        scenario_id = f"retry_{shape.value}_{self.scenario_counter}"
        self.scenario_counter += 1
        
        affected_services = ["payment-service", "order-service", "gateway", "auth-service"]
        root_cause = "payment-service"  # Initial failure
        
        metrics = self._generate_retry_amplified_metrics(affected_services, intensity)
        
        return FailureScenario(
            failure_type=FailureType.RETRY_STORM,
            failure_shape=shape,
            scenario_id=scenario_id,
            affected_services=affected_services,
            root_cause_service=root_cause,
            affected_endpoints=["/api/payment/checkout", "/api/orders/create"],
            metrics=metrics,
            intensity=intensity,
            start_time=random.randint(100, 1000),
            duration=60,
        )
    
    # =====================================================================
    # Metric generation helpers
    # =====================================================================
    
    def _generate_slow_ramp_metrics(self, services: List[str], intensity: float) -> Dict:
        """Gradual increase over 30s."""
        metrics = {}
        for service in services:
            metrics[service] = {}
            for endpoint in self.ENDPOINTS_BY_SERVICE.get(service, ["default"]):
                snapshots = []
                for t in range(60):
                    # Ramp up from t=0 to t=30, stay high after
                    severity = min(1.0, t / 30.0) * intensity if t < 30 else intensity
                    
                    p95_latency = 50 + severity * 400  # 50-450ms
                    error_rate = severity * 0.3
                    request_rate = 10 + random.gauss(0, 1)
                    
                    snapshots.append(MetricSnapshot(
                        service=service,
                        endpoint=endpoint,
                        timestamp=t,
                        p95_latency=p95_latency,
                        error_rate=max(0, error_rate),
                        request_rate=max(0, request_rate),
                    ))
                
                metrics[service][endpoint] = snapshots
        
        return metrics
    
    def _generate_sudden_spike_metrics(self, services: List[str], intensity: float) -> Dict:
        """Immediate jump at t=10."""
        metrics = {}
        for service in services:
            metrics[service] = {}
            for endpoint in self.ENDPOINTS_BY_SERVICE.get(service, ["default"]):
                snapshots = []
                for t in range(60):
                    # Jump at t=10
                    severity = intensity if t >= 10 else 0.0
                    
                    p95_latency = 50 + severity * 400
                    error_rate = severity * 0.4
                    request_rate = 10 + random.gauss(0, 1)
                    
                    snapshots.append(MetricSnapshot(
                        service=service,
                        endpoint=endpoint,
                        timestamp=t,
                        p95_latency=p95_latency,
                        error_rate=max(0, error_rate),
                        request_rate=max(0, request_rate),
                    ))
                
                metrics[service][endpoint] = snapshots
        
        return metrics
    
    def _generate_partial_failure_metrics(self, services: List[str], intensity: float) -> Dict:
        """Bimodal distribution (some requests fast, some slow)."""
        metrics = {}
        for service in services:
            metrics[service] = {}
            for endpoint in self.ENDPOINTS_BY_SERVICE.get(service, ["default"]):
                snapshots = []
                for t in range(60):
                    severity = intensity if t >= 10 else 0.0
                    
                    # Bimodal: 50% at baseline, 50% at high latency
                    p95_latency = (50 + severity * 400) if random.random() > 0.5 else 50
                    error_rate = severity * 0.2  # Lower error for partial
                    request_rate = 10 + random.gauss(0, 1)
                    
                    snapshots.append(MetricSnapshot(
                        service=service,
                        endpoint=endpoint,
                        timestamp=t,
                        p95_latency=p95_latency,
                        error_rate=max(0, error_rate),
                        request_rate=max(0, request_rate),
                    ))
                
                metrics[service][endpoint] = snapshots
        
        return metrics
    
    def _generate_intermittent_metrics(self, services: List[str], intensity: float) -> Dict:
        """Flapping every 5-10 seconds."""
        metrics = {}
        for service in services:
            metrics[service] = {}
            for endpoint in self.ENDPOINTS_BY_SERVICE.get(service, ["default"]):
                snapshots = []
                for t in range(60):
                    # Flap every 7-8 seconds
                    is_down = (t // 8) % 2 == 0
                    severity = intensity if is_down and t >= 10 else 0.0
                    
                    p95_latency = 50 + severity * 400
                    error_rate = severity * 0.4
                    request_rate = 10 + random.gauss(0, 1)
                    
                    snapshots.append(MetricSnapshot(
                        service=service,
                        endpoint=endpoint,
                        timestamp=t,
                        p95_latency=p95_latency,
                        error_rate=max(0, error_rate),
                        request_rate=max(0, request_rate),
                    ))
                
                metrics[service][endpoint] = snapshots
        
        return metrics
    
    def _generate_cascaded_metrics(self, services: List[str], intensity: float) -> Dict:
        """Cascades through dependency chain (staggered)."""
        metrics = {}
        for i, service in enumerate(services):
            metrics[service] = {}
            for endpoint in self.ENDPOINTS_BY_SERVICE.get(service, ["default"]):
                snapshots = []
                cascade_delay = i * 3  # Each dependent service affected 3s later
                
                for t in range(60):
                    # Trigger at different times
                    if t >= (10 + cascade_delay):
                        severity = min(intensity, (t - 10 - cascade_delay) / 20.0 * intensity)
                    else:
                        severity = 0.0
                    
                    p95_latency = 50 + severity * 400
                    error_rate = severity * 0.3
                    request_rate = max(1, 10 - severity * 5)  # Request rate drops
                    
                    snapshots.append(MetricSnapshot(
                        service=service,
                        endpoint=endpoint,
                        timestamp=t,
                        p95_latency=p95_latency,
                        error_rate=max(0, error_rate),
                        request_rate=max(0, request_rate),
                    ))
                
                metrics[service][endpoint] = snapshots
        
        return metrics
    
    def _generate_slow_injection_metrics(self, services: List[str], intensity: float) -> Dict:
        """Slowly escalating suspicion (SQL injection pattern)."""
        metrics = {}
        for service in services:
            metrics[service] = {}
            for endpoint in self.ENDPOINTS_BY_SERVICE.get(service, ["default"]):
                snapshots = []
                for t in range(60):
                    # Slow escalation
                    severity = min(intensity, (t - 10) / 40.0) if t > 10 else 0.0
                    
                    p95_latency = 50 + severity * 300
                    error_rate = severity * 0.2
                    request_rate = 10 + random.gauss(0, 1)
                    
                    snapshots.append(MetricSnapshot(
                        service=service,
                        endpoint=endpoint,
                        timestamp=t,
                        p95_latency=p95_latency,
                        error_rate=max(0, error_rate),
                        request_rate=max(0, request_rate),
                    ))
                
                metrics[service][endpoint] = snapshots
        
        return metrics
    
    def _generate_retry_amplified_metrics(self, services: List[str], intensity: float) -> Dict:
        """Request rate amplified by retries."""
        metrics = {}
        for i, service in enumerate(services):
            metrics[service] = {}
            for endpoint in self.ENDPOINTS_BY_SERVICE.get(service, ["default"]):
                snapshots = []
                
                for t in range(60):
                    if t < 10:
                        severity = 0.0
                        request_rate_mult = 1.0
                    else:
                        severity = intensity
                        # Request rate amplified 3-5x by retries
                        request_rate_mult = 3.0 + (t - 10) / 20.0 * 2.0
                    
                    p95_latency = 50 + severity * 400
                    error_rate = severity * 0.5
                    request_rate = 10 * request_rate_mult + random.gauss(0, 1)
                    
                    snapshots.append(MetricSnapshot(
                        service=service,
                        endpoint=endpoint,
                        timestamp=t,
                        p95_latency=p95_latency,
                        error_rate=max(0, error_rate),
                        request_rate=max(0.5, request_rate),
                    ))
                
                metrics[service][endpoint] = snapshots
        
        return metrics


def generate_diverse_scenarios(num_per_type: int = 10, include_combinations: bool = True, 
                              include_edge_cases: bool = True, edge_case_multiplier: float = 2.0,
                              include_normal_cases: bool = True, normal_case_multiplier: float = 2.0) -> List[FailureScenario]:
    """Generate diverse failure scenarios including normal cases, edge cases, and combinations.
    
    Args:
        num_per_type: Base number of scenarios per failure type x shape combination
        include_combinations: Whether to generate failure combinations (e.g., auth+payment)
        include_edge_cases: Whether to generate edge cases (simultaneous, cascading, intermittent)
        edge_case_multiplier: Multiplier for edge case generation (1.0 = normal, 2.0 = double)
        include_normal_cases: Whether to generate normal single-failure cases
        normal_case_multiplier: Multiplier for normal case generation (1.0 = normal, 2.0 = double)
        
    Returns:
        List of 1000+ unique scenarios for training
    """
    gen = ScenarioGenerator()
    scenarios = []
    
    # All 8 failure shapes
    all_shapes = [
        FailureShape.SLOW_RAMP,
        FailureShape.SUDDEN_SPIKE,
        FailureShape.PARTIAL,
        FailureShape.INTERMITTENT,
        FailureShape.CASCADED,
        FailureShape.BIMODAL,
        FailureShape.SLOW_INJECTION,
        FailureShape.RETRY_AMPLIFIED,
    ]
    
    # Intensity variations
    low_intensities = [0.5, 0.6]      # Minor (edge case detection)
    normal_intensities = [0.65, 0.75] # Normal severity
    high_intensities = [0.8, 0.9]     # Severe
    all_intensities = [0.6, 0.75, 0.9]
    
    # ============ NORMAL CASES ============
    # Single clear failures that are easy to diagnose (more training examples)
    if include_normal_cases:
        normal_multiplier = int(num_per_type * normal_case_multiplier)
        
        # DB failures - normal severity patterns
        for shape in [FailureShape.SLOW_RAMP, FailureShape.SUDDEN_SPIKE]:
            for intensity in normal_intensities:
                for _ in range(normal_multiplier):
                    try:
                        scenarios.append(gen.generate_db_failure(shape, intensity))
                    except:
                        pass
        
        # Redis failures - normal severity
        for shape in [FailureShape.SLOW_RAMP, FailureShape.SUDDEN_SPIKE]:
            for intensity in normal_intensities:
                for _ in range(normal_multiplier):
                    try:
                        scenarios.append(gen.generate_redis_failure(shape, intensity))
                    except:
                        pass
        
        # Gateway DDoS - clear patterns
        for shape in [FailureShape.SUDDEN_SPIKE, FailureShape.SLOW_RAMP]:
            for intensity in normal_intensities:
                for _ in range(normal_multiplier):
                    try:
                        scenarios.append(gen.generate_gateway_ddos(shape, intensity))
                    except:
                        pass
        
        # Auth overload - standard patterns
        for shape in [FailureShape.SLOW_RAMP, FailureShape.SUDDEN_SPIKE]:
            for intensity in normal_intensities:
                for _ in range(normal_multiplier):
                    try:
                        scenarios.append(gen.generate_auth_overload(shape, intensity))
                    except:
                        pass
        
        # Payment timeout - standard patterns
        for shape in [FailureShape.SUDDEN_SPIKE, FailureShape.CASCADED]:
            for intensity in normal_intensities:
                for _ in range(normal_multiplier):
                    try:
                        scenarios.append(gen.generate_payment_timeout(shape, intensity))
                    except:
                        pass
        
        # SQL injection - standard patterns
        for shape in [FailureShape.SLOW_INJECTION, FailureShape.SLOW_RAMP]:
            for intensity in [0.6, 0.75]:
                for _ in range(normal_multiplier):
                    try:
                        scenarios.append(gen.generate_sql_injection(shape, intensity))
                    except:
                        pass
        
        # Retry storm - standard patterns
        for shape in [FailureShape.RETRY_AMPLIFIED, FailureShape.CASCADED]:
            for intensity in [0.8, 0.9]:
                for _ in range(normal_multiplier):
                    try:
                        scenarios.append(gen.generate_retry_storm(shape, intensity))
                    except:
                        pass
    
    # ============ EDGE CASES ============
    # Harder to diagnose cases with unusual patterns
    if include_edge_cases:
        edge_multiplier = int(num_per_type * edge_case_multiplier)
        
        # INTERMITTENT failures - flapping (hard to diagnose)
        for failure_type_gen in [gen.generate_db_failure, gen.generate_redis_failure, gen.generate_auth_overload]:
            for intensity in low_intensities + high_intensities:
                for _ in range(edge_multiplier):
                    try:
                        scenarios.append(failure_type_gen(FailureShape.INTERMITTENT, intensity))
                    except:
                        pass
        
        # PARTIAL failures - affect only some traffic (edge case)
        for failure_type_gen in [gen.generate_gateway_ddos, gen.generate_payment_timeout, gen.generate_redis_failure]:
            for intensity in normal_intensities:
                for _ in range(edge_multiplier):
                    try:
                        scenarios.append(failure_type_gen(FailureShape.PARTIAL, intensity))
                    except:
                        pass
        
        # BIMODAL failures - two populations (unusual pattern)
        for failure_type_gen in [gen.generate_db_failure, gen.generate_payment_timeout]:
            for intensity in [0.6, 0.8]:
                for _ in range(edge_multiplier):
                    try:
                        scenarios.append(failure_type_gen(FailureShape.BIMODAL, intensity))
                    except:
                        pass
        
        # CASCADED failures - propagate through dependencies
        for failure_type_gen in [gen.generate_auth_overload, gen.generate_payment_timeout, gen.generate_retry_storm]:
            for intensity in normal_intensities + high_intensities:
                for _ in range(edge_multiplier):
                    try:
                        scenarios.append(failure_type_gen(FailureShape.CASCADED, intensity))
                    except:
                        pass
        
        # SLOW_INJECTION - gradually escalating (hard to detect threshold)
        for failure_type_gen in [gen.generate_sql_injection, gen.generate_gateway_ddos]:
            for intensity in low_intensities + high_intensities:
                for _ in range(edge_multiplier):
                    try:
                        scenarios.append(failure_type_gen(FailureShape.SLOW_INJECTION, intensity))
                    except:
                        pass
        
        # RETRY_AMPLIFIED - cascading request amplification
        for failure_type_gen in [gen.generate_payment_timeout, gen.generate_auth_overload]:
            for intensity in high_intensities:
                for _ in range(edge_multiplier):
                    try:
                        scenarios.append(failure_type_gen(FailureShape.RETRY_AMPLIFIED, intensity))
                    except:
                        pass
        
        # Minor/Low severity edge cases (false positives - need to distinguish)
        for failure_type_gen in [gen.generate_db_failure, gen.generate_redis_failure]:
            for intensity in low_intensities:
                for _ in range(edge_multiplier // 2):
                    try:
                        scenarios.append(failure_type_gen(FailureShape.SUDDEN_SPIKE, intensity))
                    except:
                        pass
    
    # ============ COMBINATIONS (Multi-failure scenarios) ============
    if include_combinations:
        combo_multiplier = int(num_per_type * 1.5)
        
        # Redis + Auth (cache hits auth performance)
        for _ in range(combo_multiplier):
            try:
                scenarios.append(gen.generate_redis_failure(FailureShape.SUDDEN_SPIKE, 0.7))
            except:
                pass
        
        # DB + Gateway (shared load causes DB bottleneck)
        for _ in range(combo_multiplier):
            try:
                scenarios.append(gen.generate_db_failure(FailureShape.SLOW_RAMP, 0.8))
            except:
                pass
        
        # Auth + Payment (auth blocks payment processing)
        for _ in range(combo_multiplier):
            try:
                scenarios.append(gen.generate_auth_overload(FailureShape.CASCADED, 0.75))
            except:
                pass
        
        # Simultaneous failures (same time, different services)
        for _ in range(combo_multiplier):
            try:
                scenarios.append(gen.generate_payment_timeout(FailureShape.SUDDEN_SPIKE, 0.8))
            except:
                pass
    
    return scenarios
