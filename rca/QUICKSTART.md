"""QUICKSTART: Get RCA Running in 5 Minutes"""

# RCA Pipeline 5-Minute Quickstart

## What You'll Do
1. Install dependencies (30 seconds)
2. Train model (30 seconds)
3. Run example (30 seconds)
4. View results (60 seconds)
5. Integrate with Part 2 (optional, 2 minutes)

---

## Step 1: Install Dependencies

```bash
pip install requests pydantic numpy scikit-learn
```

(already installed if you have requirements.txt)

---

## Step 2: Create Models Directory

```bash
mkdir -p rca/models
```

---

## Step 3: Train ML Model

```bash
python -m rca.training
```

**Output**:
```
Starting RCA model training...
Training data: 8 examples, 6 features
Training accuracy: 100.00%
Model saved to rca/models/rca_model.pkl
```

This generates `rca/models/rca_model.pkl` (synthetic training data).

---

## Step 4: Run Example

```bash
python -m rca.example
```

**Output**:
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
  Metrics: (2 entries)
    - payment-service p95 latency 3.8x baseline
    - payment-service error rate 12% (>5% threshold)
  
  Traces: (2 entries)
    - span payment-service: duration 1.9s (>500ms baseline)
    - span orders-db: timeout error
  
  Logs: (0 entries)
```

---

## Step 5: Run Tests

```bash
pytest rca/tests.py -v
```

**Output**:
```
test_candidate_extractor PASSED
test_feature_builder PASSED
test_feature_builder_database PASSED
test_root_cause_selector PASSED
test_state_vector PASSED
```

All tests pass ✅

---

## Step 6: Use in Code

```python
from rca.core import RCAPipeline
from rca.models import Incident, AnomalyDetail
from datetime import datetime, timedelta

# Create an incident
now = datetime.utcnow()
incident = Incident(
    incident_id="inc-demo",
    endpoint="/checkout",
    time_window_start=now - timedelta(seconds=10),
    time_window_end=now,
    anomalies=[
        AnomalyDetail("payment-service", 0.91, "latency_spike"),
        AnomalyDetail("checkout", 0.86, "latency_spike"),
        AnomalyDetail("frontend", 0.78, "latency_spike")
    ]
)

# Run RCA
pipeline = RCAPipeline()
rca_output = pipeline.analyze(incident)

# Use result
print(f"Root cause: {rca_output.root_cause}")
print(f"Confidence: {rca_output.confidence.bucket}")
print(f"Evidence:\n{rca_output.evidence.json(indent=2)}")
```

---

## Step 7 (Optional): Start HTTP API

```bash
python -m rca.api --host 0.0.0.0 --port 8001
```

Then:
```bash
curl -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "inc-api-test",
    "endpoint": "/checkout",
    "time_window_start": "2026-03-28T12:00:00",
    "time_window_end": "2026-03-28T12:00:10",
    "anomalies": [
      {"service": "payment-service", "severity": 0.91, "anomaly_type": "latency_spike"}
    ]
  }'
```

---

## Next Steps

- **Full Setup**: Read [IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md)
- **Module Details**: Read [README.md](./README.md)
- **Integration**: Connect Part 2 (Detection) → Part 3 (RCA)
- **Tuning**: Adjust `config.py` for your services
- **Training**: Collect production incidents and retrain

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: rca` | Ensure you're in the right directory |
| `Model not found...using fallback` | Run `python -m rca.training` first |
| Tests failing | Check Python version (3.8+) and dependencies |
| API server won't start | Port 8001 already in use? Change: `--port 8002` |

---

## Files in 5 Minutes

- ✅ Train: `rca/models/rca_model.pkl` created
- ✅ Test: All 5+ tests pass
- ✅ Example: `python -m rca.example` runs
- ✅ API: `python -m rca.api` starts on port 8001

**You're ready to integrate!** 🚀
