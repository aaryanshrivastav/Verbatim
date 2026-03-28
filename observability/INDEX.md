# Observability Documentation Index

Quick navigation for OTel pipeline documentation and configuration.

---

## 📚 Documentation Files

### Start Here (Pick One)

| Document | Purpose | Time |
|----------|---------|------|
| **[DEMO_CHECKLIST.md](./DEMO_CHECKLIST.md)** | Printable demo checklist with step-by-step instructions, talking points, and troubleshooting | 10-30 min |
| **[PIPELINE_QUICK_REFERENCE.md](./PIPELINE_QUICK_REFERENCE.md)** | One-page visual summary of pipeline, incident patterns, and queries | 5 min |
| **[OTEL_PIPELINE_GUIDE.md](./OTEL_PIPELINE_GUIDE.md)** | Comprehensive 5-part guide with architecture, data flow, incident mapping, verification, and demo checklists | 30-45 min |
| **[README_OTEL.md](./README_OTEL.md)** | Setup and configuration | 10 min |

### Configuration Files

| File | What It Contains |
|------|------------------|
| **[otel-collector-config.yaml](./otel-collector-config.yaml)** | OTel Collector pipeline with inline documentation (receivers, processors, exporters) |
| **[prometheus/prometheus.yml](./prometheus/prometheus.yml)** | Prometheus scrape config for OTel Collector metrics |
| **[docker-compose.yml](./docker-compose.yml)** | Observability stack (OTel Collector, Jaeger, Prometheus, Loki, Grafana, Promtail) |

---

## 🚀 Quick Start

```bash
# 1. Start observability stack
docker-compose up -d

# 2. Start microservices (see main README.md)
cd ..
docker-compose up -d

# 3. Run k6 load test
k6 run loadtest/scenarios/01_baseline.js --vus 5 --duration 30s

# 4. Open dashboards
# Jaeger: http://localhost:16686 → select service "gateway"
# Prometheus: http://localhost:9090 → query "http_request_total"
# Grafana: http://localhost:3000/explore → Loki → {service="gateway"}
```

---

## 📖 Guide Selection

### I want to understand the pipeline architecture (15 min)
→ Read **OTEL_PIPELINE_GUIDE.md Part 1-2**

### I want to debug an incident (20 min)
→ Read **OTEL_PIPELINE_GUIDE.md Part 3** (pick the incident that matches your issue)  
→ Use the metric/log/trace patterns provided

### I want to run a demo (30 min per scenario)
→ Use **OTEL_PIPELINE_GUIDE.md Part 5** checklist for one of the 7 incidents

### I need a quick reference during troubleshooting (2 min)
→ Open **PIPELINE_QUICK_REFERENCE.md** and scan the incident table

### I need to set up from scratch (20 min)
→ Follow **README_OTEL.md** setup section

---

## 🎯 The Three Signals

**Traces** (Jaeger)
- What: Individual request spans with parent-child relationships
- How to access: http://localhost:16686
- Use case: Find which span is slow or failing

**Metrics** (Prometheus)
- What: Counters (totals) and histograms (distributions) per service
- How to access: http://localhost:9090/graph
- Use case: Detect that something is wrong (spike in latency, error rate)

**Logs** (Loki)
- What: Structured JSON with service, level, message, custom fields
- How to access: Grafana Explore → Loki datasource
- Use case: Find exact error message and root cause

---

## 🔍 Common Queries

### Prometheus PromQL
```
# 95th percentile latency per service
histogram_quantile(0.95, http_req_duration_seconds{service="order"})

# Error rate
rate(http_request_total{status="503"}[1m])

# Cache hit ratio
rate(cache_hits_total[1m]) / (rate(cache_hits_total[1m]) + rate(cache_misses_total[1m]))
```

### Loki LogQL
```
# Find errors
{service="order"} level="ERROR"

# Find specific pattern
{service="payment"} |= "timeout"

# Count by label
{service="order"} | stats count() by level
```

### Jaeger Filters
- Service: dropdown selector
- Operation: span name (e.g., "POST /orders")
- Tags: custom labels (e.g., `http.status_code=500`)

---

## 📋 7 Incident Scenarios

All documented in **OTEL_PIPELINE_GUIDE.md Part 5**:

1. **Database Connection Pool Exhaustion** — Latency 50ms → 25s
2. **Redis Cache Failure** — Cache misses spike 1000x
3. **API Gateway DDoS** — Error spike, 503 responses
4. **Auth Service Overload** — Auth latency bottleneck
5. **Payment Timeout** — Graceful degradation, order marked failed
6. **SQL Injection** — Visible only in logs (not latency)
7. **Retry Storm** — Exponential backoff cascades, 8x latency

Each includes:
- k6 test command to trigger
- Expected signals in Prometheus (which metric spikes)
- Expected signals in Jaeger (which span is slow)
- Expected signals in Loki (which log pattern appears)
- Step-by-step demo checklist

---

## 🛠️ Troubleshooting

### No data in Jaeger
- Check: `docker-compose ps` (all services up?)
- Check: `docker-compose logs otel-collector` (check for errors)
- Check: Services have `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317` env var

### No metrics in Prometheus
- Open: http://localhost:9090/targets
- Status of "otel-collector" job should be GREEN
- If RED: check prometheus/prometheus.yml scrape config

### No logs in Loki
- Check: `docker-compose ps loki` (running?)
- Check: `docker-compose logs loki` (any errors?)
- Try: Query `{service="gateway"}` (too general, or no logs from that service?)

---

## 📞 References

- **OTel Collector Docs**: https://opentelemetry.io/docs/reference/specification/protocol/exporter/
- **Jaeger**: https://www.jaegertracing.io/docs/
- **Prometheus**: https://prometheus.io/docs/prometheus/latest/querying/basics/
- **Loki**: https://grafana.com/docs/loki/latest/logql/

---

## Next Steps

1. **If just getting started**: Read PIPELINE_QUICK_REFERENCE.md (5 min overview)
2. **If running demos**: Jump to OTEL_PIPELINE_GUIDE.md Part 5 (incident checklists)
3. **If need to debug something**: Find matching incident in Part 3, use queries provided

**Good luck!** 🚀
