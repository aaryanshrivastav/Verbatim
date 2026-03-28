"""
# Quick Start Guide - Anomaly Detection

## 1-Minute Setup

```bash
# Start detection server
python -m detection.main --prometheus-url http://localhost:9090

# Output (every second):
#   [INFO] Warming up... 599s remaining
#   [INFO] Warming up... 598s remaining
#   ... (10 minutes of baseline learning)
#   [INFO] Warming up... 0s remaining (warmup done)
#   [WARNING] Detected 1 anomalies
#   [WARNING]   - payment-service: /checkout (mixed, severity=0.88)
```

## 5-Minute Test (Without Prometheus)

```bash
# Run synthetic example
python -m detection.example_simulation --ticks 50 --anomaly-at 20

# Output shows detector warmup, then anomaly injection at tick 20
```

## Integration (Python)

```python
from detection import DetectionService, DetectionConfig

# Create service
config = DetectionConfig(
    prometheus_base_url="http://localhost:9090",
    latency_threshold=0.5,
    error_threshold=0.5,
)
service = DetectionService(config)

# Run detection
for i in range(100):
    result = service.tick()
    
    # New anomalies?
    if result["events"]:
        for event in result["events"]:
            print(f"🚨 {event['service']}: {event['endpoint']} "
                  f"({event['anomaly_type']}, severity={event['severity']:.2f})")
    
    # New incidents?
    if result["incidents"]:
        for incident in result["incidents"]:
            print(f"📊 Incident {incident['incident_id']}: "
                  f"{incident['affected_services']} on {incident['endpoint']}")
    
    time.sleep(1)
```

## Configuration

Set environment variables **before** running:

```bash
export PROMETHEUS_BASE_URL=http://prometheus:9090
export L_THRESH=0.5           # Latency trigger
export E_THRESH=0.5           # Error trigger
export S_SEVERE=0.8           # Severity trigger
export WARMUP_SECONDS=600     # 10-minute warmup
export POLL_INTERVAL_SECONDS=1

python -m detection.main
```

## Common Tasks

### Lower False Positive Rate

Increase thresholds:
```bash
export L_THRESH=0.6
export E_THRESH=0.6
export S_SEVERE=0.85
```

### Faster Anomaly Detection

Decrease window size (adapt faster):
```bash
export WINDOW_SIZE=30
export Z_MAX=2.5
```

### Debug a Stream

```python
from detection import DetectionService, DetectionConfig

service = DetectionService(DetectionConfig())
service.detector.tick()  # Run once to populate streams

state = service.get_stream_state("payment-service", "/checkout")
print(state)
# {
#   "latency_mean": 0.052,
#   "latency_std": 0.003,
#   "error_mean": 0.012,
#   "error_std": 0.002,
#   ...
# }
```

### View Recent Events

```python
events = service.get_recent_events(limit=10)
for event in events:
    print(f"{event['timestamp']}: {event['service']} - {event['anomaly_type']}")
```

### View Service Status

```python
status = service.get_status()
print(f"Streams: {status['active_streams']}")
print(f"Events: {status['recent_events']}")
print(f"Warmup: {status['in_warmup']}")
```

## Troubleshooting

### "Prometheus connection refused"

Check Prometheus is running:
```bash
curl http://localhost:9090/api/v1/query?query=up
# Should return JSON
```

### "No events detected after 10 minutes"

Verify metrics exist in Prometheus:
```bash
curl 'http://localhost:9090/api/v1/query?query=http_request_duration_seconds'
# Should return results with service_name and http_route labels
```

### "Alert storm (too many events)"

Increase thresholds or warmup:
```bash
export L_THRESH=0.7
export E_THRESH=0.7
export WARMUP_SECONDS=1200  # 20 minutes
```

## Next Steps

1. **Read the full docs**: [detection/README.md](README.md)
2. **Understand the architecture**: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
3. **Integrate with RCA**: Feed incidents to your root cause analyzer
4. **Add dashboards**: Visualize events/incidents in Grafana
5. **Fine-tune thresholds**: Based on your traffic patterns

## API Reference

See [detection/models.py](models.py) for full data model definitions.

### AnomalyEvent
```python
{
    "service": "payment-service",
    "endpoint": "/checkout",
    "anomaly_type": "latency_spike",  # or "error_spike", "mixed"
    "severity": 0.85,
    "timestamp": "2026-03-28T01:15:05Z",
    "latency_score": 0.80,
    "error_score": 0.70
}
```

### Incident
```python
{
    "incident_id": "inc-a3b2c1d0",
    "endpoint": "/checkout",
    "time_window_start": "2026-03-28T01:15:00Z",
    "time_window_end": "2026-03-28T01:15:10Z",
    "max_severity": 0.91,
    "affected_services": ["payment-service", "catalog-service"],
    "anomaly_count": 2
}
```

## Performance

- **Detection latency**: 3–6 seconds end-to-end
- **Memory per 100 services**: ~1 MB
- **CPU**: ~10% single core
- **Warmup time**: 10 minutes (configurable)

## Support

Check [README.md](README.md) section "Known Failure Modes" for common issues.
"""

# Quick reference for getting started with anomaly detection.
