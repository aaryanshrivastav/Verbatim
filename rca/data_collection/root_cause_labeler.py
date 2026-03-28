"""Root cause labeling logic for ML training.

This module implements the LABELING STRATEGY for Module D (ML Ranker) training.

THEORETICAL FRAMEWORK:
======================

When we generate training data for binary classification (is service S the root cause?),
we need a principled way to assign labels. The key insight is that in a distributed
system, a root cause has DISTINCT CHARACTERISTICS compared to secondary (dependent)
services affected by propagation:

1.  TEMPORAL PRIMACY: Root cause service's metrics deviate FIRST (lowest time lag)
2.  PROPAGATION PATTERN: Root cause -> downstream services show cascading delay
3.  SEVERITY CORRELATION: Root cause typically has HIGHEST severity among first-deviators
4.  DEPENDENCY GRAPH: Root cause does NOT depend on other already-failing services
5.  ANOMALY TYPE MATCH: Root cause anomaly type (latency/error) matches symptom origin

LABELING ALGORITHM:
===================

For each synthetic incident scenario with a known root_cause_service:

  For each service S in affected_services:
    1. Extract metrics time-series for S
    2. Detect when S first deviates (earliest timestamp where z-score > threshold)
    3. Compare deviation timing across all services
    4. Compute service confidence score based on:
       - Is this technically the ROOT CAUSE? (check dependency graph)
       - Does it match expected propagation pattern?
       - What's the severity vs other services?
    5. Assign label:
       - label = 1.0 if S == root_cause_service
       - label = 0.0 if S is dependent/secondary
       - label = confidence_score for intermediate/ambiguous cases

CONFIDENCE SCORING:
===================

For synthetic data created by ScenarioGenerator, we KNOW the ground truth (root_cause_service).
So we assign high confidence (0.95+) to known root cause and low (0.05) to known non-causes.

For REAL data from production, the labeling would come from:
  - Incident post-mortem analysis
  - Root cause analysis reports
  - Manual expert review
  - Correlation with known incidents
  - Logs/traces explicitly identifying root cause

EDGE CASES:
===========

1. CASCADED FAILURES: Initial root cause causes secondary failures that look similar
   -> Solution: Use timing (which deviated first) to distinguish

2. SIMULTANEOUS FAILURES: Two independent failures happen at same time
   -> Solution: Each gets labeled separately; model learns they can co-occur

3. AMBIGUOUS PRODUCTION DATA: Not sure which is really root cause
   -> Solution: Create training examples with confidence scores in (0,1)
   -> Model learns to rank probabilities, not just binary classification

4. RECOVERY PATTERNS: After root cause is fixed, dependent services recover
   -> Solution: Label based on ONSET timing, not recovery

TRAINING EXAMPLE FORMAT:
========================

Each training example is:
{
    "example_id": "scenario_db_2_service_catalog",
    "scenario_id": "scenario_db_2",
    "service": "catalog-service",
    "endpoint": "/api/catalog/search",
    "label": 0,                         # 0=not root cause, 1=root cause
    "label_confidence": 0.98,           # How sure are we? [0,1]
    "labeling_rationale": {
        "method": "temporal_primacy",   # How label was determined
        "root_cause_service": "db",     # Known ground truth
        "first_deviation_time": 10,     # When this service first deviated (sec)
        "root_cause_first_time": 10,    # When root cause first deviated
        "severity_at_peak": 0.45,       # Max anomaly severity for this service
        "root_cause_peak_severity": 0.8 # Max severity of actual root cause
    },
    "features": {
        "state_vector": [0, 1, 0, 0, 2, 1],
        "max_latency": 350.5,
        "max_error_rate": 0.28,
        "anomaly_types": ["latency_spike"],
    },
}

This gives the human labeler/reviewer full transparency on HOW and WHY
each example was labeled, enabling refinement if needed.
"""

from typing import Dict, List, Tuple, Any
from dataclasses import dataclass, asdict
import json

from rca.data_collection.synthetic_scenario_generator import FailureScenario, MetricSnapshot


@dataclass
class LabelingRationale:
    """Explains why an example was labeled a certain way."""
    method: str  # e.g., "temporal_primacy", "dependency_graph", "severity_cascade"
    root_cause_service: str
    root_cause_service_endpoint: str
    this_service: str
    this_service_endpoint: str
    
    # Timing analysis
    first_deviation_time_this_service: int  # seconds since incident start
    first_deviation_time_root_cause: int
    time_lag_seconds: int  # (first_dev_this - first_dev_root)
    
    # Severity analysis
    max_severity_this_service: float
    max_severity_root_cause: float
    severity_ratio: float  # max_severity_this / max_severity_root_cause
    
    # Dependency analysis
    depends_on_root_cause: bool
    
    # Summary
    reasoning: str


class RootCauseLabelGenerator:
    """Generates labels for training examples from synthetic scenarios."""
    
    # Service dependency graph (from scenario generator, duplicated here)
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
    
    DEVIATION_THRESHOLD = 2.0  # Z-score threshold for "notable deviation"
    
    def generate_training_examples(
        self,
        scenario: FailureScenario,
    ) -> List[Dict[str, Any]]:
        """Generate training examples from a scenario.
        
        For each service in the scenario, create ONE training example:
        - label=1 if this service is the root cause
        - label=0 if this service is secondary/dependent
        
        Args:
            scenario: FailureScenario with metrics and known root cause
            
        Returns:
            List of training examples (one per affected service)
        """
        training_examples = []
        
        # First pass: analyze deviation timings for all services
        deviation_analysis = self._analyze_deviations(scenario)
        
        # Second pass: create training example for each service
        for service in scenario.affected_services:
            # Find representative endpoint for this service
            endpoint = scenario.affected_endpoints[0] if scenario.affected_endpoints else "/"
            
            is_root_cause = (service == scenario.root_cause_service)
            
            # Generate labeling rationale
            rationale = self._generate_rationale(
                scenario=scenario,
                service=service,
                endpoint=endpoint,
                is_root_cause=is_root_cause,
                deviation_analysis=deviation_analysis,
            )
            
            # Extract features from metrics
            features = self._extract_features(scenario, service, endpoint)
            
            # Confidence score
            if is_root_cause:
                confidence = 0.98  # Very confident about known root cause
            else:
                # For non-root-cause services, confidence depends on clarity
                # If it clearly depends on root cause, confidence is high
                if self._depends_on(service, scenario.root_cause_service):
                    confidence = 0.95
                else:
                    # Coincidental failure or ambiguous, lower confidence
                    confidence = 0.80
            
            label = 1 if is_root_cause else 0
            
            training_example = {
                "example_id": f"{scenario.scenario_id}_{service}",
                "scenario_id": scenario.scenario_id,
                "failure_type": scenario.failure_type.value,
                "failure_shape": scenario.failure_shape.value,
                
                # Classification target
                "service": service,
                "endpoint": endpoint,
                "label": label,                      # 0 or 1
                "label_confidence": confidence,      # [0,1]
                
                # For model
                "features": features,
                
                # Transparent labeling rationale
                "labeling_rationale": asdict(rationale),
            }
            
            training_examples.append(training_example)
        
        return training_examples
    
    def _analyze_deviations(self, scenario: FailureScenario) -> Dict[str, int]:
        """Find when each service first deviates from baseline.
        
        Returns:
            Dict mapping service -> first_deviation_timestamp_seconds
        """
        deviations = {}
        
        for service in scenario.affected_services:
            # Get metrics for this service
            if service not in scenario.metrics:
                deviations[service] = 999  # No data, treat as late
                continue
            
            endpoints_data = scenario.metrics[service]
            if not endpoints_data:
                deviations[service] = 999
                continue
            
            # Use first endpoint's data
            endpoint = list(endpoints_data.keys())[0]
            snapshots: List[MetricSnapshot] = endpoints_data[endpoint]
            
            # Find first deviation (where latency spikes)
            first_dev = 999
            for snap in snapshots:
                # Simple heuristic: deviation occurs when latency > 150ms
                if snap.p95_latency > 150:
                    first_dev = snap.timestamp
                    break
            
            deviations[service] = first_dev
        
        return deviations
    
    def _generate_rationale(
        self,
        scenario: FailureScenario,
        service: str,
        endpoint: str,
        is_root_cause: bool,
        deviation_analysis: Dict[str, int],
    ) -> LabelingRationale:
        """Generate transparent labeling rationale."""
        
        this_first_dev = deviation_analysis.get(service, 999)
        root_first_dev = deviation_analysis.get(scenario.root_cause_service, 999)
        
        # Get max severity
        this_max_severity = self._get_max_severity(scenario, service, endpoint)
        root_max_severity = self._get_max_severity(scenario, scenario.root_cause_service, endpoint)
        
        depends_on_root = self._depends_on(service, scenario.root_cause_service)
        
        # Build reasoning
        if is_root_cause:
            reasoning = f"Service {service} is the identified root cause of {scenario.failure_type.value} ({scenario.failure_shape.value})"
        elif depends_on_root:
            reasoning = f"Service {service} depends on root cause ({scenario.root_cause_service}) and was affected {this_first_dev - root_first_dev}s later"
        else:
            reasoning = f"Service {service} was affected but does not depend on root cause; likely coincidental or secondary effect"
        
        return LabelingRationale(
            method="temporal_primacy_and_dependency",
            root_cause_service=scenario.root_cause_service,
            root_cause_service_endpoint=endpoint,
            this_service=service,
            this_service_endpoint=endpoint,
            first_deviation_time_this_service=this_first_dev,
            first_deviation_time_root_cause=root_first_dev,
            time_lag_seconds=this_first_dev - root_first_dev,
            max_severity_this_service=this_max_severity,
            max_severity_root_cause=root_max_severity,
            severity_ratio=this_max_severity / root_max_severity if root_max_severity > 0 else 0,
            depends_on_root_cause=depends_on_root,
            reasoning=reasoning,
        )
    
    def _depends_on(self, service: str, target: str) -> bool:
        """Check if service depends on target using dependency graph."""
        deps = self.DEPENDENCY_GRAPH.get(service, [])
        return target in deps
    
    def _get_max_severity(self, scenario: FailureScenario, service: str, endpoint: str) -> float:
        """Get maximum severity for a service/endpoint."""
        if service not in scenario.metrics:
            return 0.0
        
        endpoints = scenario.metrics[service]
        if endpoint not in endpoints:
            # Use first endpoint
            endpoint = list(endpoints.keys())[0] if endpoints else None
            if not endpoint:
                return 0.0
        
        snapshots: List[MetricSnapshot] = endpoints[endpoint]
        
        max_severity = 0.0
        for snap in snapshots:
            # Severity = combo of latency and error
            latency_severity = min(1.0, (snap.p95_latency - 50) / 400.0)  # 50->0, 450->1
            error_severity = snap.error_rate
            combined = 0.6 * latency_severity + 0.4 * error_severity
            max_severity = max(max_severity, combined)
        
        return max_severity
    
    def _extract_features(
        self,
        scenario: FailureScenario,
        service: str,
        endpoint: str,
    ) -> Dict[str, Any]:
        """Extract features from metrics for ML input."""
        
        if service not in scenario.metrics or endpoint not in scenario.metrics[service]:
            return {
                "max_latency": 50.0,
                "max_error_rate": 0.0,
                "mean_latency": 50.0,
                "anomaly_types": [],
                "state_vector": [0, 0, 0, 0, 0, 0],
            }
        
        snapshots: List[MetricSnapshot] = scenario.metrics[service][endpoint]
        
        # Compute statistics
        latencies = [s.p95_latency for s in snapshots]
        errors = [s.error_rate for s in snapshots]
        
        max_latency = max(latencies)
        max_error = max(errors)
        mean_latency = sum(latencies) / len(latencies)
        
        # Determine anomaly types
        anomaly_types = []
        if max_latency > 150:
            anomaly_types.append("latency_spike")
        if max_error > 0.1:
            anomaly_types.append("error_spike")
        
        # Create state vector (simplified: 6 services -> 6 states)
        # State: 0=healthy, 1=degraded, 2=critical
        state_vector = self._compute_state_vector(snapshots)
        
        return {
            "max_latency": float(max_latency),
            "max_error_rate": float(max_error),
            "mean_latency": float(mean_latency),
            "anomaly_types": anomaly_types,
            "state_vector": state_vector,
        }
    
    def _compute_state_vector(self, snapshots: List[MetricSnapshot]) -> List[int]:
        """Compute state vector from metrics (similar to Module C)."""
        state = []
        
        max_latency = max(s.p95_latency for s in snapshots)
        max_error = max(s.error_rate for s in snapshots)
        
        # Critical: latency > 300ms or error > 0.3
        if max_latency > 300 or max_error > 0.3:
            state = [2]
        # Degraded: latency > 150ms or error > 0.1
        elif max_latency > 150 or max_error > 0.1:
            state = [1]
        # Healthy
        else:
            state = [0]
        
        # Pad to 6 (matching fixed service set)
        while len(state) < 6:
            state.append(0)
        
        return state[:6]
    
    def generate_incident_training_example(self, scenario: FailureScenario) -> Dict[str, Any]:
        """Generate training example in Component 2 incident format.
        
        This matches the real event/incident structure from detection/models.py:
        - incident: incident_id, endpoint, time_window, anomalies[]
        - labels: service-level labels with confidence and reasoning
        
        Args:
            scenario: FailureScenario with metrics and known root cause
            
        Returns:
            Dict with "incident" and "labels" keys in Component 2 format
        """
        from datetime import datetime, timedelta
        
        # Create incident metadata
        incident_id = f"inc-{scenario.scenario_id}"
        endpoint = scenario.affected_endpoints[0] if scenario.affected_endpoints else "/api/default"
        
        # Use scenario timestamp as incident time
        base_time = datetime(2026, 3, 28, 11, 15, 5)
        time_window_start = (base_time - timedelta(seconds=10)).isoformat() + "Z"
        time_window_end = base_time.isoformat() + "Z"
        
        # Convert scenario metrics to Component 2 events (anomalies)
        anomalies = []
        anomaly_analysis = self._analyze_deviations(scenario)
        
        for service in scenario.affected_services:
            # Get max severity for this service
            max_severity = self._get_max_severity(scenario, service, endpoint)
            
            # Get anomaly types
            if service not in scenario.metrics or endpoint not in scenario.metrics[service]:
                latency_score = 0.0
                error_score = 0.0
                anomaly_type = "unknown"
            else:
                snapshots = scenario.metrics[service][endpoint]
                
                # Calculate scores
                max_latency = max(s.p95_latency for s in snapshots)
                max_error = max(s.error_rate for s in snapshots)
                
                # Latitude and error scores (0-1)
                latency_score = min(1.0, (max_latency - 50) / 400.0)
                error_score = min(1.0, max_error / 1.0)
                
                # Determine primary anomaly type
                if max_latency > 150 and max_error > 0.1:
                    anomaly_type = "mixed"
                elif max_latency > 150:
                    anomaly_type = "latency_spike"
                elif max_error > 0.1:
                    anomaly_type = "error_spike"
                else:
                    anomaly_type = "minor_anomaly"
            
            # Detected at is when first deviation occurred
            detected_at_offset = anomaly_analysis.get(service, 10)
            detected_at = (base_time - timedelta(seconds=10 - detected_at_offset)).isoformat() + "Z"
            
            event = {
                "service": service,
                "endpoint": endpoint,
                "anomaly_type": anomaly_type,
                "severity": round(max_severity, 3),
                "detected_at": detected_at,
                "latency_score": round(latency_score, 2),
                "error_score": round(error_score, 2),
            }
            
            anomalies.append(event)
        
        # Create incident
        incident = {
            "incident_id": incident_id,
            "endpoint": endpoint,
            "time_window_start": time_window_start,
            "time_window_end": time_window_end,
            "anomalies": anomalies,
        }
        
        # Generate labels for each service
        deviation_analysis = anomaly_analysis
        labels = []
        
        for service in scenario.affected_services:
            is_root_cause = (service == scenario.root_cause_service)
            
            # Generate labeling rationale
            rationale = self._generate_rationale(
                scenario=scenario,
                service=service,
                endpoint=endpoint,
                is_root_cause=is_root_cause,
                deviation_analysis=deviation_analysis,
            )
            
            # Confidence score
            if is_root_cause:
                confidence = 0.98
            else:
                if self._depends_on(service, scenario.root_cause_service):
                    confidence = 0.95
                else:
                    confidence = 0.80
            
            label = 1 if is_root_cause else 0
            
            label_entry = {
                "service": service,
                "endpoint": endpoint,
                "label": label,  # 1 = root cause, 0 = not root cause
                "confidence": confidence,
                "method": rationale.method,
                "reasoning": rationale.reasoning,
                "details": {
                    "root_cause_service": rationale.root_cause_service,
                    "time_lag_seconds": rationale.time_lag_seconds,
                    "severity_ratio": round(rationale.severity_ratio, 3),
                    "depends_on_root_cause": rationale.depends_on_root_cause,
                }
            }
            
            labels.append(label_entry)
        
        # Add scenario metadata for reference
        return {
            "incident": incident,
            "labels": labels,
            "scenario_metadata": {
                "scenario_id": scenario.scenario_id,
                "failure_type": scenario.failure_type.value,
                "failure_shape": scenario.failure_shape.value,
                "root_cause_service": scenario.root_cause_service,
            }
        }
