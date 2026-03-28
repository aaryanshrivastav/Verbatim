# OTel Observability Quick Start Checklist

Print this page and check off each step as you go through the observability demo.

---

## 🚀 Setup Phase (First Time Only)

- [ ] Clone/navigate to Verbatim repository
- [ ] Read [observability/INDEX.md](./observability/INDEX.md) for navigation
- [ ] Install Docker and Docker Compose
- [ ] Install k6 (https://k6.io/docs/getting-started/installation/)

---

## 📦 Start Services

- [ ] **Terminal 1**: Start observability stack
  ```bash
  cd observability/
  docker-compose up -d
  sleep 10
  ```
  
- [ ] **Terminal 2**: Start microservices
  ```bash
  cd ..
  docker-compose up -d
  sleep 30
  ```

- [ ] **Verify**: Check all services running
  ```bash
  docker-compose ps
  # All services should show "Up"
  ```

---

## 🌐 Verify Dashboards Are Accessible

- [ ] **Jaeger UI** → Open http://localhost:16686
  - Expected: Jaeger interface with service dropdown
  
- [ ] **Prometheus** → Open http://localhost:9090
  - Expected: Prometheus graph interface
  
- [ ] **Grafana** → Open http://localhost:3000 (admin/admin)
  - Expected: Grafana home
  
- [ ] **Loki** → Via Grafana (Explore → Loki datasource)
  - Expected: Loki query interface

---

## 📊 Pick Your Demonstration

### Option A: Quick Baseline (5 minutes)

- [ ] Run k6 baseline test:
  ```bash
  k6 run loadtest/scenarios/01_baseline.js --vus 5 --duration 30s
  ```

- [ ] **In Jaeger** (http://localhost:16686):
  - [ ] Select service: "gateway"
  - [ ] Look for traces → click one to see span tree
  - Expected: Gateway span → auth/catalog/order/payment children

- [ ] **In Prometheus** (http://localhost:9090):
  - [ ] Query: `http_request_total`
  - Expected: Multiple metrics with service labels (gateway, auth, order, etc.)

- [ ] **In Grafana/Loki** (http://localhost:3000/explore → Loki):
  - [ ] Query: `{service="gateway"}`
  - Expected: Logs with timestamps from gateway service

### Option B: Incident Scenario (10-15 minutes)

Pick one incident from the list below and follow the detailed checklist in [observability/OTEL_PIPELINE_GUIDE.md](./observability/OTEL_PIPELINE_GUIDE.md) Part 5.

**Choose one:**
- [ ] Incident 1: Database Connection Pool Exhaustion (04_db_exhaustion.js)
- [ ] Incident 2: Redis Cache Failure (05_redis_failure.js + docker-compose stop redis)
- [ ] Incident 3: API Gateway DDoS (07_ddos_spike.js + high VUs)
- [ ] Incident 4: Auth Service Overload (simulate slow auth)
- [ ] Incident 5: Payment Timeout (02_payment_timeout.js)
- [ ] Incident 6: SQL Injection (send malicious payload)
- [ ] Incident 7: Retry Storm (06_retry_storm.js)

**For chosen incident:**
- [ ] Follow scenario setup
- [ ] (Watch Prometheus during test)
  - [ ] Which metric spikes?
  - [ ] What is baseline vs incident value?
- [ ] (Watch Jaeger during test)
  - [ ] Find slowest trace
  - [ ] Identify which span is the bottleneck
- [ ] (Search Loki during test)
  - [ ] What error log appears?
  - [ ] Can you find the root cause in the message?
- [ ] Recovery: Stop the incident/test
- [ ] (Verify metrics normalize)

---

## 🎯 Talking Points During Demo

### Architecture (1 min)
- "Services emit traces, metrics, and logs via OpenTelemetry"
- "OTel Collector receives all telemetry and routes to three backends"
- "Three signal types give complete visibility: what/why/when something goes wrong"

### Traces Demo (2 min)
- "Open Jaeger, filter by service:gateway"
- "Each trace shows request path through all services"
- "Click a trace to see spans and their latencies"
- "Parent-child relationships show request dependencies"

### Metrics Demo (2 min)
- "Open Prometheus, query http_req_duration_seconds"
- "See 95th percentile latency, error rates, cache efficiency"
- "Metrics alert us that something is wrong (spike detection)"

### Logs Demo (2 min)
- "Open Grafana → Explore → Loki"
- "Search {service='order'} to see all order service logs"
- "Search {service='payment'} |= 'timeout' to find specific errors"
- "Logs tell us WHY something went wrong (error details)"

### Integration Demo (2 min)
- "When Prometheus shows latency spike..."
- "...we go to Jaeger to find which span is slow..."
- "...and check Loki for the error message that caused it"
- "All three backends work together for complete visibility"

---

## 🔍 Troubleshooting During Demo

### No traces in Jaeger?
- [ ] Check: `docker-compose ps otel-collector` → UP?
- [ ] Check: Services have `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317`
- [ ] Check: `docker-compose logs otel-collector` → any errors?

### No metrics in Prometheus?
- [ ] Check: http://localhost:9090/targets → "otel-collector" job green?
- [ ] If red: prometheus/prometheus.yml may be misconfigured

### No logs in Loki?
- [ ] Check: `docker-compose ps loki` → UP?
- [ ] Try: Very general query `{job="loki"}` to see if ANY logs exist

### k6 test not starting?
- [ ] Check: k6 installed: `k6 version`
- [ ] Check: Microservices running: `docker-compose ps`
- [ ] Check: API responding: `curl http://localhost:8000/products`

---

## 📋 Post-Demo Checklist

- [ ] Collected feedback from audience
- [ ] Noted any questions for documentation improvements
- [ ] Stopped all containers:
  ```bash
  docker-compose down
  cd observability/
  docker-compose down
  ```

---

## 📚 For Deeper Learning

**After demo, share with attendees:**
- [ ] Path to docs: `observability/INDEX.md`
- [ ] Full pipeline guide: `observability/OTEL_PIPELINE_GUIDE.md` (600+ lines)
- [ ] Quick reference: `observability/PIPELINE_QUICK_REFERENCE.md` (1 page)
- [ ] Configuration details: `observability/otel-collector-config.yaml` (with inline comments)

---

## 🎓 Key Learnings to Communicate

- ✅ **complete observability**: Traces show HOW, metrics show WHAT, logs show WHY
- ✅ **Distributed tracing**: Follow requests across 5 microservices in one view
- ✅ **Anomaly detection**: Prometheus metrics spike before users notice problems
- ✅ **Root cause analysis**: Combined signals pinpoint exact failure
- ✅ **Production-ready**: Same stack used in real microservices deployments
- ✅ **Open standards**: OTel works with any backend (Jaeger, Prometheus, Loki, etc.)

---

## 💡 Pro Tips

- **For time-pressed audience**: Start with PIPELINE_QUICK_REFERENCE.md (5 min overview)
- **For technical audience**: Deep dive into OTEL_PIPELINE_GUIDE.md Part 3 (incident mapping)
- **For CTO/Manager**: Focus on bottom-line (faster MTTR, confidence in production)
- **For on-call engineer**: Show incident scenario matching their real experiences
- **For SRE**: Dive into verification steps (Part 4) and runnable checklists (Part 5)

---

## ✨ Demo Success Criteria

- [ ] User can see traces in Jaeger (service dropdown works, traces visible)
- [ ] User sees metrics in Prometheus (at least one metric appears)
- [ ] User finds logs in Loki (at least one log entry visible)
- [ ] User understands three signals work together (ask them to explain)
- [ ] User wants to try an incident scenario (engagement!)

---

**Estimated Total Demo Time**: 
- ⚡ Quick baseline: 10 minutes
- 🔧 One incident scenario: 20-30 minutes
- 📚 Full deep-dive: 45-60 minutes

**Good luck with your demo!** 🚀

---

For detailed procedures, see [observability/OTEL_PIPELINE_GUIDE.md](./observability/OTEL_PIPELINE_GUIDE.md)
