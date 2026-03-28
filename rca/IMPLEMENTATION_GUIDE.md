"""IMPLEMENTATION GUIDE: RCA Pipeline (Part 3)"""

# RCA Pipeline Implementation Guide for Verbatim

## What Is This?

The **RCA (Root Cause Analysis) Pipeline** is Part 3 of the Verbatim microservice observability system.

**Purpose**: Given an incident where multiple services are degraded, automatically identify which service actually caused the problem (root cause), with evidence and confidence.

**Example**:
```
Detection discovers:
  - frontend latency spike (0.78 severity)
  - checkout latency spike (0.86 severity)
  - payment-service latency spike (0.91 severity)

RCA analysis returns:
  Root cause: payment-service (confidence: HIGH)
  
  Evidence:
    - Prometheus: payment-service p95 latency 3.8x baseline
    - Jaeger: payment-service spans timing out
    - Loki: "DB connection timeout to orders-db"
    
  Why payment-service?
    - High severity (0.91)
    - 80% of traces contain error spans
    - Located at critical junction (payment processing)
```

---

## System Architecture

### Part 1 → Part 2 → Part 3 Flow

```
[Part 1: Prometheus]
    ↓ Scrapes metrics every 15s
    
[Part 2: Anomaly Detection]
    ↓ Fires when (latency_anomaly AND error_anomaly) OR severe
    ↓ Outputs: Incident with {anomaly_service, severity} pairs
    
[Part 3: RCA Pipeline]  ← YOU ARE HERE
    ↓ Analyzes: Which service caused this?
    ↓ Outputs: RCA JSON with {root_cause, confidence, evidence}
    
[Downstream: Alerting/Remediation]
    ↓ Routes to on-call engineer or auto-remediation
```

---

## 7-Module Pipeline (A–G)

### Module A: Trace Graph Builder

**What it does**: Queries Jaeger traces, extracts span metrics

**Key steps**:
1. Query Jaeger for traces during incident window (T-10s to T)
2. For each trace, walk spans and mark errors
3. Group by service, compute per-service metrics:
   - How many spans for this service?
   - How many had errors or were suspicious (3x slow)?
   - Coverage: what % of traces included this service?

**Output**: Dict[service → {span_count, error_count, trace_coverage, suspicious_ratio}]

**Code entry point**: `trace_graph_builder.py / TraceGraphBuilder.build_graph()`

---

### Module B: Candidate Extractor

**What it does**: Filters services down to likely root causes

**Filter logic**:
```
A service is a CANDIDATE if:
  - It appears in ≥30% of traces (trace_coverage >= 0.3) AND
  - EITHER:
      - ≥20% of its spans are suspicious (error/slow)
      - OR its metrics severity >= 0.5
```

**Example**:
- payment-service: 95% trace coverage, 45% suspicious spans → YES, candidate
- frontend: 85% coverage, 10% suspicious → Maybe, depends on metric severity
- orders-db: 50% coverage, 80% suspicious → YES, strong candidate

**Output**: List[Candidate] (typically 2–5 services)

**Code entry point**: `candidate_extractor.py / CandidateExtractor.extract_candidates()`

---

### Module C: Feature Builder

**What it does**: Builds 6-value feature vector for each candidate

**Features**:
```
[m, t, c, depth, is_db, is_edge]

m = metrics_severity        [0–1] (from incident)
t = suspicious_span_ratio    [0–1] (from traces)
c = trace_coverage           [0–1] (coverage)
depth = hop_distance         [int] (0=frontend, 1=gateway, 2+=service, -1=db)
is_db = database?            [0/1]
is_edge = frontend/gateway?  [0/1]
```

**Why these features?**
- m, t, c: Quantify how anomalous the service is
- depth: Services deeper in call chain less likely to be root cause (cascade)
- is_db, is_edge: Structural hints (DBs often bottlenecks, frontends rarely root cause)

**Example**:
```
payment-service:  [0.91, 0.45, 0.95, 3, 0, 0]
orders-db:        [0.85, 0.80, 0.80, -1, 1, 0]
checkout:         [0.86, 0.15, 0.98, 2, 0, 0]
```

**Code entry point**: `feature_builder.py / FeatureBuilder.build_features()`

---

### Module D: ML Ranker

**What it does**: Uses ML model to score each candidate

**Process**:
1. Load pretrained model (pickled)
2. For each candidate, run: `model.predict_proba([features])[0][1]`
3. Result: probability that service is root cause

**Fallback** (if no model):
```
score = 0.5*m + 0.4*t + 0.1*c
```

**Training** (one-time offline):
```python
# Simulate incidents with known root causes
for incident in historical_incidents:
    features = [m, t, c, depth, is_db, is_edge]
    label = 1 if service_was_root_cause else 0
    training_data.append((features, label))

# Train
model = LogisticRegression()
model.fit(training_data_X, training_data_y)
joblib.dump(model, "rca_model.pkl")
```

**Code entry point**: `ml_ranker.py / MLRanker.rank_candidates()`

---

### Module E: Root Cause Selection + Confidence

**What it does**: Pick the best candidate and assign confidence

**Algorithm**:
```python
p1 = highest probability
p2 = second highest
confidence = p1 - p2

if confidence >= 0.3:
    bucket = "high"
elif confidence >= 0.15:
    bucket = "medium"
else:
    bucket = "low"
```

**Example**:
```
Candidates ranked:
  payment-service: 0.84
  orders-db: 0.47
  checkout: 0.30

→ Root cause: payment-service
→ confidence = 0.84 - 0.47 = 0.37 → "high"
```

**Code entry point**: `root_cause_selector.py / RootCauseSelector.select_root_cause()`

---

### Module F: State Vector for RL

**What it does**: Builds a 6-value vector representing system health

**Fixed services** (in order): [frontend, gateway, auth, checkout, payment, db]

**State per service**:
```
2 = critical (severity >= 0.8)
1 = degraded (severity >= 0.3)
0 = healthy
```

**Example** (for incident above):
```
frontend:       0.78 severity → state=1 (degraded)
gateway:        not in incident → state=0 (healthy)
auth:           not in incident → state=0
checkout:       0.86 severity → state=2 (critical)
payment:        0.91 severity → state=2 (critical)
db:             not in incident → state=0

→ state_vector = [1, 0, 0, 2, 2, 0]
```

**Use**: RL agents can use this to plan remediation (e.g., "if payment=critical, restart payment service")

**Code entry point**: `state_vector.py / StateVectorBuilder.build_state_vector()`

---

### Module G: Evidence Assembler

**What it does**: Gathers proof from 3 sources

**1. Prometheus (Metrics)**:
```
p95_latency_ms = 1520  (vs 400 baseline)
error_rate = 12%  (vs 5% threshold)
```

**2. Jaeger (Traces)**:
```
"span payment-service: duration 1900ms (>500ms baseline)"
"span orders-db: timeout error"
```

**3. Loki (Logs)**:
```
"DB connection timeout to orders-db"
"retry exhausted for /charge"
```

**Output**: Evidence object with 3 lists of strings

**Code entry point**: `evidence_assembler.py / EvidenceAssembler.assemble_evidence()`

---

## Setup Instructions

### 1. Prerequisites

Ensure you have:
- ✅ Part 1 running (Prometheus, scraping metrics)
- ✅ Part 2 running (Detection, emitting incidents)
- ✅ External services available:
  - Jaeger (default: http://localhost:16686)
  - Prometheus (default: http://localhost:9090)
  - Loki (default: http://localhost:3100)

### 2. Install Dependencies

Add to `requirements.txt`:
```
requests>=2.28.0
pydantic>=1.10.0
numpy>=1.21.0
scikit-learn>=1.0.0
```

Then:
```bash
pip install -r requirements.txt
```

### 3. Create Models Directory

```bash
mkdir -p rca/models
```

### 4. Train ML Model (One-Time)

```bash
python -m rca.training
```

This generates `rca/models/rca_model.pkl` using synthetic data.

**For production**: Collect historical incidents with labels and retrain weekly.

### 5. Run Tests

```bash
pytest rca/tests.py -v
```

All tests should pass.

### 6. Run Example

```bash
python -m rca.example
```

Output:
```
=== RCA RESULTS ===
Root Cause: payment-service
Confidence: 0.840 (high)
State Vector: [0, 0, 1, 0, 2, 1]
Top Candidates:
  1. payment-service: 0.840
  2. orders-db: 0.470
  3. checkout: 0.300

Evidence:
  Metrics: payment-service p95 latency 3.8x baseline
  Traces: span payment-service: duration 1.9s
  Logs: DB connection timeout to orders-db
```

---

## Integration with Part 2 (Detection)

### How to Connect

In your Detection service, after emitting an incident:

```python
# Part 2: detection/service.py

from rca.core import RCAPipeline
from rca.models import Incident, AnomalyDetail

class DetectionService:
    def __init__(self):
        self.rca_pipeline = RCAPipeline()
    
    def on_incident_emitted(self, incident_from_detector):
        """Call RCA when incident is emitted."""
        
        # Convert detector incident to RCA incident
        rca_incident = Incident(
            incident_id=incident_from_detector.incident_id,
            endpoint=incident_from_detector.endpoint,
            time_window_start=incident_from_detector.time_window_start,
            time_window_end=incident_from_detector.time_window_end,
            anomalies=[
                AnomalyDetail(
                    service=anom.service,
                    severity=anom.severity,
                    anomaly_type=anom.anomaly_type
                )
                for anom in incident_from_detector.anomalies
            ]
        )
        
        # Run RCA analysis
        rca_output = self.rca_pipeline.analyze(rca_incident)
        
        # Store/export result
        self.store_rca_result(rca_output)
        self.send_to_alerting(rca_output)
```

### Data Contract

**Detection → RCA**:
```python
Incident(
    incident_id: str,
    endpoint: str,
    time_window_start: datetime,
    time_window_end: datetime,
    anomalies: List[
        {service: str, severity: float[0-1], anomaly_type: str}
    ]
)
```

**RCA → Downstream**:
```python
RCAOutput(
    incident_id: str,
    endpoint: str,
    root_cause: str,
    confidence: {value: float, bucket: "high"|"medium"|"low"},
    top_candidates: [{service, probability}],
    affected_services: [str],
    state_vector: [int] × 6,
    evidence: {metrics: [], traces: [], logs: []},
    ...
)
```

---

## Configuration (Environment Variables)

```bash
# External services
JAEGER_BASE_URL=http://localhost:16686
PROMETHEUS_BASE_URL=http://localhost:9090
LOKI_BASE_URL=http://localhost:3100

# Trace analysis
RCA_TRACE_QUERY_LIMIT=20                    # Max traces per incident
RCA_SPAN_SUSPICIOUS_K=3.0                   # Suspicious if 3x slower
RCA_BASELINE_WINDOW=60                      # 60-second baseline

# Candidate filtering
RCA_TRACE_COVERAGE_THRESHOLD=0.3            # Min % of traces
RCA_SUSPICIOUS_RATIO_THRESHOLD=0.2          # Min % of suspicious spans
RCA_METRICS_SEVERITY_THRESHOLD=0.5          # Min severity

# ML
RCA_ML_MODEL_PATH=rca/models/rca_model.pkl

# Confidence
RCA_CONFIDENCE_HIGH=0.3                     # p1 - p2 >= this
RCA_CONFIDENCE_MEDIUM=0.15

# State vector
RCA_CRITICAL_SEVERITY=0.8
RCA_DEGRADED_SEVERITY=0.3
```

---

## API Endpoint (Optional)

If you want to expose RCA as an HTTP service:

```bash
python -m rca.api --host 0.0.0.0 --port 8001
```

Then POST to `/analyze`:
```bash
curl -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "inc-1042",
    "endpoint": "/checkout",
    "time_window_start": "2026-03-28T12:00:00",
    "time_window_end": "2026-03-28T12:00:10",
    "anomalies": [
      {"service": "payment-service", "severity": 0.91, "anomaly_type": "latency_spike"},
      {"service": "checkout", "severity": 0.86, "anomaly_type": "latency_spike"}
    ]
  }'
```

Response:
```json
{
  "incident_id": "inc-1042",
  "root_cause": "payment-service",
  "confidence": {"value": 0.84, "bucket": "high"},
  "evidence": {...},
  ...
}
```

---

## Troubleshooting

### RCA slow or timing out
- Check Jaeger availability (was last Query successful?)
- Reduce `RCA_TRACE_QUERY_LIMIT` from 20 to 10
- Check network latency between services

### No candidates extracted
- Lower `RCA_TRACE_COVERAGE_THRESHOLD` (e.g., 0.2 instead of 0.3)
- Verify Jaeger is collecting traces from target endpoint
- Check if incident window is correct (T-10s to T)

### Wrong root cause identified
- Retrain ML model with more examples
- Check service_depth_map in config (is depth correct?)
- Review evidence: are Prometheus/Loki queries returning data?

### Confidence always "low"
- Check if model is loaded: `python -c "import joblib; joblib.load('rca/models/rca_model.pkl')"`
- Retrain model: `python -m rca.training`
- Fallback should still work (but with lower accuracy)

---

## Files & Organization

```
rca/
  ├── __init__.py
  ├── models.py              ← Data models (Incident, RCAOutput)
  ├── config.py              ← Configuration (thresholds, service maps)
  ├── ring_buffer.py         ← Ring buffer for baselines
  │
  ├── core.py                ← Main orchestrator (RCAPipeline)
  ├── trace_graph_builder.py ← Module A
  ├── candidate_extractor.py ← Module B
  ├── feature_builder.py     ← Module C
  ├── ml_ranker.py           ← Module D
  ├── root_cause_selector.py ← Module E
  ├── state_vector.py        ← Module F
  ├── evidence_assembler.py  ← Module G
  │
  ├── clients/
  │   ├── jaeger_client.py   ← HTTP queries to Jaeger
  │   ├── prometheus_client.py ← HTTP queries to Prometheus
  │   └── loki_client.py     ← HTTP queries to Loki
  │
  ├── training.py            ← Train ML model (offline)
  ├── example.py             ← Synthetic demo
  ├── api.py                 ← FastAPI HTTP server
  ├── tests.py               ← Unit tests
  │
  ├── models/
  │   └── rca_model.pkl      ← Pickled ML model
  │
  └── README.md              ← Detailed docs
```

---

## Key Data Structures

### Incident (Input)

```python
Incident(
    incident_id="inc-1042",
    endpoint="/checkout",
    time_window_start=datetime(2026, 3, 28, 12, 0, 0),
    time_window_end=datetime(2026, 3, 28, 12, 0, 10),
    anomalies=[
        AnomalyDetail("frontend", 0.78, "latency_spike"),
        AnomalyDetail("payment-service", 0.91, "latency_spike"),
    ]
)
```

### TraceMetrics

```python
TraceMetrics(
    service="payment-service",
    span_count=100,
    suspicious_count=45,
    trace_coverage=0.95,
    suspicious_span_ratio=0.45
)
```

### FeatureVector

```python
FeatureVector(
    service="payment-service",
    m=0.91,         # metrics_severity
    t=0.45,         # suspicious_span_ratio
    c=0.95,         # trace_coverage
    depth=3,        # hop distance
    is_db=0,
    is_edge=0
)
```

### RCAOutput (Final)

```python
RCAOutput(
    incident_id="inc-1042",
    endpoint="/checkout",
    root_cause="payment-service",
    confidence=Confidence(value=0.84, bucket="high"),
    top_candidates=[
        CandidatePrediction(service="payment-service", probability=0.84),
        CandidatePrediction(service="orders-db", probability=0.47),
    ],
    affected_services=["frontend", "checkout", "payment-service"],
    state_vector=[0, 0, 1, 0, 2, 1],
    evidence=Evidence(
        metrics=["payment-service p95 latency 3.8x baseline"],
        traces=["span payment-service: duration 1900ms"],
        logs=["DB connection timeout to orders-db"]
    )
)
```

---

## Next Steps

1. **Setup**: Follow steps 1–6 above
2. **Verify**: Run tests, example, API
3. **Integrate**: Connect to Part 2 / Detection
4. **Monitor**: Track accuracy and confidence
5. **Tune**: Retrain ML model weekly with production data

---

## References

- [RCA README](./README.md) — Detailed module explanations
- [Example](./example.py) — Synthetic incident walkthrough
- [Tests](./tests.py) — Unit test examples
- Jaeger API: https://www.jaegertracing.io/docs/latest/apis/
- Prometheus API: https://prometheus.io/docs/prometheus/latest/querying/api/

---

## Questions?

Refer to README.md for:
- Module-by-module deep dive
- Tuning guide
- Performance characteristics
- Troubleshooting
