"""
# Part 2: Anomaly Detection System - Implementation Summary

## Executive Summary

This is a **production-ready metrics-only anomaly detection system** for microservices.

**What it does**: Detects which services are anomalous right now.
**What it doesn't do**: Diagnose root cause (that's RCA).
**Data source**: Prometheus metrics only (no traces, logs, or causal models).
**Output**: Anomaly events and incidents for RCA handoff.

---

## Architecture Overview

### System Boundary

```
┌─────────────────────────────────────────────────────┐
│                  OBSERVABILITY STACK                │
├─────────────────────────────────────────────────────┤
│                                                     │
│  DETECTION (Part 2) ← Part 1 feeds metrics          │
│                                                     │
│  Input:  Prometheus metrics (latency, errors)       │
│  Output: Anomaly events → Incidents                 │
│          Severity: [0, 1]                           │
│          Classification: latency/error/mixed        │
│                                                     │
│                    ↓                                │
│                                                     │
│  RCA (Part 3) ← consumes incidents                  │
│                                                     │
│  Input:  Incidents (which services, when)           │
│  Output: Root cause diagnosis                       │
│          (via traces, logs, dependency chains)      │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Component Interaction

```
PrometheusClient
    ↓ (fetches metrics)
DerivedMetricsComputer
    ↓ (p95_latency, error_rate)
AnomalyDetector
    ┣━ RingBuffer (per stream)
    ┣━ RollingStats (mean/std)
    ┣━ AnomalyScorer (z-score)
    ┗━ IncidentCluster (grouping)
        ↓
    AnomalyEvent
        ↓
    Incident
        ↓
    RCA System (external)
```

---

## Technical Implementation

### 1. Ring Buffer (`ring_buffer.py`)

**Purpose**: Maintain sliding window of last 60 metric values.

**Key points**:
- Fixed-size circular buffer
- O(1) push, O(n) get_all (n=window_size)
- No reallocation on overflow
- Handles age-based statistics

**Usage**:
```python
buffer = RingBuffer(60)  # Last 60 seconds
buffer.push(0.052)       # New metric value
buffer.push(0.048)
# ... after 60 pushes ...
all_values = buffer.get_all()  # Returns [oldest, ..., newest]
```

### 2. Rolling Statistics (`rolling_stats.py`)

**Purpose**: Compute mean and std from buffer (online).

**Formulas**:
- `mean = Σx / n`
- `std = √(Σ(x - mean)² / (n - 1))`  [sample std]

**Key points**:
- Recomputes from full buffer each call (correct, not micro-optimized)
- Handles edge cases: empty buffer, < 2 values
- Used by detector for z-score normalization

**Usage**:
```python
stats = RollingStats(buffer)
mu, sigma = stats.get_stats()
```

### 3. Prometheus Client (`prometheus_client.py`)

**Purpose**: HTTP queries to Prometheus API.

**Methods**:
- `get_p95_latency_by_service_endpoint()` → histogram_quantile(0.95, ...)
- `get_error_rate_by_service_endpoint()` → (5xx errors) / (total requests)
- `get_request_rate_by_service_endpoint()` → rate(...) [debug only]

**Key points**:
- Encapsulates all PromQL in one place
- Handles label extraction
- Error resilience: returns empty dict on failure
- Metric names configurable

**Usage**:
```python
client = PrometheusClient("http://prometheus:9090")
latencies = client.get_p95_latency_by_service_endpoint(
    latency_metric="http_request_duration_seconds",
    service_label="service_name",
    endpoint_label="http_route"
)
# Returns: {("payment", "/checkout"): 0.052, ...}
```

### 4. Derived Metrics (`derived_metrics.py`)

**Purpose**: Orchestrate metric fetching and combine into dashboard.

**Abstraction**: Single `refresh_all()` call returns:
```python
{
    ("service", "endpoint"): {
        "p95_latency": 0.052,      # seconds
        "error_rate": 0.015,        # [0, 1]
        "request_rate": 105.3       # req/sec
    }
}
```

### 5. Anomaly Scorer (`scorer.py`)

**Purpose**: Z-score normalization and severity computation.

**Formulas**:
```
z = (x - μ) / (σ + ε)
score = min(1.0, |z| / Z_max)
severity = 0.6 * latency_score + 0.4 * error_score
```

**Key values**:
- ε (epsilon) = 1e-6 (avoid divide-by-zero)
- Z_max = 3.0 (3 standard deviations)
- Score range: [0, 1]
- Severity range: [0, 1]

### 6. Main Detector (`detector.py`)

**Purpose**: Orchestrates all components; the core detection loop.

**State per stream**:
```python
StreamState:
    key: StreamKey(service, endpoint, metric_type)
    buffer: RingBuffer  # Ring buffer with last 60 values
    rolling_mean: float
    rolling_std: float
    is_anomalous: bool
    last_anomaly_emitted_at: float  # For deduplication
```

**Per tick**:
1. Fetch metrics from Prometheus
2. For each (service, endpoint):
   - Update latency buffer + stats
   - Compute latency_score
   - Update error buffer + stats
   - Compute error_score
   - Compute severity
3. Check triggers:
   - latency_anomaly = (latency_score >= L_thresh)
   - error_anomaly = (error_score >= E_thresh)
   - is_severe = (severity >= S_severe)
4. Emit event if: (latency_anomaly AND error_anomaly) OR is_severe
5. Cluster event into incident
6. Return new events and incidents

**Warm-up logic**:
- First 600 seconds: build buffers, NO events
- After warm-up: normal trigger logic

### 7. Incident Clustering (`incident_cluster.py`)

**Purpose**: Group related anomalies into incidents.

**Clustering rule**:
- Time window: 10 seconds (configurable)
- Key: (endpoint, time_window)
- All services with anomalies in window = same incident

**Example**:
```
T=0s    payment-service: /checkout latency spike → Incident #1
T=0.5s  catalog-service: /checkout error spike  → Join Incident #1
T=1s    gateway-service: /checkout error spike  → Join Incident #1
T=11s   order-service: /checkout latency spike  → Incident #2 (new window)
```

**Output**:
```python
Incident:
    incident_id: "inc-a3b2c1d0"
    endpoint: "/checkout"
    time_window_start: T=0s
    time_window_end: T=10s
    anomalies: [
        {service: "payment", severity: 0.91, type: "latency_spike"},
        {service: "catalog", severity: 0.78, type: "error_spike"},
        {service: "gateway", severity: 0.71, type: "error_spike"}
    ]
```

### 8. Service Wrapper (`service.py`)

**Purpose**: HTTP-friendly interface to detector.

**Methods**:
- `tick()` → Returns JSON with events, incidents, warmup status
- `get_recent_events(limit)` → Last N events
- `get_recent_incidents(limit)` → Last N incidents
- `get_stream_state(service, endpoint)` → Debug stream stats
- `get_status()` → Overall service health

### 9. Configuration (`config.py`)

**Purpose**: Load settings from environment variables.

**Defaults**:
```
PROMETHEUS_BASE_URL=http://localhost:9090
L_THRESH=0.5
E_THRESH=0.5
S_SEVERE=0.8
WINDOW_SIZE=60
Z_MAX=3.0
WARMUP_SECONDS=600
CLUSTER_WINDOW_SECONDS=10
POLL_INTERVAL_SECONDS=1
LATENCY_WEIGHT=0.6
ERROR_WEIGHT=0.4
DEDUP_COOLDOWN_SECONDS=30
```

### 10. Data Models (`models.py`)

**Key Pydantic models**:
- `AnomalyEvent`: Single anomaly (service, endpoint, severity, timestamp)
- `AnomalyType`: Enum (LATENCY_SPIKE, ERROR_SPIKE, MIXED)
- `Incident`: Cluster of anomalies (incident_id, endpoint, time_window, anomalies)
- `IncidentAnomaly`: Service's contribution to incident
- `StreamKey`: Identity (service, endpoint, metric_type)
- `StreamState`: Internal state (buffer, stats, anomaly flag)

---

## Formulas

### Z-Score (Statistical Normalization)

```
z = (x - μ) / (σ + ε)
```

**Interpretation**:
- z ≈ 0: Value near mean (normal)
- z ≈ 3: Value 3σ away (99.7% confidence anomalous)
- z ≈ -2: Value 2σ below mean

**Why Z-score?**
- Agnostic to metric scale (works for 0.01s and 1000s)
- Statistical rigor (known distribution)
- Interpretable (number of std devs)

### Normalized Score (Severity Component)

```
score = min(1.0, |z| / Z_max)
```

**Maps z to [0, 1]**:
- z = 0 → score = 0
- |z| = Z_max (3.0) → score = 1.0
- |z| > Z_max → score = 1.0 (capped)

### Severity (Combined Score)

```
severity = clip[0,1](0.6 * latency_score + 0.4 * error_score)
```

**Weights**:
- 60% latency (service slow)
- 40% error (service broken)
- Tunable via LATENCY_WEIGHT, ERROR_WEIGHT

### Trigger Condition

**Emit anomaly event if**:
```
(latency_anomaly AND error_anomaly) OR is_severe

Where:
  latency_anomaly = (score_latency >= L_thresh)  # default 0.5
  error_anomaly = (score_error >= E_thresh)      # default 0.5
  is_severe = (severity >= S_severe)             # default 0.8
```

**Interpretation**:
- Both latency AND error spike together → high confidence mixed issue
- If either is VERY bad (>= S_severe) → trigger anyway
- Reduces false positives vs single-stream triggers

---

## File Structure

```
detection/
├── __init__.py                  # Module exports
├── config.py                    # Configuration from env vars
├── models.py                    # Pydantic data models
├── ring_buffer.py               # Fixed-size circular buffer
├── rolling_stats.py             # Online mean/std computation
├── prometheus_client.py         # HTTP queries to Prometheus
├── derived_metrics.py           # p95_latency, error_rate, request_rate
├── scorer.py                    # Z-score and severity calculation
├── detector.py                  # Main detection engine
├── incident_cluster.py          # Anomaly clustering into incidents
├── service.py                   # HTTP service interface
├── main.py                      # Standalone CLI entry point
├── example_simulation.py         # Synthetic demo (no Prometheus needed)
├── README.md                    # Full documentation
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Pytest configuration
│   └── test_detection.py        # Unit tests (ring buffer, stats, scorer, etc.)
│
└── IMPLEMENTATION_SUMMARY.md    # This file
```

---

## Usage

### Standalone CLI

```bash
# Run detection server
python -m detection.main \
  --prometheus-url http://prometheus:9090 \
  --log-level INFO \
  --poll-interval 1

# With custom thresholds
python -m detection.main \
  --l-thresh 0.4 \
  --e-thresh 0.6 \
  --s-severe 0.75

# Write results to file
python -m detection.main --output-file /tmp/results.jsonl

# Test mode (10 iterations only)
python -m detection.main --max-iterations 10
```

### Embedded Module

```python
from detection import DetectionConfig, DetectionService

config = DetectionConfig(
    prometheus_base_url="http://prometheus:9090",
    latency_threshold=0.5,
    error_threshold=0.5,
    severity_threshold=0.8,
)

service = DetectionService(config)

# Run one detection cycle
result = service.tick()
# result["events"]: List of AnomalyEvent
# result["incidents"]: List of Incident
# result["in_warmup"]: Boolean
# result["warmup_remaining_seconds"]: int

# Access recent history
events = service.get_recent_events(limit=100)
incidents = service.get_recent_incidents(limit=50)

# Debug stream state
state = service.get_stream_state("payment-service", "/checkout")
# {"latency_mean": 0.052, "latency_std": 0.003, ...}
```

### Example Simulation

```bash
# Run synthetic demo (no Prometheus needed)
python -m detection.example_simulation \
  --ticks 50 \
  --anomaly-at 20

# Output:
#   [Tick 20] WARMUP: 0s remaining (warmup done)
#   [Tick 20] ⚠ 1 ANOMALIES DETECTED:
#   [Tick 20]   - payment-service:/checkout (latency_spike, severity=0.85)
#   [Tick 20] 🔴 1 INCIDENTS CREATED:
#   [Tick 20]   - inc-a3b1c2: /checkout (max_severity=0.85)
```

---

## Integration Points

### Prometheus Metrics

**Required metrics** (must emit from microservices via OTel):

```
http_request_duration_seconds (histogram)
  ├── service_name="payment-service"
  ├── http_route="/checkout"
  └── http_status_code="200"

http_request_total (counter)
  ├── service_name="payment-service"
  ├── http_route="/checkout"
  └── http_status_code="500"
```

**Derived in detector**:
```
p95_latency = histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[1m]))
error_rate = rate(http_request_total{http_status_code=~"5.."}[1m]) / rate(http_request_total[1m])
request_rate = rate(http_request_total[1m])
```

### RCA System Integration

```python
def handle_incident(incident: Incident):
    """RCA consumes detection incident."""
    # incident.incident_id → unique ID
    # incident.endpoint → which API endpoint
    # incident.time_window_start/end → when to search
    # incident.affected_services → which services to investigate
    # incident.anomalies[i].severity → how bad
    
    # Query traces for affected services in time window
    traces = query_jaeger(
        service_names=incident.affected_services,
        start_time=incident.time_window_start,
        end_time=incident.time_window_end,
        endpoint=incident.endpoint
    )
    
    # Query logs for errors
    logs = query_loki(
        service_names=incident.affected_services,
        start_time=incident.time_window_start,
        end_time=incident.time_window_end,
        level="ERROR"
    )
    
    # Diagnose root cause
    root_cause = diagnose(traces=traces, logs=logs)
    
    return root_cause
```

### Alert Manager Integration

```python
# Forward anomaly events to AlertManager
def send_alert(event: AnomalyEvent):
    alert = {
        "labels": {
            "severity": "critical" if event.severity > 0.9 else "warning",
            "alertname": "AnomalyDetected",
            "service": event.service,
            "endpoint": event.endpoint,
        },
        "annotations": {
            "summary": f"{event.anomaly_type} in {event.service}",
            "description": f"Severity: {event.severity:.2f}",
        }
    }
    requests.post("http://alertmanager:9093/api/v1/alerts", json=[alert])
```

---

## Tuning Guide

### Problem: Too Many Alerts (Alert Fatigue)

**Symptoms**: Every few seconds, new anomalies.

**Causes**:
1. Thresholds too low
2. Baseline too noisy (warm-up too short)
3. Z_max too small (too sensitive)

**Fixes**:
```bash
# Increase warmup period
WARMUP_SECONDS=1200  # 20 minutes instead of 10

# Increase thresholds
L_THRESH=0.6         # Was 0.5
E_THRESH=0.6         # Was 0.5
S_SEVERE=0.9         # Was 0.8

# Less sensitive z-score clipping
Z_MAX=4.0            # Was 3.0

# Longer deduplication cooldown
DEDUP_COOLDOWN_SECONDS=60  # Was 30
```

### Problem: Missing Real Failures

**Symptoms**: Production incidents but detector silent.

**Causes**:
1. Thresholds too high
2. Window too large (slow adaptation)
3. Weights imbalanced

**Fixes**:
```bash
# Lower thresholds
L_THRESH=0.3         # Was 0.5
E_THRESH=0.3         # Was 0.5

# Faster adaptation
WINDOW_SIZE=30       # Was 60 (faster to fill, faster to react)

# More sensitive z-score
Z_MAX=2.0            # Was 3.0

# Increase error weight
ERROR_WEIGHT=0.6     # Was 0.4 (care more about errors)
LATENCY_WEIGHT=0.4   # Was 0.6
```

### Problem: Baseline Drift

**Symptoms**: After a system change, thresholds stale.

**Cause**: Learned baseline doesn't match new normal.

**Fixes**:
```bash
# Restart detector (rebuilds baseline)
pkill -f detection

# Or: increase window size (more adaptive)
WINDOW_SIZE=120  # More history = slower drift

# Or: implement scheduled resets in orchestration
# (e.g., weekly restart)
```

---

## Known Limitations

| Limitation | Impact | Workaround |
|-----------|--------|-----------|
| **Metrics-only** | Can't detect causal chains | Use RCA for diagnosis |
| **Per-endpoint** | Cardinality explosion with 1000+ endpoints | Aggregate in Prometheus or filter |
| **Fixed window** | No adaptive seasonality | Run multiple detectors with different windows |
| **Cold start** | First 10 min noiseless | Manually set baseline if known |
| **Label consistency** | Different metric label names break it | Standardize OTel instrumentation |
| **Resource limits** | Memory for buffers scales with streams | Monitor and tune WINDOW_SIZE |

---

## Performance Characteristics

### Time Complexity

- **Per tick**: O(S × E) where S=services, E=endpoints
  - Prometheus query: 1–2s (network bound)
  - Buffer updates: O(S × E × 2) [latency + error]
  - Scoring: O(S × E × 2)
  - Clustering: O(events) [typically < 10]

- **Total**: ~2–5s per tick (Prometheus query dominates)

### Space Complexity

- Per stream: ~1 KB (buffer + stats)
- With 100 services, 5 endpoints each, 2 metric types:
  - Total: 100 × 5 × 2 × 1 KB = 1 MB
- Scales linearly with S × E

### Scalability

| Metric | Limit | Notes |
|--------|-------|-------|
| Max services | 1000+ | Single detector OK |
| Max endpoints/service | 100 | Recommend <50 for clarity |
| Max streams | 10,000 | ~10 MB memory |
| Detection latency | 3–6s | Prometheus query bound |
| CPU per detector | ~10% | Single core, standard workload |

---

## Testing

```bash
# Run all tests
pytest detection/tests/test_detection.py -v

# With coverage
pytest detection/tests/test_detection.py --cov=detection --cov-report=html

# Specific test class
pytest detection/tests/test_detection.py::TestRingBuffer -v

# Run simulation
python -m detection.example_simulation --ticks 100 --anomaly-at 30
```

---

## Deployment

### Single Instance (Development)

```bash
# Start detection
python -m detection.main \
  --prometheus-url $PROMETHEUS_URL \
  --log-level INFO \
  --poll-interval 1

# Collect results locally
```

### Container Deployment

```dockerfile
FROM python:3.11-slim
RUN pip install requests pydantic python-dotenv
COPY detection/ /app/detection/
WORKDIR /app
CMD ["python", "-m", "detection.main"]
```

```bash
docker run \
  -e PROMETHEUS_BASE_URL=http://prometheus:9090 \
  -e L_THRESH=0.5 \
  -e E_THRESH=0.5 \
  anomaly-detector:1.0
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: anomaly-detector
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: detector
        image: anomaly-detector:1.0
        env:
        - name: PROMETHEUS_BASE_URL
          value: http://prometheus:9090
        - name: L_THRESH
          value: "0.5"
        - name: E_THRESH
          value: "0.5"
        - name: S_SEVERE
          value: "0.8"
        ports:
        - containerPort: 8080  # Service port, if adding HTTP
```

---

## Roadmap / Future Enhancements

1. **HTTP Service Interface**
   - FastAPI wrapper: `/health`, `/events`, `/incidents`, `/config`
   - Real-time WebSocket for streaming events

2. **Adaptive Thresholds**
   - Learn per-endpoint thresholds via clustering
   - Hourly/daily seasonality adjustment

3. **Multi-Detector Coordination**
   - Sharding by endpoint
   - Gossip protocol for incident deduplication

4. **Custom Metrics**
   - Allow user-defined metric streams
   - Pluggable scorers (not just z-score)

5. **Trace-Aware Fallback**
   - Optional trace correlation in RCA handoff
   - "If latency spike, here are related traces"

---

## See Also

- [README.md](README.md) – Full documentation
- [detection/config.py](config.py) – Configuration reference
- [detection/models.py](models.py) – Data model details
- [detection/detector.py](detector.py) – Main algorithm
- [detection/tests/test_detection.py](tests/test_detection.py) – Unit tests
- [../observability/OTEL_PIPELINE_GUIDE.md](../observability/OTEL_PIPELINE_GUIDE.md) – OTel setup (Part 1)
"""

# This file documents the complete anomaly detection system (Part 2).
# Read this first to understand the full architecture and design decisions.
