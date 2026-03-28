"""Generate unlabeled synthetic incident data for end-to-end pipeline testing.

This generator creates realistic incidents (from Component 2 detection)
WITHOUT labels, representing what the detection module would output.
"""

import json
import random
import sys
import io
from datetime import datetime, timedelta
from typing import List
from rca.models import Incident, AnomalyDetail

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


# Service topology
SERVICES = [
    "frontend", "gateway", "auth-service", "catalog-service",
    "order-service", "payment-service", "redis", "db"
]

# Logical groupings
FRONTEND_LAYER = ["frontend"]
GATEWAY_LAYER = ["gateway"]
SERVICE_LAYER = ["auth-service", "catalog-service", "order-service", "payment-service"]
DATA_LAYER = ["redis", "db"]

# Anomaly propagation patterns (how anomalies spread through the system)
ANOMALY_PATTERNS = {
    "db_failure": ["db", "payment-service", "order-service", "gateway"],
    "cache_failure": ["redis", "auth-service", "catalog-service", "gateway"],
    "auth_failure": ["auth-service", "gateway", "frontend"],
    "payment_failure": ["payment-service", "order-service", "gateway"],
    "catalog_failure": ["catalog-service", "gateway"],
    "cascade": ["frontend", "gateway", "auth-service", "catalog-service", "payment-service"],
    "isolated": ["order-service"],
    "gateway_degradation": ["gateway", "frontend"],
}

# Endpoints
ENDPOINTS = [
    "/api/checkout",
    "/api/auth/login",
    "/api/products",
    "/api/orders",
    "/api/payment/charge",
    "/health",
]

# Anomaly types
ANOMALY_TYPES = ["latency_spike", "error_spike", "mixed"]


def generate_incident(
    incident_id: str,
    timestamp: datetime,
    pattern_name: str = None,
    intensity: float = None,
) -> Incident:
    """Generate a single incident with anomalies.
    
    Args:
        incident_id: Unique incident ID
        timestamp: Incident occurrence time
        pattern_name: Type of anomaly pattern (random if None)
        intensity: Severity multiplier (random if None)
        
    Returns:
        Incident with anomalies (no labels)
    """
    if pattern_name is None:
        pattern_name = random.choice(list(ANOMALY_PATTERNS.keys()))
    
    if intensity is None:
        intensity = random.uniform(0.5, 1.0)
    
    # Services affected by this incident
    affected_services = ANOMALY_PATTERNS[pattern_name]
    
    # Generate anomalies for each affected service
    anomalies = []
    for i, service in enumerate(affected_services):
        # Severity decreases as anomaly propagates
        base_severity = 0.7 + (0.3 * intensity)
        severity = base_severity * (1.0 - i * 0.15)  # Decay
        severity = max(0.4, min(1.0, severity))  # Clamp to [0.4, 1.0]
        
        anomaly = AnomalyDetail(
            service=service,
            severity=severity,
            anomaly_type=random.choice(ANOMALY_TYPES),
        )
        anomalies.append(anomaly)
    
    # Create incident
    time_window_start = timestamp
    time_window_end = timestamp + timedelta(seconds=10)
    
    incident = Incident(
        incident_id=incident_id,
        endpoint=random.choice(ENDPOINTS),
        time_window_start=time_window_start,
        time_window_end=time_window_end,
        anomalies=anomalies,
    )
    
    return incident


def generate_unlabeled_dataset(
    count: int = 150,
    output_file: str = "training_data/unlabeled_incidents.jsonl",
) -> int:
    """Generate unlabeled incident dataset.
    
    Args:
        count: Number of incidents to generate (100-200)
        output_file: Output file path
        
    Returns:
        Number of incidents generated
    """
    if not (100 <= count <= 200):
        print(f"⚠ Warning: count should be 100-200, using {count}")
    
    # Varied distribution of patterns
    patterns = list(ANOMALY_PATTERNS.keys())
    intensities = [0.5, 0.7, 0.85, 1.0]
    
    incidents = []
    base_time = datetime(2026, 3, 28, 10, 0, 0)
    
    for i in range(count):
        incident_id = f"inc-unlabeled-{i+1:04d}"
        
        # Vary incident timing (spread over ~2 hours)
        timestamp = base_time + timedelta(minutes=random.randint(0, 120))
        
        # Mix of different patterns and intensities
        pattern = patterns[i % len(patterns)]
        intensity = intensities[i % len(intensities)]
        
        incident = generate_incident(
            incident_id=incident_id,
            timestamp=timestamp,
            pattern_name=pattern,
            intensity=intensity,
        )
        incidents.append(incident)
    
    # Write to JSONL format
    with open(output_file, 'w') as f:
        for incident in incidents:
            json.dump(incident_to_dict(incident), f)
            f.write('\n')
    
    print(f"[OK] Generated {count} unlabeled incidents -> {output_file}")
    
    # Print summary
    pattern_counts = {}
    for incident in incidents:
        # Infer pattern from services
        for pattern, services in ANOMALY_PATTERNS.items():
            if all(s in [a.service for a in incident.anomalies] for s in services[:2]):
                pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
                break
    
    print(f"\nPattern distribution:")
    for pattern, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
        print(f"  {pattern}: {count}")
    
    return len(incidents)


def incident_to_dict(incident: Incident) -> dict:
    """Convert Incident to JSON-serializable dict."""
    return {
        "incident_id": incident.incident_id,
        "endpoint": incident.endpoint,
        "time_window_start": incident.time_window_start.isoformat(),
        "time_window_end": incident.time_window_end.isoformat(),
        "anomalies": [
            {
                "service": anom.service,
                "severity": anom.severity,
                "anomaly_type": anom.anomaly_type,
            }
            for anom in incident.anomalies
        ],
    }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate unlabeled incident data")
    parser.add_argument(
        "--count",
        type=int,
        default=150,
        help="Number of incidents to generate (100-200)",
    )
    parser.add_argument(
        "--output",
        default="training_data/unlabeled_incidents.jsonl",
        help="Output file path",
    )
    
    args = parser.parse_args()
    
    count = generate_unlabeled_dataset(
        count=args.count,
        output_file=args.output,
    )
    
    print(f"\n[OK] Dataset ready for pipeline processing")
    print(f"  Run: python rca/run_full_pipeline.py --input {args.output}")
