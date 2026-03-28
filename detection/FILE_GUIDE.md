"""
# Anomaly Detection (Part 2) - File Navigation Guide

## 📍 Start Here

### 1. For Quick Start (5 minutes)
- **[QUICKSTART.md](QUICKSTART.md)** – Get detector running in 1 minute
- **[example_simulation.py](example_simulation.py)** – See it work without Prometheus

### 2. For Understanding (30 minutes)
- **[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** – Full architecture breakdown
- **[README.md](README.md)** – Complete reference documentation

### 3. For Integration (1 hour)
- **[INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)** – How Part 2 connects with Part 1 & 3
- **[models.py](models.py)** – Data model definitions
- **[config.py](config.py)** – Configuration options

### 4. For Implementation (depends on task)
- **Core detector**: [detector.py](detector.py)
- **Prometheus integration**: [prometheus_client.py](prometheus_client.py)
- **Scoring logic**: [scorer.py](scorer.py)
- **Incident grouping**: [incident_cluster.py](incident_cluster.py)

## 📂 File Structure & Purposes

```
detection/
├── QUICKSTART.md                    ← START HERE (5 min)
├── IMPLEMENTATION_SUMMARY.md        ← READ SECOND (architecture)
├── README.md                        ← REFERENCE (full docs)
├── INTEGRATION_GUIDE.md             ← FOR INTEGRATION
│
├── __init__.py                      # Module exports
├── config.py                        # Configuration from env vars
├── models.py                        # Pydantic data models
│
├── CORE DETECTION PIPELINE:
├── ring_buffer.py                   # Fixed-size circular buffer
├── rolling_stats.py                 # Online mean/std computation
├── scorer.py                        # Z-score + severity calculation
├── detector.py                      # Main detection engine
│
├── INPUT/OUTPUT:
├── prometheus_client.py             # HTTP client for Prometheus
├── derived_metrics.py               # Compute p95, error_rate, etc.
├── incident_cluster.py              # Group anomalies into incidents
├── service.py                       # Python API interface
│
├── DEPLOYMENT/SERVING:
├── main.py                          # CLI entry point
├── api.py                           # HTTP API (FastAPI)
├── example_simulation.py             # Synthetic demo (no Prometheus)
│
├── TESTS:
├── tests/
│   ├── __init__.py
│   ├── conftest.py                  # Pytest configuration
│   └── test_detection.py            # Unit tests
│
└── This file:
    └── FILE_GUIDE.md                # You are here
```

## 🔄 Reading Order by Use Case

### "I want to understand how anomaly detection works"
1. Read: [QUICKSTART.md](QUICKSTART.md) (5 min)
2. Run: `python -m detection.example_simulation --ticks 50 --anomaly-at 20` (2 min)
3. Read: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) (15 min)
4. Read: [README.md](README.md) (15 min)

### "I want to deploy to production"
1. Read: [QUICKSTART.md](QUICKSTART.md) (5 min)
2. Read: [README.md](README.md) section "Deployment" (10 min)
3. Read: [config.py](config.py) (3 min)
4. Read: [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) (15 min)
5. Deploy: `python -m detection.api` or use Docker/K8s examples

### "I want to integrate with my RCA system"
1. Read: [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) (20 min)
2. Study: [models.py](models.py) - understand Incident structure (10 min)
3. Implement: RCA consumer that calls `detection.GET /incidents`
4. Test: Run [example_simulation.py](example_simulation.py)

### "I want to tune thresholds"
1. Read: [README.md](README.md) section "Tuning Guide" (10 min)
2. Read: [config.py](config.py) to see all options (3 min)
3. Run with custom flags: `python -m detection.main --l-thresh 0.6 --e-thresh 0.6`
4. Use [example_simulation.py](example_simulation.py) to test changes

### "I want to modify the algorithm"
1. Read: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) sections "Formulas" and "Component Interaction" (20 min)
2. Study: [scorer.py](scorer.py) - z-score and severity (10 min)
3. Study: [detector.py](detector.py) - main loop tick() method (15 min)
4. Modify component
5. Run tests: `pytest detection/tests/test_detection.py -v` (5 min)

### "I want to add custom metrics"
1. Read: [README.md](README.md) section "Metric Streams" (5 min)
2. Study: [derived_metrics.py](derived_metrics.py) and [prometheus_client.py](prometheus_client.py) (15 min)
3. Add PromQL query to PrometheusClient
4. Update scorer weights if needed: [config.py](config.py)

## 📊 Dependency Graph

```
┌─ config.py
│  (defines all settings)
│
├─ models.py
│  (data models)
│
├─ ring_buffer.py
│  (fixed-size buffer)
│  └─ rolling_stats.py
│     (compute mean/std)
│
├─ prometheus_client.py
│  (fetch metrics from Prometheus)
│  └─ derived_metrics.py
│     (p95, error_rate, request_rate)
│
├─ scorer.py
│  (z-score + severity)
│
├─ detector.py ← MAIN
│  Uses: config, models, ring_buffer, rolling_stats,
│         derived_metrics, scorer, prometheus_client
│  Produces: AnomalyEvent, Incident
│
├─ incident_cluster.py
│  (groups events into incidents)
│
├─ service.py
│  (Python API wrapper around detector)
│
├─ main.py
│  (CLI entry point)
│
├─ api.py
│  (HTTP API wrapper via FastAPI)
│
└─ example_simulation.py
   (synthetic metrics demo)
```

## 🧪 Testing

```bash
# Run all tests
pytest detection/tests/test_detection.py -v

# Run specific test class
pytest detection/tests/test_detection.py::TestRingBuffer -v

# Run with coverage
pytest detection/tests/test_detection.py --cov=detection --cov-report=html

# Run example simulation
python -m detection.example_simulation --ticks 50 --anomaly-at 20
```

## 🚀 Key Concepts to Learn

### Z-Score
- Formula: `z = (x - mean) / (std + epsilon)`
- Maps any metric to standard normal distribution
- Anomalous if |z| > 3 (3 standard deviations)
- See: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) "Formulas"

### Severity
- Combines latency and error into [0, 1] score
- Formula: `severity = 0.6 * latency_score + 0.4 * error_score`
- 60% latency, 40% error (configurable)
- See: [scorer.py](scorer.py)

### Ring Buffer
- Fixed-size sliding window (60 seconds by default)
- O(1) push, O(n) read
- Used for computing rolling mean/std
- See: [ring_buffer.py](ring_buffer.py)

### Incident Clustering
- Groups anomalies by endpoint + time window
- 10-second clustering window
- All services in window = same incident
- See: [incident_cluster.py](incident_cluster.py)

### Warm-Up Period
- First 10 minutes: NO anomaly events (building baseline)
- After warm-up: normal detection
- Prevents false positives on startup
- See: [detector.py](detector.py) `is_in_warmup()`

## 📚 Further Reading

### For Algorithms & ML
- Z-score in statistics: https://en.wikipedia.org/wiki/Standard_score
- Anomaly detection: https://en.wikipedia.org/wiki/Anomaly_detection
- Time series analysis: https://otexts.com/fpp2/

### For Observability
- OTEL_PIPELINE_GUIDE.md (Part 1 setup)
- Prometheus best practices: https://prometheus.io/docs/
- Distributed tracing: https://opentelemetry.io/docs/instrumentation/python/

### For RCA (Part 3)
- Root cause analysis: https://en.wikipedia.org/wiki/Root_cause_analysis
- Fault localization: https://arxiv.org/abs/2002.09155

## ❓ FAQ

### "Where do I start if I'm new?"
→ [QUICKSTART.md](QUICKSTART.md), then run [example_simulation.py](example_simulation.py)

### "How do I tune thresholds?"
→ [README.md](README.md) "Tuning Guide" section

### "How do I add custom metrics?"
→ [prometheus_client.py](prometheus_client.py) - add PromQL query

### "How do I integrate with RCA?"
→ [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)

### "How do I deploy to production?"
→ [README.md](README.md) "Deployment" section + [api.py](api.py)

### "How do I debug issues?"
→ [README.md](README.md) "Known Failure Modes" + [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) "Troubleshooting"

## ✅ Checklist

Before deploying to production:

- [ ] Read [QUICKSTART.md](QUICKSTART.md)
- [ ] Run [example_simulation.py](example_simulation.py)
- [ ] Read [README.md](README.md)
- [ ] Verify Prometheus metrics exist (Part 1 working)
- [ ] Verify label names match Part 1: `service_label`, `endpoint_label`, `status_label`
- [ ] Test warmup period: 10 minutes with no alerts
- [ ] Tune thresholds for your traffic pattern
- [ ] Integrate with RCA system (Part 3)
- [ ] Set up monitoring of detector itself
- [ ] Run `pytest detection/tests/test_detection.py` - should pass
- [ ] Load test: run `example_simulation.py --ticks 1000` - should be stable

## 📞 Support

If you encounter issues:

1. Check [README.md](README.md) "Known Failure Modes"
2. Check [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) "Troubleshooting"
3. Review [example_simulation.py](example_simulation.py) to understand expected behavior
4. Run unit tests: `pytest detection/tests/` to isolate component issues
5. Enable debug logging: `--log-level DEBUG`

## 📝 License

This module is part of Verbatim observability system.
See LICENSE file in repository root.
"""

# Navigation guide for anomaly detection module.
# Start with quick-start.md or implementation_summary.md depending on your goal.
