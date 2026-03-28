"""
# Part 2: Integration with Part 1 (Observability) and Part 3 (RCA)

## System Architecture

```
PART 1: OBSERVABILITY (OpenTelemetry, Prometheus)
├── Microservices emit metrics/traces/logs
├── OTel Collector aggregates
└── Prometheus stores metrics

    PART 2: DETECTION (This Module)
    ├── Input: Prometheus metrics
    ├── Process: Z-score anomaly scoring
    ├── Output: AnomalyEvent + Incident
    └── Delay: 3–6 seconds end-to-end

        PART 3: RCA (Root Cause Analysis - TODO)
        ├── Input: Incident (service, endpoint, time window)
        ├── Process: Query traces/logs for root cause
        ├── Output: Root cause diagnosis
        └── Action: Alert, auto-remediate, etc.
```

## Data Flow

```
Step 1: Microservice generates telemetry
┌─────────────────────────────┐
│  payment-service /checkout  │
│  - HTTP request duration: 523ms
│  - HTTP status: 500
│  - Request rate: 42 req/sec
└──────────────┬──────────────┘
               │ OTLP/gRPC + HTTP
               ↓

Step 2: OTel Collector (Part 1)
┌─────────────────────────────┐
│  OTel Collector             │
│  - Receives traces, metrics │
│  - Exports to Jaeger        │
│  - Exports to Prometheus    │
│  - Exports to Loki          │
└──────────────┬──────────────┘
               │ Prometheus scrape (1-2s)
               ↓

Step 3: Anomaly Detection (Part 2) ← YOU ARE HERE
┌─────────────────────────────┐
│  Prometheus metrics         │
│  ├─ p95_latency: 0.520s     │
│  ├─ error_rate: 0.15        │
│  └─ request_rate: 42 req/s  │
└──────────────┬──────────────┘
               │ Every 1 second
               ↓
     ┌─────────────────────┐
     │  Anomaly Detector  │
     │  ├─ Z-score        │
     │  ├─ Severity       │
     │  └─ Trigger        │
     └────────────┬────────┘
                 │
              Severity=0.91, type=mixed
                 │
     ┌─────────────────────┐
     │ Event Emission      │
     │ AnomalyEvent{       │
     │   service: payment, │
     │   endpoint: /check, │
     │   severity: 0.91,   │
     │   type: mixed       │
     │ }                   │
     └────────────┬────────┘
                 │
     ┌─────────────────────┐
     │ Clustering          │
     │ Incident{           │
     │   endpoint: /check, │
     │   services: [pay...│
     │   max_sev: 0.91    │
     │ }                   │
     └────────────┬────────┘
                 │
                 ↓

Step 4: RCA System (Part 3) ← TO BE IMPLEMENTED
┌─────────────────────────────┐
│  Query Jaeger traces        │
│  payment-service → db call  │
│    status: 500              │
│    duration: 2s (timeout)   │
│                             │
│  Root Cause:                │
│    Database connection pool │
│    exhausted                │
│                             │
│  Action:                    │
│    Alert on-call            │
│    Auto-restart DB service  │
│    Or: scale up pool size   │
└─────────────────────────────┘
```

## Integration Points

### From Part 1 (Output)

The detection module **consumes**:

**Prometheus Metrics:**
```
http_request_duration_seconds (histogram)
  Labels: service_name, http_route, http_status_code
  Used by: detector → DerivedMetricsComputer → histogram_quantile(0.95)

http_request_total (counter)
  Labels: service_name, http_route, http_status_code
  Used by: detector → DerivedMetricsComputer → rate() and error_rate
```

**Assumption**: Part 1 (OpenTelemetry) correctly:
- Instruments all microservices
- Exports metrics to Prometheus
- Uses consistent label names
- Scrapes at regular intervals (every 1–2 seconds)

### To Part 3 (Input)

The detection module **produces**:

**Incident Objects:**
```python
Incident:
    incident_id: "inc-a3b2c1d0"
    endpoint: "/checkout"  # Which API endpoint was affected
    time_window_start: 2026-03-28T01:15:00Z
    time_window_end: 2026-03-28T01:15:10Z
    affected_services: ["payment-service", "catalog-service"]
    anomalies: [
        {service: "payment", severity: 0.91, type: "latency_spike"},
        {service: "catalog", severity: 0.78, type: "error_spike"}
    ]
```

Part 3 (RCA) consumes this and:
1. Queries Jaeger traces for affected services in time window
2. Queries Loki logs for errors
3. Builds dependency graph
4. Diagnoses root cause
5. Triggers remediation

### Glue Code Example

```python
from detection import DetectionService, DetectionConfig
from rca import RCAEngine  # Part 3 (to be implemented)

# Initialize both systems
detection = DetectionService(DetectionConfig.from_env())
rca_engine = RCAEngine(jaeger_url="http://jaeger:16686", ...)

# Main loop
while True:
    # Part 2: Detect anomalies
    result = detection.tick()
    
    # Forward incidents to Part 3
    for incident in result["incidents"]:
        diagnosis = rca_engine.diagnose(incident)
        
        # diagnosis = {
        #     "root_cause": "DB connection pool exhausted",
        #     "affected_services": ["payment-service"],
        #     "recommended_action": "scale payment-service DB pool",
        #     "traces": [...],
        #     "logs": [...]
        # }
        
        print(f"Incident {incident['incident_id']}: {diagnosis['root_cause']}")
        
        # Trigger alerting, auto-remediation, etc.
        alert_oncall(diagnosis)
        maybe_auto_remediate(diagnosis)
    
    time.sleep(detection.config.poll_interval_seconds)
```

## Configuration Alignment

### Part 1 → Part 2

**OTel Metrics must have these labels:**

```
http_request_duration_seconds{
  service_name="payment-service",  ← Part 2 reads: service_label
  http_route="/checkout",          ← Part 2 reads: endpoint_label
  http_status_code="500"           ← Part 2 reads: status_label
}
```

**Part 2 must configure**:

```python
# detection/config.py
service_label = "service_name"      # Match OTel instrumentation
endpoint_label = "http_route"       # Match OTel instrumentation
status_label = "http_status_code"   # Match OTel instrumentation
```

If labels don't match, detector returns empty metrics.

### Part 2 → Part 3

**Incident message schema fixed:**

```python
# All fields from Part 2:
{
    "incident_id": str,
    "endpoint": str,
    "time_window_start": datetime,
    "time_window_end": datetime,
    "affected_services": List[str],
    "anomalies": List[{
        "service": str,
        "severity": float,
        "anomaly_type": str,  # "latency_spike", "error_spike", "mixed"
        "detected_at": datetime
    }]
}

# Part 3 must handle:
# - latency_spike: query traces for slow calls
# - error_spike: query logs for errors
# - mixed: both
```

## Deployment Architecture

### Development (1 VM)

```
┌─────────────────┐
│ Docker Desktop  │
├─────────────────┤
│ - OTel Collector│ (Part 1)
│ - Prometheus    │ (Part 1)
│ - Microservices │ (Your app)
├─────────────────┤
│ - Detector:8000 │ (Part 2) ← Python Flask/FastAPI
│ - Jaeger        │ (Part 3 support)
│ - Loki          │ (Part 3 support)
└─────────────────┘
```

### Production (Multiple VMs)

```
┌────────────────────────────┐
│ Observability Tier         │ (Part 1)
├────────────────────────────┤
│ - OTel Collector (cluster) │
│ - Prometheus (HA)          │
│ - Thanos (long-term)       │
│ - Jaeger (cluster)         │
│ - Loki (cluster)           │
└────────────┬───────────────┘
             │
┌────────────────────────────┐
│ Detection Tier             │ (Part 2)
├────────────────────────────┤
│ - Detector Pod #1          │
│ - Detector Pod #2 (HA)     │
│ - Detector Pod #3 (HA)     │
│ Scaling: 1 pod per 500     │
│          service/endpoints │
└────────────┬───────────────┘
             │
┌────────────────────────────┐
│ RCA / Action Tier          │ (Part 3)
├────────────────────────────┤
│ - RCA Engine               │
│ - Alert Manager            │
│ - Auto-remediation         │
│ - Dashboard (Grafana)      │
└────────────────────────────┘
```

## Verification Matrix

| Check | Part 1 | Part 2 | Part 3 |
|-------|--------|--------|--------|
| Prometheus metrics exist | ✅ Emit | ← Consumes | |
| Label names match | ✅ Define | ← Must match | |
| Sample rate > 0 | ✅ Guarantee | ← Verify | |
| Warmup period | N/A | ✅ 10 min | ← Wait for |
| Incident JSON format | | ✅ Generate | ← Parse |
| Trace correlation | | | ← Lookup |
| Root cause diagnosis | | | ✅ Output |

## Testing Integration

### Integration Test

```python
"""Test that Part 2 correctly consumes Part 1 metrics."""

def test_detection_with_prometheus():
    # Verify Prometheus is running and has metrics
    client = PrometheusClient("http://localhost:9090")
    latencies = client.get_p95_latency_by_service_endpoint()
    assert len(latencies) > 0, "No metrics in Prometheus"
    
    # Verify label names match config
    config = DetectionConfig()
    for (service, endpoint), latency in latencies.items():
        assert service != "unknown"
        assert endpoint != "unknown"
    
    # Verify detector can ingest
    detector = AnomalyDetector(config)
    events, incidents = detector.tick()
    
    # Should not crash; might not have anomalies yet
    assert isinstance(events, list)
    assert isinstance(incidents, list)
    
    print("✅ Part 2 correctly consumes Part 1 metrics")


def test_rca_consumes_incidents():
    """Test that Part 3 can consume Part 2 incidents."""
    
    # Create a synthetic incident
    from detection.models import Incident, IncidentAnomaly, AnomalyType
    from datetime import datetime, timedelta
    
    incident = Incident(
        incident_id="test-001",
        endpoint="/checkout",
        time_window_start=datetime.utcnow() - timedelta(seconds=5),
        time_window_end=datetime.utcnow(),
        anomalies=[
            IncidentAnomaly(
                service="payment-service",
                severity=0.91,
                anomaly_type=AnomalyType.LATENCY_SPIKE,
                detected_at=datetime.utcnow()
            )
        ]
    )
    
    # RCA should be able to handle this
    rca = RCAEngine(...)  # Part 3 connector
    diagnosis = rca.diagnose(incident)
    
    assert diagnosis is not None
    assert "root_cause" in diagnosis
    
    print("✅ Part 3 correctly consumes Part 2 incidents")
```

## Troubleshooting Cross-Component Issues

| Problem | Diagnosis | Solution |
|---------|-----------|----------|
| Detector reports "no metrics" | Prometheus unhealthy | Check Prometheus metrics endpoint |
| Label mismatches | Detector silent | Verify OTel instrument label names |
| Incident never reaches RCA | Detector not emitting | Check warmup period, thresholds |
| RCA can't query traces | Jaeger unreachable | Check Jaeger URL in Part 3 config |
| Alert spam from Detection | Thresholds too low | Increase L_THRESH, E_THRESH |

## Monitoring the Monitoring

Add these metrics **about** the detector itself:

```python
# detection/metrics.py (hypothetical)
detector_ticks_total = Counter(
    "detector_ticks_total",
    "Number of detection ticks"
)
detector_events_total = Counter(
    "detector_events_total",
    "Total anomaly events emitted",
    ["service", "anomaly_type"]
)
detector_incidents_total = Counter(
    "detector_incidents_total",
    "Total incidents created"
)
detector_prometheus_query_duration_seconds = Histogram(
    "detector_prometheus_query_duration_seconds",
    "Time to query Prometheus"
)
```

Query these in Prometheus to verify detector health:

```promql
# Detector is running?
rate(detector_ticks_total[5m]) > 0

# Detector is detecting anomalies?
rate(detector_events_total[5m]) > 0

# Detector query latency acceptable?
histogram_quantile(0.95, detector_prometheus_query_duration_seconds_bucket) < 5

# Not alerting on everything?
(rate(detector_events_total[5m]) / rate(detector_ticks_total[5m])) < 0.1
```

## Next Steps

1. **Deploy Part 2** (this detector)
   - Verify metrics flow from Part 1
   - Tune thresholds for your workload
   - Monitor warmup period

2. **Integrate Part 3** (RCA system)
   - Implement RCAEngine to consume incidents
   - Query Jaeger traces for root cause
   - Connect alerting / auto-remediation

3. **Operations**
   - Monitor detector health metrics
   - Create dashboards for incidents
   - Run incident post-mortems regularly
   - Refine thresholds as behavior evolves

## See Also

- [detection/README.md](README.md) – Full detector documentation
- [detection/IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) – Deep dive
- [../observability/OTEL_PIPELINE_GUIDE.md](../observability/OTEL_PIPELINE_GUIDE.md) – Part 1 setup
- [detection/models.py](models.py) – Data models
"""

# Integration guide for Parts 1, 2, and 3 of the observability system.
