# OpenTelemetry Observability Setup

Complete instrumentation of microservices with OpenTelemetry for metrics, traces, and logs.

## Components

### Metrics Pipeline
- **Collection**: OpenTelemetry SDK in each service
- **Export**: OTLP gRPC to OTel Collector
- **Storage**: Prometheus
- **Visualization**: Grafana (port 3000)

### Traces Pipeline
- **Collection**: OpenTelemetry SDK in each service
- **Export**: OTLP gRPC to OTel Collector
- **Storage**: Jaeger (port 16686)
- **Visualization**: Jaeger UI

### Logs Pipeline
- **Collection**: Structured JSON logs via structlog
- **Export**: OTLP gRPC to OTel Collector
- **Storage**: Loki (port 3100)
- **Visualization**: Grafana (via Loki datasource)

## Architecture

```
┌─────────────────────────────────────────────────────┐
│         Microservices (FastAPI + OpenTelemetry)     │
│  ┌──────────┬──────────┬──────────┬──────────────┐  │
│  │   Auth   │ Catalog  │  Order   │  Payment     │  │
│  │ Service  │ Service  │ Service  │  Service     │  │
│  └──────────┴──────────┴──────────┴──────────────┘  │
│             OTLP/gRPC (port 4317)                   │
└────────────────────┬────────────────────────────────┘
                     │
             ┌───────▼────────┐
             │ OTel Collector │
             │ (port 4317)    │
             └───┬────────┬───┘
                 │        │
          ┌──────▼──┐  ┌───▼──────┐  ┌────────┐
          │Prometheus  │  Jaeger  │  │ Loki   │
          │(9090)   │  │(16686)   │  │(3100)  │
          └──┬──────┘  └────┬─────┘  └────┬───┘
             │              │             │
             └──────┬───────┴─────────────┘
                    │
              ┌─────▼──────┐
              │  Grafana   │
              │  (3000)    │
              └────────────┘
```

## Setup

### 1. Start Observability Stack (Docker Compose)

```bash
cd observability/
docker-compose up -d
```

### 2. Verify Services Are Running

- Prometheus: http://localhost:9090
- Jaeger: http://localhost:16686
- Grafana: http://localhost:3000 (admin/admin)
- Loki: http://localhost:3100

### 3. Start Microservices with OTEL_EXPORTER_OTLP_ENDPOINT

```bash
# In separate terminals or use docker-compose
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Auth Service
python -m auth.main

# Catalog Service
python -m catalog.main

# Order Service
python -m order.main

# Payment Service
python -m payment.main

# Gateway Service
python -m gateway.main

# Main App (combines all services)
python main.py
```

## Telemetry Philosophy

### Metrics (Prometheus)
- **Purpose**: Trigger detection of anomalies
- **Granularity**: Service-level aggregates
- **Examples**:
  - `http_request_total` - total requests per endpoint
  - `http_request_duration_seconds` - request latency histogram
  - `external_call_errors_total` - failed external calls
  - `cache_hits_total` / `cache_misses_total` - cache efficiency

### Traces (Jaeger)
- **Purpose**: Root cause analysis - understand end-to-end request flow
- **Granularity**: Individual request spans with full context
- **Features**:
  - Trace propagation via HTTP headers (W3C `traceparent` standard)
  - Parent-child span relationships
  - Attributes for context (user.id, order.id, etc)
  - Events for milestones (cache_hit, external_call, etc)

### Logs (Loki via JSON)
- **Purpose**: Supporting evidence - only simple facts, no complex structures
- **No `trace_id` in message**: Use Loki's own trace integration instead
- **Format**: JSON-structured logs via structlog
- **Examples**:
  ```json
  {
    "timestamp": "2024-01-28T15:30:45.123456",
    "service": "payment-service",
    "level": "ERROR",
    "message": "timeout calling DB",
    "event_type": "dependency_failure",
    "latency_ms": 2100,
    "failure_mode": "payment_timeout"
  }
  ```

## Key Metrics Defined

### Request Metrics
- `http_request_total` (counter)
  - Labels: service, method, endpoint, status_code
- `http_request_duration_seconds` (histogram)
  - Labels: service, method, endpoint
- `http_error_total` (counter)
  - Labels: service, method, endpoint, error_type

### External Call Metrics
- `external_call_duration_seconds` (histogram)
  - Labels: source_service, target_service
- `external_call_errors_total` (counter)
  - Labels: source_service, target_service, error_type

### Database Metrics
- `db_query_duration_seconds` (histogram)
  - Labels: service, query_type
- `db_query_errors_total` (counter)
  - Labels: service, query_type, error_type

### Cache Metrics (Catalog)
- `cache_hits_total` (counter)
  - Labels: service
- `cache_misses_total` (counter)
  - Labels: service

### Service-Specific Metrics
- Auth: `auth_failures_total`
- Payment: `payment_failures_total`
- Order: Inherits all above

## Configuration

### OTel Collector (otel-collector-config.yaml)
- **Receivers**: OTLP gRPC (4317), OTLP HTTP (4318), Zipkin (9411)
- **Processors**: Batch, Memory Limiter, Attributes
- **Exporters**:
  - Traces → Jaeger (14250)
  - Metrics → Prometheus (8889)
  - Logs → Loki (3100)

### Service Configuration
Each service's `main.py` calls:

```python
from shared.telemetry import setup_opentelemetry, instrument_fastapi_app
from shared.otel_metrics import init_metrics

# Setup OpenTelemetry
tracer, meter, otel_logger = setup_opentelemetry(
    service_name="service-name",
    otlp_endpoint="http://localhost:4317",  # From env var
    enable_prometheus_metrics=True,
)

# Initialize metrics
otel_metrics = init_metrics(meter, "service-name")

# Instrument FastAPI app
instrument_fastapi_app(app, "service-name")
```

## Trace Propagation

Traces are automatically propagated between services via:
- **Headers**: W3C `traceparent` standard (enabled by OpenTelemetry)
- **HTTP Client**: httpx and requests libraries auto-instrument
- **FastAPI**: Auto-instruments all routes

Flow example:
```
Gateway → Auth Service → Catalog Service → Database
   │           │              │
   └──────────trace_id────────┘
   (via HTTP headers, automatically)
```

## JSON Logging Examples

### Successful Request
```json
{
  "timestamp": "2024-01-28T15:30:45.123456",
  "service": "catalog-service",
  "level": "INFO",
  "message": "product_retrieved",
  "event_type": "cache_hit",
  "product_id": "550e8400-e29b-41d4-a716-446655440000",
  "cache_ttl": 3600
}
```

### Error Case
```json
{
  "timestamp": "2024-01-28T15:31:12.654321",
  "service": "order-service",
  "level": "ERROR",
  "message": "payment_call_failed",
  "event_type": "dependency_failure",
  "dependency": "payment-service",
  "error_type": "timeout",
  "latency_ms": 10000,
  "retry_attempt": 2,
  "reason": "connection_reset"
}
```

### Retry Logic
```json
{
  "timestamp": "2024-01-28T15:31:12.700000",
  "service": "order-service",
  "level": "WARN",
  "message": "retrying_external_call",
  "event_type": "retry",
  "target": "payment-service",
  "attempt": 3,
  "backoff_seconds": 4.5,
  "max_attempts": 5
}
```

## Grafana Dashboards

After setup, Grafana automatically pulls data from:
- **Prometheus** (metrics)
- **Loki** (logs)
- **Jaeger** (traces)

### Common Queries

**Prometheus (Rate of Errors)**:
```promql
rate(http_error_total[5m])
```

**Prometheus (P95 Latency)**:
```promql
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
```

**Loki (Recent Errors)**:
```logql
{service="payment-service"} | json | level="ERROR"
```

**Jaeger (By Service)**:
- Access at http://localhost:16686
- Select service → view traces with full context

## Instrumenting Your Routes

See `INSTRUMENTATION_EXAMPLES.py` for patterns:

1. **Simple endpoint**: Wrap in span, record metrics
2. **External calls**: Trace propagation via httpx
3. **Database**: Record query duration/errors
4. **Cache**: Track hits/misses
5. **Auth**: Track failures by reason
6. **Payment**: Track outcomes and latencies

## Cleanup

```bash
cd observability/
docker-compose down
```

## Environment Variables

```bash
# Required
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Optional
export OTEL_METRICS_EXPORTER=otlp
export OTEL_TRACES_EXPORTER=otlp
export OTEL_LOGS_EXPORTER=otlp
export OTEL_SDK_DISABLED=false
```

## Troubleshooting

1. **No metrics in Prometheus**: Check OTel Collector logs for export errors
2. **No traces in Jaeger**: Verify trace propagation headers are set
3. **Logs not in Loki**: Ensure structlog is configured correctly
4. **OTel Collector not starting**: Check otel-collector-config.yaml syntax

## References

- [OpenTelemetry Python SDK](https://opentelemetry.io/docs/instrumentation/python/)
- [OTLP Specification](https://opentelemetry.io/docs/specs/otel/protocol/)
- [Prometheus Metrics](https://prometheus.io/docs/concepts/samples/)
- [Jaeger Tracing](https://www.jaegertracing.io/docs/)
- [Loki Logs](https://grafana.com/docs/loki/latest/)
