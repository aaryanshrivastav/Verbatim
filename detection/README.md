"""Anomaly Detection Module - README

## Overview

This module provides **production-ready anomaly detection** for microservices.

### Core Principle: DETECTION ONLY

This is a **metrics-only detection engine**. It:
- ✅ Detects: "Which services are anomalous right now?"
- ❌ Does NOT diagnose: "Why is this service broken?" (that's RCA)
- ❌ Uses NO traces or logs for triggering
- ❌ Uses NO causal inference

**Boundary**: Detection outputs events. Incidents group events. RCA consumes incidents.

## Architecture

### Components

1. **MetricsSource (Prometheus)**
   - Fetches metrics via HTTP API
   - Extracts p95_latency, error_rate, request_rate

2. **StreamState (Per-Service Ring Buffers)**
   - Maintains rolling window (60 values, ~60 seconds)
   - Stores (service, endpoint, metric_type)

3. **RollingStats**
   - Computes mean and std from ring buffer
   - Used for z-score normalization

4. **AnomalyScorer**
   - Z-score: (value - mean) / (std + epsilon)
   - Normalized score: min(1.0, |z| / Z_max)
   - Severity: 0.6 * latency_score + 0.4 * error_score

5. **TriggerLogic**
   - Latency anomaly: score_latency >= L_thresh (default 0.5)
   - Error anomaly: score_error >= E_thresh (default 0.5)
   - Combined: (latency AND error) OR severe (severity >= S_severe, default 0.8)

6. **AnomalyEvent**
   - Emitted when trigger condition met
   - Contains: service, endpoint, anomaly_type, severity, timestamp

7. **IncidentCluster**
   - Groups events by endpoint + time window
   - Incident key: (endpoint, 10-second window)
   - All services in window join incident

### Data Flow

```
Prometheus
    ↓ (1 query/sec)
[p95_latency, error_rate, request_rate]
    ↓
per-{service, endpoint} state:
  - RingBuffer(60 values)
  - rolling_mean, rolling_std
    ↓
Scoring (per stream):
  - z_score = (current - mean) / (std + 1e-6)
  - score = min(1.0, |z| / 3.0)
    ↓
Severity (per {service, endpoint}):
  - severity = 0.6 * latency_score + 0.4 * error_score
    ↓
Trigger (if NOT in warmup):
  - emit if (latency_anomaly AND error_anomaly) OR severe
    ↓
AnomalyEvent
    ↓
IncidentCluster:
  - group by (endpoint, 10-sec window)
    ↓
Incident (for RCA)
```

## Formulas

### Z-Score

```
z = (x - μ) / (σ + ε)
```

- x: current metric value
- μ: rolling mean (last 60 values)
- σ: rolling std dev (last 60 values)
- ε: epsilon (1e-6) to avoid division by zero

### Normalized Score

```
score = min(1.0, |z| / Z_max)
```

- Maps z-score to [0, 1]
- Typical Z_max = 3.0 (3 standard deviations = ~99.7% of values under normal distribution)

### Severity

```
severity = clip[0,1](0.6 * latency_score + 0.4 * error_score)
```

- Weighted combination of two streams
- 60% latency, 40% error (tunable)

### Triggers

**Latency Anomaly:**
- `score_latency >= L_thresh` (default 0.5)

**Error Anomaly:**
- `score_error >= E_thresh` (default 0.5)

**Emit Event If:**
- `(latency_anomaly AND error_anomaly) OR severity >= S_severe`

## Configuration

All settings via environment variables. Defaults provided:

```bash
# Prometheus connection
PROMETHEUS_BASE_URL=http://localhost:9090

# Anomaly thresholds
L_THRESH=0.5              # Latency trigger
E_THRESH=0.5              # Error rate trigger
S_SEVERE=0.8              # Severity trigger

# Statistical parameters
WINDOW_SIZE=60            # Rolling buffer (seconds)
Z_MAX=3.0                 # Z-score clipping
LATENCY_WEIGHT=0.6        # Severity weight
ERROR_WEIGHT=0.4          # Severity weight

# Timing
WARMUP_SECONDS=600        # First 10 min: baseline only
CLUSTER_WINDOW_SECONDS=10 # Incident grouping window
POLL_INTERVAL_SECONDS=1   # Detection loop frequency

# Deduplication
DEDUP_COOLDOWN_SECONDS=30 # Re-emit same anomaly after 30s
```

## Behavior

### Warm-Up Period (First 10 Minutes)

During first 600 seconds:
- Build buffers
- Compute baseline (mean/std)
- Store baseline state
- **DO NOT emit events**

After warm-up:
- Normal trigger logic applies
- Baseline is frozen; drift detection on rolling window

### Latency Target

- Prometheus scrape: 1–2s
- Rolling window refresh: 3–5s
- Detection compute: <1s
- **End-to-end target: 3–6 seconds**

### Deduplication & Cooldown

Same anomaly repeated = suppressed for `DEDUP_COOLDOWN_SECONDS` (default 30s).
Prevents alert storms for steady-state anomalies.

Reset on state change:
- Anomaly clears → emit clear event after cooldown
- Anomaly returns → emit new event

## Metric Streams

**Per {service, endpoint, metric_type}:**

### p95_latency
- Derived from: `http_request_duration_seconds` histogram
- Query: `histogram_quantile(0.95, rate(..._bucket[1m]))`
- Range: [0, ∞) seconds
- Anomalous if: Z-score high (unexpected latency spike)

### error_rate
- Derived from: `http_request_total` counter with status codes
- Calculation: `(5xx_errors) / (total_requests)`
- Range: [0, 1]
- Anomalous if: Z-score high (unexpected error spike)

### request_rate (debug only)
- Not used in triggers
- Stored in event metadata
- Useful for dashboards and post-mortems

## Usage

### Standalone

```bash
# Run detection loop
python -m detection.main \
  --prometheus-url http://localhost:9090 \
  --log-level INFO \
  --poll-interval 1 \
  --output-file /tmp/detection_results.jsonl

# With custom thresholds
python -m detection.main \
  --l-thresh 0.4 --e-thresh 0.6 --s-severe 0.75

# Testing: 10 iterations only
python -m detection.main --max-iterations 10
```

### Embedded (Python Module)

```python
from detection import DetectionConfig, DetectionService

# Build config
config = DetectionConfig(
    prometheus_base_url="http://prometheus:9090",
    latency_threshold=0.5,
    error_threshold=0.5,
    severity_threshold=0.8,
    warmup_seconds=600
)

# Create service
service = DetectionService(config)

# Run detection tick
result = service.tick()

# result.events: List of new AnomalyEvent
# result.incidents: List of new Incident
# result.warmup_remaining_seconds: Seconds until warm-up done
# result.in_warmup: Boolean flag
```

## Output Models

### AnomalyEvent

```json
{
  "service": "payment-service",
  "endpoint": "/checkout",
  "anomaly_type": "latency_spike",
  "severity": 0.91,
  "timestamp": "2026-03-28T01:15:05Z",
  "latency_score": 0.85,
  "error_score": 0.60
}
```

### Incident

```json
{
  "incident_id": "inc-a3b2c1d0",
  "endpoint": "/checkout",
  "time_window_start": "2026-03-28T01:15:00Z",
  "time_window_end": "2026-03-28T01:15:10Z",
  "max_severity": 0.91,
  "affected_services": ["payment-service", "catalog-service"],
  "anomaly_count": 2,
  "anomalies": [
    {
      "service": "payment-service",
      "severity": 0.91,
      "anomaly_type": "latency_spike",
      "detected_at": "2026-03-28T01:15:05Z"
    },
    {
      "service": "catalog-service",
      "severity": 0.78,
      "anomaly_type": "error_spike",
      "detected_at": "2026-03-28T01:15:06Z"
    }
  ]
}
```

## Tuning Guide

### High Alert Rate (Too Many Events)

**Problem**: Threshold too low → noisy baseline.

**Solutions**:
1. Increase `WARMUP_SECONDS` (e.g., 1200 for 20 minutes)
2. Increase `Z_MAX` (e.g., 4.0 for ±4σ)
3. Increase thresholds: `L_THRESH`, `E_THRESH`, `S_SEVERE`
4. Increase `DEDUP_COOLDOWN_SECONDS` (e.g., 60s)

### Low Sensitivity (Missing Failures)

**Problem**: Threshold too high → missed anomalies.

**Solutions**:
1. Decrease `WINDOW_SIZE` (e.g., 30 for faster adaptation)
2. Decrease `Z_MAX` (e.g., 2.0 for ±2σ)
3. Decrease thresholds: `L_THRESH`, `E_THRESH`
4. Check Prometheus data quality (gaps? delays?)

### Baseline Drift

**Problem**: Normal behavior changes; alerts go stale.

**Solutions**:
- Restart detector (rebuilds baseline)
- Increase `WINDOW_SIZE` (more history for stability)
- Implement scheduled resets in RCA

## Known Failure Modes

| Mode | Cause | Impact | Mitigation |
|------|-------|--------|-----------|
| **Threshold too low** | Noisy baseline | Alert storm | Increase warmup, tune thresholds |
| **Threshold too high** | Insensitive | Missed failures | Lower thresholds, check data |
| **Short warmup** | Insufficient baseline | False positives | Increase WARMUP_SECONDS |
| **Prometheus lag** | Scrape delays | Stale detection | Monitor Prometheus health |
| **Zero variance** | Metrics never change | Always anomalous | Add jitter to thresholds |
| **Label cardinality** | Too many endpoints | Memory explosion | Filter in Prometheus or detector |

## Testing

```bash
# Run unit tests
pytest detection/tests/test_detection.py -v

# With coverage
pytest detection/tests/test_detection.py --cov=detection --cov-report=html
```

Test coverage:
- ✅ Ring buffer: push, pop, overflow
- ✅ Rolling stats: mean, std
- ✅ Z-score: calculation, normalization
- ✅ Severity: combination
- ✅ Warmup: suppression behavior
- ✅ Incident clustering: grouping, time windows

## Integration

### With Grafana

```json
{
  "datasource": "Prometheus",
  "targets": [
    {
      "expr": "anomaly_detector_events_total"
    }
  ],
  "alertName": "AnomalyDetected",
  "query": "max by (service, endpoint) (anomaly_score)"
}
```

### With RCA System

Consume `Incident` objects from detection module:

```python
def consume_incident(incident: Incident):
    """RCA handler: given incident, diagnose root cause."""
    # incident.affected_services → query traces
    # incident.time_window → query logs
    # incident.endpoint → query metadata
    pass
```

### With Alert Manager

Forward events to AlertManager via stdout JSON:

```bash
python -m detection.main --log-level ERROR > alert_stream.jsonl

# Consume alert_stream.jsonl in upstream system
```

## Performance

- **Per-tick latency**: ~100-200 ms for 50 services × 5 endpoints
- **Memory**: ~50 KB per stream (ring buffer + stats)
- **CPU**: ~10% single-core for standard workloads
- **Prometheus query time**: 1-2 seconds (network bound)

Scaling:
- 1-100 services/endpoints: No issues
- 100-1000 services/endpoints: Monitor memory, consider sharding
- 1000+ services/endpoints: Split into multiple detector instances

## See Also

- [OTEL_PIPELINE_GUIDE.md](../observability/OTEL_PIPELINE_GUIDE.md) - Complete observability setup
- [incident_cluster.py](incident_cluster.py) - Incident grouping logic
- [models.py](models.py) - Data model definitions
- [config.py](config.py) - Configuration schema
"""

# This file is a markdown documentation file.
# To view in VS Code: Right-click → "Open Preview"
