"""README for RCA (Root Cause Analysis) Pipeline.

Part 3 of the Microservice Observability System.
"""

# RCA Pipeline — Part 3

## Overview

The **RCA (Root Cause Analysis) Pipeline** takes incidents from the Detection system (Part 2) and automatically identifies the **single most probable root cause service** using trace graphs, metrics, and ML-based ranking.

**Input**: Incident with multiple anomalous services
**Output**: RCA JSON with root cause, confidence, evidence, and state vector for RL agents

---

## Architecture

7-stage pipeline (Modules A–G):

```
Incident (from Detection)
    ↓
[A] TRACE GRAPH BUILDER
    - Query Jaeger traces (by endpoint + time window)
    - Extract spans, compute duration baselines (ring buffer)
    - Per service: compute suspicious_span_ratio, trace_coverage
    ↓
[B] CANDIDATE EXTRACTOR
    - Filter: appears_in_traces >= 0.3 AND
             (suspicious_ratio >= 0.2 OR metrics_severity >= 0.5)
    - Result: 2–5 candidate services
    ↓
[C] FEATURE BUILDER
    - For each candidate: [m, t, c, depth, is_db, is_edge]
    - m = metrics_severity (from incident)
    - t = suspicious_span_ratio (from traces)
    - c = trace_coverage
    - depth = hop distance (0=frontend, 1=gateway, 2+=service, -1=db)
    - is_db, is_edge = service type flags
    ↓
[D] ML RANKER
    - Load pretrained model (LogisticRegression or RandomForest)
    - predict_proba([features]) per candidate
    - Fallback: score = 0.5*m + 0.4*t + 0.1*c
    ↓
[E] ROOT CAUSE SELECTION + CONFIDENCE
    - Select highest p_s
    - Compute confidence = p1 - p2
    - Bucket: high (>=0.3), medium (>=0.15), low
    ↓
[F] STATE VECTOR FOR RL
    - Fixed 6-service vector: [frontend, gateway, auth, checkout, payment, db]
    - state[i] = 2 (critical) if severity >= 0.8
    - state[i] = 1 (degraded) if severity >= 0.3
    - state[i] = 0 (healthy) otherwise
    ↓
[G] EVIDENCE ASSEMBLER
    - Prometheus: latency baseline comparison, error rate
    - Jaeger: representative error spans, duration spikes
    - Loki: error logs, exceptions, timeouts
    ↓
RCA Output JSON
```

---

## File Structure

```
rca/
  __init__.py
  models.py              # Pydantic models (Incident, RCAOutput, etc.)
  config.py              # Configuration (thresholds, service maps)
  ring_buffer.py        # Ring buffer for baseline tracking
  core.py               # Main orchestrator (pipeline.analyze())
  
  # Modules A–G
  trace_graph_builder.py
  candidate_extractor.py
  feature_builder.py
  ml_ranker.py
  root_cause_selector.py
  state_vector.py
  evidence_assembler.py
  
  # Clients (HTTP to external services)
  clients/
    jaeger_client.py    # Jaeger trace API
    prometheus_client.py
    loki_client.py
  
  # Training & examples
  training.py           # Offline ML model training
  example.py            # Synthetic example
  tests.py              # Unit tests
```

---

## Quick Start

### 1. Install Dependencies

Add to `requirements.txt`:

```
requests>=2.28.0
pydantic>=1.10.0
numpy>=1.21.0
scikit-learn>=1.0.0  # For training
pytest>=7.0.0        # For tests
```

```bash
pip install -r requirements.txt
```

### 2. Train ML Model (One-Time)

```bash
python -m rca.training
# Saves: rca/models/rca_model.pkl
```

This trains on synthetic data. In production:
- Replay historical incidents from your data warehouse
- Run chaos experiments (k6, gremlin) and label outcomes
- Re-train weekly/monthly

### 3. Run Example

```bash
python -m rca.example
```

Output:
```
Root Cause: payment-service
Confidence: 0.840 (high)
State Vector: [0, 0, 1, 0, 2, 1]
Evidence:
  Metrics: payment-service p95 latency 3.8x baseline
  Traces: span payment-service: duration 1.9s
  Logs: DB connection timeout to orders-db
```

### 4. Run Tests

```bash
pytest rca/tests.py -v
```

### 5. Integrate with Detection + Integration Point

```python
from rca.core import RCAPipeline
from rca.models import Incident, AnomalyDetail
from datetime import datetime, timedelta

# From Detection Part 2, you receive an Incident
incident = Incident(
    incident_id="inc-1042",
    endpoint="/checkout",
    time_window_start=datetime.utcnow() - timedelta(seconds=10),
    time_window_end=datetime.utcnow(),
    anomalies=[
        AnomalyDetail("frontend", 0.78, "latency_spike"),
        AnomalyDetail("checkout", 0.86, "latency_spike"),
        AnomalyDetail("payment-service", 0.91, "latency_spike")
    ]
)

# Run RCA
pipeline = RCAPipeline()
rca_output = pipeline.analyze(incident)

# Use output
print(f"Root Cause: {rca_output.root_cause}")
print(f"Confidence: {rca_output.confidence.bucket}")
print(f"Evidence: {rca_output.evidence.json()}")

# Send to downstream system (alerting, remediation, etc.)
store_rca_result(rca_output)
```

---

## Configuration

Set via environment variables. Defaults:

```bash
# External services
export JAEGER_BASE_URL=http://localhost:16686
export PROMETHEUS_BASE_URL=http://localhost:9090
export LOKI_BASE_URL=http://localhost:3100

# Trace query
export RCA_TRACE_QUERY_LIMIT=20
export RCA_SPAN_SUSPICIOUS_K=3.0       # Suspicious if 3x slower than baseline
export RCA_BASELINE_WINDOW=60           # 60s baseline window

# Candidate extraction
export RCA_TRACE_COVERAGE_THRESHOLD=0.3
export RCA_SUSPICIOUS_RATIO_THRESHOLD=0.2
export RCA_METRICS_SEVERITY_THRESHOLD=0.5

# ML ranker
export RCA_ML_MODEL_PATH=rca/models/rca_model.pkl

# Confidence buckets
export RCA_CONFIDENCE_HIGH=0.3
export RCA_CONFIDENCE_MEDIUM=0.15

# State thresholds
export RCA_CRITICAL_SEVERITY=0.8
export RCA_DEGRADED_SEVERITY=0.3
```

---

## Module Details

### Module A: Trace Graph Builder

**Input**: Incident (endpoint, time_window)
**Output**: Dict[service → TraceMetrics]

**Process**:
1. Query Jaeger: `/api/traces?tags=endpoint&start=T-10s&end=T&limit=20`
2. Sort by: error_span_count DESC, duration DESC
3. Per trace, per service:
   - Count spans
   - Mark as error if: error tag or error keyword in logs
   - Mark as suspicious if: duration > 3*baseline
4. Compute rolling baselines (ring buffer)

**Key Metrics**:
- `span_count`: Total spans
- `suspicious_count`: Error + slow spans
- `trace_coverage`: Fraction of traces containing service
- `suspicious_span_ratio`: suspicious / total

### Module B: Candidate Extractor

**Input**: Incident + trace_metrics
**Output**: List[Candidate]

**Filter Logic**:
```python
if (trace_coverage >= 0.3 AND
    (suspicious_ratio >= 0.2 OR metrics_severity >= 0.5)):
    → candidate
```

**Result**: 2–5 high-probability services

### Module C: Feature Builder

**Input**: Candidates
**Output**: Candidates with complete feature vectors

**Features**:
- `m`: metrics_severity [0, 1]
- `t`: suspicious_span_ratio [0, 1]
- `c`: trace_coverage [0, 1]
- `depth`: hop distance (int)
- `is_db`: 1 if database, 0 else
- `is_edge`: 1 if frontend/gateway, 0 else

**Service Map** (configurable):
```python
{
    "frontend": depth=0, is_edge=1,
    "api-gateway": depth=1, is_edge=1,
    "auth": depth=2,
    "checkout": depth=2,
    "payment-service": depth=3,
    "orders-db": depth=-1, is_db=1,
    ...
}
```

### Module D: ML Ranker

**Input**: Candidates with feature vectors
**Output**: Candidates with `.probability` set

**Model**: LogisticRegression or RandomForestClassifier (pickled)

**Training Sketch**:
```python
X = [
    [m, t, c, depth, is_db, is_edge],  # features
    ...
]
y = [1, 0, 1, 0, ...]  # 1 if root cause, 0 otherwise

model = LogisticRegression()
model.fit(StandardScaler().fit_transform(X), y)
```

**Online Inference**:
```python
features = candidate.feature_vector.to_array()
p = model.predict_proba([features])[0][1]  # P(root_cause)
candidate.probability = p
```

**Fallback** (if no model or prediction fails):
```python
score = 0.5*m + 0.4*t + 0.1*c
confidence = "low"
```

### Module E: Root Cause Selection

**Input**: Ranked candidates
**Output**: (root_cause, confidence, top_3)

**Algorithm**:
```python
p1 = max(probabilities)
p2 = second_max(probabilities)
confidence = p1 - p2

if confidence >= 0.3:
    bucket = "high"
elif confidence >= 0.15:
    bucket = "medium"
else:
    bucket = "low"
```

### Module F: State Vector for RL

**Input**: Incident
**Output**: List[int] of length 6

**Index Order**: [frontend, gateway, auth, checkout, payment, db]

**State Mapping**:
```python
if severity >= 0.8:
    state = 2  # critical
elif severity >= 0.3:
    state = 1  # degraded
else:
    state = 0  # healthy
```

**Use Case**: RL agent can use this to plan remediation actions

### Module G: Evidence Assembler

**Input**: Incident + root_cause_service
**Output**: Evidence (metrics, traces, logs)

**Queries**:

1. **Prometheus (Metrics)**:
   ```
   histogram_quantile(0.95, rate(...))  # p95 latency
   error_rate = 5xx_count / total_count
   ```

2. **Jaeger (Traces)**:
   ```
   Get top error spans with service=root_cause
   Compute duration vs baseline
   ```

3. **Loki (Logs)**:
   ```
   {service="root_cause"} |= "error" or |= "timeout"
   Take 2–3 representative errors
   ```

---

## Output Contract (RCAOutput)

```json
{
  "incident_id": "inc-1042",
  "endpoint": "/checkout",
  "root_cause": "payment-service",
  "confidence": {
    "value": 0.84,
    "bucket": "high"
  },
  "top_candidates": [
    { "service": "payment-service", "probability": 0.84 },
    { "service": "orders-db", "probability": 0.47 },
    { "service": "checkout", "probability": 0.30 }
  ],
  "affected_services": ["checkout", "frontend", "payment-service"],
  "state_vector": [0, 0, 1, 0, 2, 1],
  "original_severity": 0.91,
  "time_window": ["2026-03-28T12:00:00", "2026-03-28T12:00:10"],
  "evidence": {
    "metrics": [
      "payment-service p95 latency 3.8x baseline (1520ms vs 400ms)",
      "payment-service error rate 12% (>5% threshold)"
    ],
    "traces": [
      "span payment-service: duration 1900ms (>500ms baseline)",
      "span orders-db: timeout error"
    ],
    "logs": [
      "DB connection timeout to orders-db",
      "retry exhausted for /charge"
    ]
  }
}
```

---

## Tuning Guide

### When RCA Gets It Wrong

**Problem**: Wrong root cause identified
**Solutions**:
1. **Re-train ML model**: Add more labeled examples to training data
2. **Adjust candidate thresholds**: Lower `RCA_METRICS_SEVERITY_THRESHOLD` to catch less obvious candidates
3. **Check service map**: Ensure `service_depth_map` and `database_services` are accurate
4. **Adjust feature weights**: In fallback, change `0.5*m + 0.4*t + 0.1*c` if needed

**Problem**: False negatives (root cause not in candidates)
**Solutions**:
1. Lower `RCA_TRACE_COVERAGE_THRESHOLD` (default 0.3)
2. Lower `RCA_SUSPICIOUS_RATIO_THRESHOLD` (default 0.2)
3. Ensure Jaeger is collecting traces from all services

**Problem**: Cascading misidentification
**Feature**: State vector helps downstream RL agent understand multi-service failures

---

## Integration with Part 1 & Part 2

**Data Flow**:

```
Part 1: Prometheus
  ↓ (metrics)
Part 2: Detection
  ↓ (incident)
Part 3: RCA
  ↓ (root cause + evidence)
Downstream: Alerting, Auto-Remediation, RuleLearning
```

**Part 2 → Part 3**:
```python
# Part 2 emits:
incident = Incident(
    incident_id=cluster.id,
    endpoint=cluster.endpoint,
    time_window_start=cluster.time_window_start,
    time_window_end=cluster.time_window_end,
    anomalies=[
        AnomalyDetail(
            service=anom.service,
            severity=anom.severity,
            anomaly_type=anom.anomaly_type
        )
        for anom in cluster.anomalies
    ]
)

# Part 3 consumes:
pipeline = RCAPipeline()
rca = pipeline.analyze(incident)

# Output to database / alerting system
store_rca(rca)
```

---

## Advanced: ML Training Loop

For production, you need:

1. **Data Collection**:
   - Tag every incident with ground-truth root cause (manual + automated)
   - Store feature vectors + labels

2. **Training Pipeline**:
   ```bash
   # Weekly
   python scripts/retrain_rca_model.py \
       --input data/incidents_last_7d.csv \
       --output rca/models/rca_model_v2.pkl \
       --validate
   ```

3. **Model Registry**:
   - Version models (v1, v2, ...)
   - A/B test online (50% v1, 50% v2)
   - Canary rollout (1% v2 → 10% → 100%)

4. **Monitoring**:
   - Track RCA accuracy: % of root causes correctly identified
   - Track confidence distribution
   - Alert if accuracy drops <80%

---

## Troubleshooting

| Issue | Diagnosis | Fix |
|-------|-----------|-----|
| No candidates extracted | `RCA_TRACE_COVERAGE_THRESHOLD` too high | Lower threshold or check Jaeger data |
| Root cause not in top 3 | Model underfitting | Retrain with more data |
| Confidence always low | Feature scaling issue | Use StandardScaler in training |
| Jaeger queries timeout | Jaeger overloaded | Reduce `RCA_TRACE_QUERY_LIMIT` or scale Jaeger |
| Wrong evidence gathered | Prometheus labels mismatch | Check service_name, http_route labels |

---

## Performance Characteristics

**Latency per incident**: ~500ms–2s (depends on Jaeger/Prometheus query latency)
**Memory**: ~50MB (model + baselines)
**Throughput**: 100–1000 incidents/min (scales with number of modules in parallel)

**Bottlenecks**:
- Jaeger query time (typically 200–800ms)
- ML prediction (typically <10ms)
- Evidence assembly (typically 100–500ms)

---

## Future Enhancements

1. **Multi-root causes**: If correlation_score < 0.5, report top-2 instead of 1
2. **Cascade detection**: If all services equally anomalous, dig deeper (packet loss? network partition?)
3. **Historical patterns**: ML model learns recurrent failure modes
4. **Cost-weighted ranking**: Prioritize cheaper-to-fix services (e.g., config change < code deploy)
5. **RL feedback loop**: State vector → RL agent → remediation action → outcome → retrain

---

## References

- **Jaeger API**: https://www.jaegertracing.io/docs/latest/apis/
- **Prometheus API**: https://prometheus.io/docs/prometheus/latest/querying/api/
- **Loki API**: https://grafana.com/docs/loki/latest/api/
- **Scikit-learn**: https://scikit-learn.org/stable/

---

## License

Licensed under the same terms as the Verbatim project.
