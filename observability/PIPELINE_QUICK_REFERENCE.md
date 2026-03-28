# OTel Pipeline at a Glance

## The Complete Data Flow

```
┌─────────────────────────────────┐
│      k6 Load Generator          │
│  (10 VUs, 2 minutes, baseline)  │
└────────────┬────────────────────┘
             │ HTTP requests
             ▼
┌─────────────────────────────────────────────────┐
│  Microservices (OpenTelemetry Instrumented)     │
│  ┌──────┬──────┬──────┬──────┬────────┐         │
│  │Auth  │Order │Catalog │Payment│Gateway│         │
│  └──────┴──────┴──────┴──────┴────────┘         │
│                                                  │
│  Each service generates:                        │
│  • Spans (request tracing)                      │
│  • Metrics (counters, histograms)               │
│  • Logs (structured JSON)                       │
└────────────────┬─────────────────────────────────┘
                 │ OTLP/gRPC (port 4317)
                 ▼
┌──────────────────────────────────────────────┐
│     OpenTelemetry Collector                  │
│                                              │
│  Receives (OTLP,  Zipkin)                    │
│         ↓                                     │
│  Processes (batch, memory_limit, attributes)│
│         ↓                                     │
│  Routes by type:                             │
│  • Spans → Jaeger exporter                   │
│  • Metrics → Prometheus exporter             │
│  • Logs → Loki exporter                      │
└──┬────────────────────────┬──────────────┬───┘
   │                        │              │
   ▼                        ▼              ▼
Jaeger              Prometheus          Loki
(16686)             (9090)              (3100)

   │                        │              │
   └────────────────┬───────┴──────────────┘
                    ▼
              Grafana (3000)
         (visualizes all three)
```

## 7 Signal Patterns (One Per Incident)

### How Each Incident Appears in Observability

| Incident | k6 Test | Prometheus Signal | Jaeger Signal | Loki Signal |
|----------|---------|------------------|-------------|-----------|
| **DB Exhaustion** | 04_db_exhaustion.js + high VUs | `http_req_duration p95: 50ms→25s` | `db:query span = 30s timeout` | `{service="order"} \|= "pool exhausted"` |
| **Redis Down** | 05_redis_failure.js | `cache_misses_total spikes 1000x` | `catalog span: 5ms→200ms` | `{service="catalog"} \|= "redis connection"` |
| **DDoS Spike** | 07_ddos_spike.js (100+ VUs) | `http_req_duration p95: 120ms→8s` | Multiple traces queued, slow | `{service="gateway"} status="503"` |
| **Auth Overload** | baseline.js during auth abuse | `auth:validate p95: 50ms→500ms` | `auth/validate = bottleneck span` | `{service="auth"} \|= "slow"` |
| **Payment Timeout** | 02_payment_timeout.js | `order latency p95: 150ms→2100ms` | `payment:charge span = 2000ms` | `{service="payment"} \|= "timeout"` |
| **SQL Injection** | baseline.js with malicious payload | `auth_failures_total spike` | `auth span shows SQLAlchemy error` | `{service="auth"} \|= "admin' OR"` |
| **Retry Storm** | 06_retry_storm.js | `retry_counter ×4, latency ×8` | 4 payment spans per order | `{service="order"} \|= "Retry attempt"` |

## Common Query Patterns

### Prometheus (Answer: "What's wrong?")

```promql
# Is latency high?
histogram_quantile(0.95, http_req_duration_seconds{service="order"})

# Is error rate high?
rate(http_request_total{status="503"}[1m])

# Are retries happening?
rate(retry_counter_total{service="order"}[1m])
```

### Loki (Answer: "Why is it wrong?")

```logql
# Find the error message
{service="order"} level="ERROR"

# Find specific failure type
{service="payment"} |= "timeout"
{service="auth"} |= "invalid"
{service="catalog"} |= "redis"
```

### Jaeger (Answer: "Which span is the bottleneck?")

```
1. Select service dropdown
2. Search for slowest trace in time window
3. Click trace ID
4. Look at span tree
5. Identify slowest child span = bottleneck
```

## Incident Response Workflow

```
1. Alert triggers (e.g., latency spike in Prometheus)
   ↓
2. Open Jaeger, search for slowest traces in time window
   ↓
3. Identify slow span (e.g., payment:charge taking 2000ms)
   ↓
4. Open Loki, search for that service's error logs
   Query: {service="payment"} |= "timeout"
   ↓
5. Find root cause log entry (e.g., "Timeout after 2000ms")
   ↓
6. Implement fix / Scale / Restart service
   ↓
7. Verify recovery in all three backends
   - Prometheus: latency back to baseline
   - Jaeger: new traces show normal duration
   - Loki: no more error messages
```

## Quick Start: Verify the Pipeline

```bash
# 1. Start observability stack
cd observability/
docker-compose up -d
sleep 10

# 2. Start microservices  
cd ..
docker-compose up -d
sleep 30

# 3. Generate traffic
k6 run loadtest/scenarios/01_baseline.js --vus 5 --duration 30s

# 4. Open dashboards
# Jaeger: http://localhost:16686
# - Select service: "gateway"
# - Should see traces appearing
#
# Prometheus: http://localhost:9090
# - Query: http_request_total
# - Should see services reporting metrics
#
# Grafana/Loki: http://localhost:3000 (Explore → Loki)
# - Query: {service="gateway"}
# - Should see logs

# 5. Verify all three backends have data
echo "✓ Jaeger shows traces"
echo "✓ Prometheus shows metrics"
echo "✓ Loki shows logs"
```

## The Key Insight

**One metric spike could have many causes.** Use all three backends together:

- **Prometheus tells you *something* is wrong** (baseline: p95=150ms, now p95=3000ms)
- **Jaeger tells you *which* service/span** (payment span = 2900ms)
- **Loki tells you *why***: (message: "Payment timeout after 2000ms")

---

**Full documentation**: See [OTEL_PIPELINE_GUIDE.md](./OTEL_PIPELINE_GUIDE.md)
**Implementation details**: See inline comments in [otel-collector-config.yaml](./otel-collector-config.yaml)
