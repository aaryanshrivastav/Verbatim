# OpenTelemetry Implementation Summary

## Files Created/Modified

### Core Telemetry Modules
- `shared/telemetry.py` - OpenTelemetry SDK setup and FastAPI instrumentation
- `shared/otel_metrics.py` - ServiceMetrics class for recording metrics
- `requirements.txt` - Added OpenTelemetry dependencies

### Service Updates (Added to each)
- `auth/main.py` - Setup OpenTelemetry for auth service
- `catalog/main.py` - Setup OpenTelemetry for catalog service
- `order/main.py` - Setup OpenTelemetry for order service
- `payment/main.py` - Setup OpenTelemetry for payment service
- `gateway/main.py` - Setup OpenTelemetry for gateway service
- `main.py` - Updated root app with OpenTelemetry

### Observability Stack
- `observability/docker-compose.yml` - Added OTel Collector service
- `observability/otel-collector-config.yaml` - OTel Collector configuration
- `observability/README_OTEL.md` - Comprehensive setup and usage guide
- `observability/INSTRUMENTATION_EXAMPLES.py` - Code examples for instrumenting routes

## Key Features Implemented

### 1. Metrics (Prometheus)
```python
# Automatically recorded metrics
- http_request_total (counter)
- http_request_duration_seconds (histogram)
- http_error_total (counter)
- external_call_duration_seconds (histogram)
- external_call_errors_total (counter)
- db_query_duration_seconds (histogram)
- db_query_errors_total (counter)
- cache_hits_total (counter)
- cache_misses_total (counter)
- auth_failures_total (counter)
- payment_failures_total (counter)
```

### 2. Traces (Jaeger)
- Automatic span creation for FastAPI routes
- Trace propagation via W3C traceparent headers
- Automatic instrumentation of outbound HTTP calls
- Attributes for context (service, endpoint, status, etc)
- Exception recording with stacktraces

### 3. Logs (JSON via Loki)
- Structured JSON logging via structlog
- No trace_id in logs (uses Loki's trace integration)
- Fields: timestamp, service, level, message, event_type, custom_fields

### 4. OTel Collector
- OTLP/gRPC receiver on port 4317
- OTLP/HTTP receiver on port 4318
- Pipelines:
  - Traces → Jaeger
  - Metrics → Prometheus
  - Logs → Loki

## Imports Added to Each Service

```python
# In each service's main.py:
from shared.telemetry import setup_opentelemetry, instrument_fastapi_app
from shared.otel_metrics import init_metrics

# Setup
tracer, meter, otel_logger = setup_opentelemetry(
    service_name="service-name",
    otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
)
otel_metrics = init_metrics(meter, "service-name")

# Instrument FastAPI
instrument_fastapi_app(app, "service-name")
```

## Telemetry Flow

```
┌────────────────────────────────────────────────┐
│ Microservice (FastAPI + OpenTelemetry)         │
│ - Spans created automatically                  │
│ - Metrics recorded per request                 │
│ - Logs emitted as JSON                         │
└────────────────────┬───────────────────────────┘
                     │ OTLP/gRPC
                     ▼
        ┌────────────────────────────┐
        │ OpenTelemetry Collector    │
        │ - Receives all telemetry   │
        │ - Batches data             │
        │ - Routes to backends       │
        └─┬──────────┬──────────┬────┘
          │          │          │
      Traces     Metrics      Logs
          │          │          │
          ▼          ▼          ▼
       Jaeger   Prometheus    Loki
          │          │          │
          └──────────┴──────────┘
               │
               ▼
            Grafana
       (Unified Dashboard)
```

## Usage Example: Instrumenting a Route

```python
import time
from shared.telemetry import tracer
from shared.otel_metrics import get_metrics

metrics = get_metrics()

@router.get("/products/{product_id}")
async def get_product(product_id: str):
    with tracer.start_as_current_span("get_product") as span:
        span.set_attribute("product.id", product_id)
        
        start_time = time.time()
        try:
            # Your business logic
            product = await db.fetch_product(product_id)
            
            duration = time.time() - start_time
            metrics.record_request_count("GET", "/products/{product_id}", 200)
            metrics.record_request_duration("GET", "/products/{product_id}", duration)
            
            return product
            
        except Exception as e:
            span.record_exception(e)
            metrics.record_error("GET", "/products/{product_id}", type(e).__name__)
            raise
```

## Example JSON Log Output

```json
{
  "timestamp": "2024-01-28T15:30:45.123456",
  "service": "order-service",
  "level": "ERROR",
  "message": "external_call_failed",
  "event_type": "dependency_failure",
  "dependency": "payment-service",
  "failure_mode": "timeout",
  "latency_ms": 10000,
  "retry_attempt": 2
}
```

## Running the Stack

### Start Observability (Docker Compose)
```bash
cd observability/
docker-compose up -d
```

### Start Microservices
```bash
# Set environment variable
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Run services
python main.py              # Main app (port 8000)
python auth.main           # Auth service (port 8001)
python catalog.main        # Catalog service (port 8002)
python order.main          # Order service (port 8003)
python payment.main        # Payment service (port 8004)
python gateway.main        # Gateway service (port 8005)
```

### Access UIs
- Prometheus: http://localhost:9090
- Jaeger: http://localhost:16686
- Grafana: http://localhost:3000
- Loki: http://localhost:3100

## Telemetry Philosophy

| Component | Purpose | Use Case |
|-----------|---------|----------|
| **Metrics** | Trigger detection | Alert on high error rate, latency spikes |
| **Traces** | Root cause analysis | Debug why a specific request failed |
| **Logs** | Supporting evidence | Understand context around anomaly |

**KEY**: Logs do NOT contain trace_id - Loki integrates traces separately
