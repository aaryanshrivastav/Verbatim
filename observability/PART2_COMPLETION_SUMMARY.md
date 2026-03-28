# Part 2 Completion Summary: OTel Collector Pipeline Configuration

## What Was Delivered

### 1. ✅ Enhanced OTel Collector Config (otel-collector-config.yaml)

**Changes**: Added 80+ lines of inline documentation explaining:
- **Receivers section**: OTLP (gRPC 4317, HTTP 4318) + Zipkin (legacy)
- **Processors section**: 
  - `batch`: Waits 10s or 1024 items; reduces network overhead
  - `memory_limiter`: Max 512 MB; drops telemetry if exceeded
  - `attributes`: Adds `environment=production` label to all data
- **Exporters section**: 
  - `prometheus` (port 8889): Metrics exposed for scraping
  - `jaeger`: Traces sent to Jaeger backend (port 14250)
  - `loki`: Logs sent to Loki (port 3100)
- **Service pipelines**: 
  - Traces: otlp/zipkin → processors → Jaeger
  - Metrics: otlp → processors → Prometheus
  - Logs: otlp → processors → Loki

---

### 2. ✅ Comprehensive OTEL_PIPELINE_GUIDE.md (NEW FILE)

**5 Parts** covering:

#### Part 1: OTel Collector Pipeline Overview
- Mermaid diagram showing components and data flow
- Reference table mapping component types to their purpose
- Explanation of three specialized pipelines

#### Part 2: How k6 Traffic Flows Through the Pipeline

**Traces (Request Tracing)**:
- How spans are created as k6 requests traverse services
- Example: Payment timeout trace showing all 5 spans with timing
- How to find traces in Jaeger UI

**Metrics (Performance Counters)**:
- Counters (http_request_total, auth_failures_total, cache_hits_total, retry_counter)
- Histograms (http_req_duration_seconds, db_query_duration_seconds)
- Example metric spike during DB failure scenario
- How to query metrics in Grafana/Prometheus

**Logs (Structured Events)**:
- JSON logs with service, level, message, trace_id, etc.
- Example log searches for each incident type
- How to correlate logs with other signals

#### Part 3: Incident-to-Pipeline Mapping (7 Incidents)

Detailed breakdown of each incident:

1. **Database Connection Pool Exhaustion**
   - What happens: requests queue after pool limit
   - How it appears in Prometheus: p95 latency jumps 50ms → 30s
   - How it appears in Jaeger: db:query span shows 30s timeout
   - How it appears in Loki: "pool exhausted" + "timeout" logs

2. **Redis Cache Failure**
   - What happens: cache misses cascade to DB
   - Prometheus: cache_misses_total spikes, cache_hits_total flat
   - Jaeger: catalog queries get slow (200ms vs 5ms)
   - Loki: "redis connection refused" + "cache miss" patterns

3. **API Gateway DDoS**
   - What happens: connection pool exhausted, 503 errors
   - Prometheus: status="503" spike, http_req_duration p95 → 8s
   - Jaeger: traces show queueing delays
   - Loki: "connection refused" + "limit exceeded" messages

4. **Auth Service Overload**
   - What happens: JWT validation becomes bottleneck
   - Prometheus: auth:validate latency 50ms → 500ms
   - Jaeger: auth/validate span visible as child bottleneck
   - Loki: "slow auth validation" messages

5. **Payment Timeout**
   - What happens: payment service times out, order marked `payment_failed`
   - Prometheus: order latency spikes 150ms → 2100ms
   - Jaeger: 4-span trace showing payment timeout as terminal span
   - Loki: "payment timeout" + "payment_failed" logs

6. **SQL Injection**
   - What happens: attack attempt visible only in logs (metrics don't spike)
   - Prometheus: auth_failures_total may spike
   - Jaeger: auth span shows SQLAlchemy exception
   - Loki: **PRIMARY**: SQL patterns visible ("admin' OR '1'='1")

7. **Retry Storm**
   - What happens: exponential backoff creates cascading delays
   - Prometheus: retry_counter ↑, external_call_total ×4, latency ↑↑
   - Jaeger: 4 payment spans in single order trace
   - Loki: "Retry attempt 1/4", "Retry attempt 2/4" sequences

#### Part 4: How to Verify the Pipeline

**Step 1: Traces (Jaeger)**
- Run k6 baseline, check http://localhost:16686 for service list
- Filter by service (gateway), see traces with duration/status

**Step 2: Metrics (Prometheus)**
- Query http://localhost:9090, search for `http_request_total`
- Verify metric appears with service labels

**Step 3: Logs (Loki)**
- Grafana Explore → Loki datasource
- Query: `{service="order"}`
- See logs with timestamps and content

**Step 4: Correlate All Three**
- Note k6 start time (e.g., 15:30:00)
- Prometheus: set time range to that window, see metrics
- Jaeger: filter traces to that time window
- Loki: query logs from that time window
- All three should show activity from k6 run

#### Part 5: 7 Incident Demo Checklist

Each incident has a 5-7 step checklist:

1. **Baseline observation** (normal metrics, latency, errors)
2. **Inject incident** (stop Redis, enable timeout, spike load, etc.)
3. **Run k6 test** (monitor live spikes in Prometheus)
4. **Observe in Jaeger** (find traces, identify slow span)
5. **Observe in Loki** (search for error patterns)
6. **Recovery** (disable incident, watch metrics normalize)
7. **Verify** (checklist of what should have been observed)

---

## How to Use This Documentation

### For a Quick Overview:
1. Read **Part 1** (5 min): Component reference + pipeline diagram
2. Skim **Part 2** (10 min): Quick data flow explanation

### For Understanding the System:
1. Read **Part 2** fully (15-20 min): Understand traces/metrics/logs flow
2. Read **Part 3 incidents 1-3** (10 min): See how failures map to signals

### For Running Demos:
1. Refer to **Part 5 checklist** for specific incident
2. Follow step-by-step instructions
3. Verify using queries provided in each section

### For Debugging a Real Issue:
1. Identify which incident category it resembles
2. Go to **Part 3** section for that incident
3. Use the metric/log/trace patterns to investigate

---

## Key Concepts Explained

### Three Backends, Three Signal Types

| Backend | Signal Type | Detects | Query Tool |
|---------|-------------|---------|-----------|
| **Jaeger** | Traces | Which span is slow (root cause) | Filter by trace ID, service |
| **Prometheus** | Metrics | That something is wrong (anomaly) | PromQL queries |
| **Loki** | Logs | Why it's wrong (error message) | LogQL queries |

**Workflow**: Metrics alert → Jaeger tells you which span → Loki shows why

### The Pipeline Flow

```
Service emits span/metric/log
    ↓
OTel SDK adds trace_id + context
    ↓
OTel Collector receives (port 4317)
    ↓
Batch processor (wait 10s or 1024 items)
    ↓
Memory limiter (max 512 MB)
    ↓
Attributes processor (add environment=production)
    ↓
Router picks backend(s) based on signal type:
    - Spans → Jaeger
    - Metrics → Prometheus
    - Logs → Loki
    ↓
Backend stores data
    ↓
UI queries data:
    - Jaeger UI (port 16686)
    - Prometheus UI (port 9090)
    - Grafana (port 3000, queries Prometheus/Loki/Jaeger)
```

---

## Quick Reference

### Open These in Browser During Demo

- Jaeger: http://localhost:16686/search
- Prometheus: http://localhost:9090/graph
- Grafana: http://localhost:3000/explore (admin/admin)
- Loki: Accessible via Grafana Explore → Loki datasource

### Common Prometheus Queries

```promql
# See all request rates
rate(http_request_total[1m])

# 95th percentile latency for order service
histogram_quantile(0.95, http_req_duration_seconds{service="order"})

# Error rate
rate(http_request_total{status="503"}[1m]) / rate(http_request_total[1m])
```

### Common Loki Queries

```logql
# All order errors
{service="order"} level="ERROR"

# Payment timeouts
{service="payment"} |= "timeout"

# Retry storm detection
{service="order"} |= "Retry attempt"
```

---

## Files Modified/Created

- ✅ `observability/otel-collector-config.yaml` - Added 80+ lines of inline documentation
- ✅ `observability/OTEL_PIPELINE_GUIDE.md` - NEW: 600+ line comprehensive guide

---

## What This Enables

✅ **Understanding the pipeline**: How OTel Collector receives → processes → routes telemetry  
✅ **Debugging incidents**: Map each failure mode to observable signals  
✅ **Correlating signals**: Show how traces + metrics + logs tell complete story  
✅ **Running demos**: Follow checklists to reproduce each incident  
✅ **Training SREs**: Teach observability patterns through concrete examples  

---

## Next Steps

1. **Verify the pipeline is working**:
   ```bash
   cd observability/
   docker-compose up -d
   cd ..
   docker-compose up -d
   k6 run loadtest/scenarios/01_baseline.js --vus 5 --duration 30s
   # Check Jaeger, Prometheus, Loki for data
   ```

2. **Run through an incident demo**:
   - Follow Part 5 checklist for Incident 1 (DB failure)
   - Observe metrics spike in Prometheus
   - Find trace in Jaeger
   - Search logs in Loki

3. **Share with team**:
   - Show OTEL_PIPELINE_GUIDE.md to SREs/DevOps
   - Use incident checklists for team training

---

## Notes

- The OTel Collector is designed to handle high telemetry volume (1000s of spans/sec)
- Memory limiter (512 MB) may drop telemetry under extreme load to prevent OOMkill
- Batch processor introduces up to 10s latency (acceptable for observability, not real-time alerts)
- All three backends (Jaeger, Prometheus, Loki) should be queried together for complete picture

---

**Questions?** Refer to [Part 3 of OTEL_PIPELINE_GUIDE.md](./observability/OTEL_PIPELINE_GUIDE.md#part-3-incident-to-pipeline-mapping) for specific failure mode explanations.
