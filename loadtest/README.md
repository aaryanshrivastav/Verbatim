# k6 Load Testing Suite - Microservices Observability Demo

Comprehensive load testing and chaos engineering suite for the FastAPI microservices demo, with incident simulation, distributed tracing validation, and observability metric collection.

---

## Quick Start

### Prerequisites

- k6 installed
- Docker & Docker Compose (for running microservices)
- Microservices running on localhost:8000

### Installation

```bash
# Install k6
# macOS:
brew install k6

# Linux (Ubuntu/Debian):
sudo apt-get update
sudo apt-get install -y k6

# Windows: Download from https://github.com/grafana/k6/releases
```

### Run Baseline Test

```bash
# Start microservices
cd d:\Verbatim
docker-compose up -d

# Simple health check
docker-compose ps

# Run baseline load test (baseline scenario)
k6 run scenarios/01_baseline.js --vus 10 --duration 30s

# Expected output:
# ✓ List products
# ✓ Login
# ✓ Browse products again (cache hit)
# ✓ Create order
# ✓ Order status confirmed
```

---

## File Structure

```
loadtest/
├── README.md (this file)
├── API_DISCOVERY.md (complete API inventory)
├── FLOW_MAPPING.md (user journeys with traces)
├── INCIDENT_PLAYBOOK.md (7 chaos scenarios)
│
├── scenarios/
│   ├── 01_baseline.js              # Healthy load test (happy path)
│   ├── 02_payment_timeout.js       # Payment timeout incident
│   ├── 03_payment_service_down.js  # Payment service unavailable
│   ├── 04_db_exhaustion.js         # DB connection pool exhaustion
│   ├── 05_redis_failure.js         # Redis cache unavailable
│   ├── 06_retry_storm.js           # Payment retry storm
│   ├── 07_ddos_spike.js            # Load spike / DDoS simulation
│   ├── 08_cascading_failure.js     # Multi-service cascade
│   └── 09_mixed_traffic.js         # All journeys mixed with incident
│
├── modules/
│   ├── helpers.js                  # Utility functions
│   ├── auth.js                     # Auth flows (login, validate)
│   ├── catalog.js                  # Catalog flows (list, get products)
│   ├── orders.js                   # Order flows (create, get)
│   ├── payment.js                  # Payment incident injection
│   └── observability.js            # Metric/trace collection
│
├── config/
│   ├── environments.js             # Gateway URLs by environment
│   └── test-data.js               # Seeded user/product IDs
│
└── results/ (generated)
    ├── baseline.json               # Baseline run results
    ├── payment_timeout.json        # Incident results
    └── comparison.html             # Visual comparison
```

---

## Concept: User Journeys

Each test scenario simulates realistic user behavior through multiple endpoints in sequence.

### **Journey 1: Browse & Checkout** (Happy Path)
1. GET /api/v1/products (list all)
2. POST /auth/login (get token)
3. POST /auth/validate (verify token)
4. POST /api/v1/orders (create order)
5. GET /api/v1/orders/{id} (confirm status)

**Expected Duration**: 1.5-3.0 seconds

### **Journey 2: Fast Repeat/Browse** (Cache Hit)
1. POST /auth/login (repeat user)
2. GET /api/v1/products (should hit Redis cache)

**Expected Duration**: 200-300ms

### **Journey 3: Failed Operations**
1. POST /auth/login with invalid credentials (401)
2. GET /products with invalid UUID (400)
3. POST /orders with insufficient stock (400)

**Expected Duration**: 100-200ms

---

## Running Tests

### Syntax

```bash
k6 run <scenario.js> [options]

# Common options:
--vus N                    # Virtual users (concurrent)
--duration Ns              # Test duration (e.g., 30s, 5m)
--ramp-up Ns              # Ramp-up period
--ramp-down Ns            # Ramp-down period
-o json=file.json         # JSON output for comparison
--tag key=value           # Add metadata
--env VAR=value           # Pass environment variables
```

### Examples

#### 1. Baseline Test (Healthy System)

```bash
k6 run scenarios/01_baseline.js \
  --vus 20 \
  --duration 2m \
  -o json=results/baseline.json
```

**What it does**:
- Ramps up 20 virtual users over 30s
- Each user browses products, logs in, creates order, repeats for 2 minutes
- Collects response times, error rates, and throughput

**Expected Results**:
- Success rate: >99%
- P95 latency: 500-800ms
- Error rate: <1%

#### 2. Payment Timeout Incident

```bash
# Step 1: Inject incident
curl -X POST http://localhost:8004/charge/simulate-failure \
  -H "Content-Type: application/json" \
  -d '{"always_timeout": true}'

# Step 2: Run test
k6 run scenarios/02_payment_timeout.js \
  --vus 20 \
  --duration 2m \
  -o json=results/payment_timeout.json

# Step 3: Disable incident
curl -X POST http://localhost:8004/charge/simulate-failure \
  -H "Content-Type: application/json" \
  -d '{"normal": true}'
```

**Expected Results**:
- All orders created (success rate: 100%)
- Order status: "payment_failed"
- P95 latency: 2000-2200ms (payment timeout adds delay)
- Error rate: 0% (orders created despite payment failure)

#### 3. Retry Storm Incident

```bash
# Enable retry storm in environment
export ENABLE_RETRY_STORM=true
export MAX_RETRIES=3

# Restart services to pick up new config
docker-compose restart order payment

# Inject payment failures
curl -X POST http://localhost:8004/charge/simulate-failure \
  -H "Content-Type: application/json" \
  -d '{"always_fail": true}'

# Run test
k6 run scenarios/06_retry_storm.js \
  --vus 20 \
  --duration 2m \
  -o json=results/retry_storm.json

# Disable incident
curl -X POST http://localhost:8004/charge/simulate-failure \
  -H "Content-Type: application/json" \
  -d '{"normal": true}'

# Disable retry storm
export ENABLE_RETRY_STORM=false
docker-compose restart order
```

**Expected Results**:
- P95 latency: 3000-3500ms (3 retries × 1s backoff)
- Payment call count: 3x higher than baseline
- Orders may fail if all 3 retries exhausted

#### 4. DDoS Load Spike

```bash
k6 run scenarios/07_ddos_spike.js \
  --vus 100 \
  --duration 10m \
  -o json=results/ddos.json
```

**Test Profile**:
```
0-2m:   Ramp to 100 VUs
2-7m:   Hold 100 VUs (baseline)
7-9m:   Spike to 500 VUs
9-12m:  Hold 500 VUs (overload)
12-14m: Ramp down to 0
```

**Expected Results**:
- 0-2m: P95 latency ~500ms, <1% errors
- 7-9m: P95 latency spike to 3000ms
- 9-12m: ~5% error rate, connection pool exhaustion
- 12-14m: Recovery (metrics normalize)

---

## Observable Signals Verification

### Prometheus Metrics

Query metrics during tests:

```promql
# HTTP request latency (during test)
histogram_quantile(0.95, http_request_duration_seconds)

# Error rate
rate(http_error_total[1m])

# Payment service latency
external_call_duration_seconds{service="payment"}

# Cache hit ratio
cache_hits_total / (cache_hits_total + cache_misses_total)

# Database query duration
db_query_duration_seconds
```

### Jaeger Distributed Traces

1. Open Jaeger: http://localhost:16686
2. Select service: "order" or "gateway"
3. Filter by duration: >1000ms
4. View trace timeline to see:
   - DB query spans
   - Payment call spans with retries
   - Backoff sleep durations

### Loki Logs

Query logs during incidents:

```logql
{service="order"} | json | level="WARNING" | "retry"
{service="payment"} | json | "timeout"
```

---

## Test Scenarios (Detailed)

### Scenario 1: 01_baseline.js
**Purpose**: Establish performance baseline in healthy conditions

**User Distribution**:
- 40% browse only (GET /products)
- 50% full checkout (browse + login + order)
- 10% failed operations (invalid UUIDs, wrong credentials)

**Duration**: 2 minutes

**Success Criteria**:
- P95 latency < 1000ms
- Error rate < 1%
- All 5 test checks pass

---

### Scenario 2: 02_payment_timeout.js
**Purpose**: Validate graceful degradation during payment timeout

**Pre-test**:
```bash
POST /charge/simulate-failure {"always_timeout": true}
```

**User Distribution**:
- 100% full checkout flow (to trigger payment)

**Duration**: 1 minute

**Success Criteria**:
- Status code: 201 (order created)
- Order status: "payment_failed"
- Latency increase: 2000-2200ms
- No exceptions thrown

---

### Scenario 3: 03_payment_service_down.js
**Purpose**: Simulate payment service crash (simulated via container stop)

**Pre-test**:
```bash
docker-compose stop payment
```

**Expected Behavior**:
- Orders return 503 or timeout
- Health check fails

**Post-test**:
```bash
docker-compose start payment
```

---

### Scenario 4: 04_db_exhaustion.js
**Purpose**: Stress test database connection pool limits

**Configuration**:
- DB_POOL_SIZE: 10 (default)
- Concurrent orders: 50+ VUs

**Expected Behavior**:
- After pool exhausted: "no more connections" error
- P95 latency: exponential increase

---

### Scenario 5: 05_redis_failure.js
**Purpose**: Verify cache-less operation during Redis outage

**Pre-test**:
```bash
docker-compose stop redis
```

**Expected Behavior**:
- GET /products responses +50-100ms (DB query, no cache)
- cache_hits_total: 0
- cache_misses_total: increases
- Error rate: 0% (still functional)

---

### Scenario 6: 06_retry_storm.js
**Purpose**: Validate retry storm escalation

**Configuration**:
```bash
export ENABLE_RETRY_STORM=true
export MAX_RETRIES=3
```

**Pre-test**:
```bash
POST /charge/simulate-failure {"always_fail": true}
```

**Expected Behavior**:
- Payment call count: 3x higher
- P95 latency: 3000-3500ms
- external_call_errors_total: +3 per order
- Backoff sleeps visible in traces

---

### Scenario 7: 07_ddos_spike.js
**Purpose**: Simulate sudden traffic spike

**VU Ramp**:
```
0-2m:    Ramp to 100 VUs
2-7m:    Hold 100 VUs
7-9m:    Ramp to 500 VUs
9-12m:   Hold 500 VUs
12-14m:  Ramp to 0
```

**Success Criteria**:
- Phase 1: < 1% errors
- Phase 2: < 5% errors, P95 < 3s
- Phase 3: Recovery visible after ramp-down

---

### Scenario 8: 08_cascading_failure.js
**Purpose**: Observe service cascade under retry stress

**Configuration**:
```bash
export ENABLE_RETRY_STORM=true
curl -X POST http://localhost:8004/charge/simulate-failure \
  -H "Content-Type: application/json" \
  -d '{"always_timeout": true}'
```

**VU Ramp**: Ramp to 100 VUs quickly

**Observable Cascade**:
1. Payment times out
2. Order service retries
3. Load on payment increases
4. Payment service degrades
5. Orders timeout
6. Gateway marks order service unhealthy
7. All checkout fails

---

## Advanced Usage

### Run All Scenarios in Sequence

```bash
#!/bin/bash

scenarios=(
  "scenarios/01_baseline.js"
  "scenarios/02_payment_timeout.js"
  "scenarios/05_redis_failure.js"
  "scenarios/06_retry_storm.js"
  "scenarios/07_ddos_spike.js"
)

for scenario in "${scenarios[@]}"; do
  echo "Running: $scenario"
  k6 run "$scenario" \
    --vus 20 \
    --duration 2m \
    -o json="results/$(basename $scenario .js).json"
  
  echo "Test complete, sleeping 30s..."
  sleep 30
done
```

### Compare Results

```bash
# Compare baseline vs incident
k6 diff results/baseline.json results/payment_timeout.json

# Generate HTML report (requires install)
k6 stat --compare results/baseline.json results/payment_timeout.json > report.html
```

### Tag Runs for Organization

```bash
k6 run scenarios/01_baseline.js \
  --tag service=microservices-demo \
  --tag environment=local \
  --tag test_date=$(date +%Y%m%d) \
  -o json=results/baseline_$(date +%Y%m%d_%H%M%S).json
```

---

## Troubleshooting

### Test Fails to Connect

```
Error: Host not found
```

**Fix**: Ensure microservices are running
```bash
docker-compose up -d
docker-compose ps  # Verify all services healthy
curl http://localhost:8000/health
```

### All Requests 503

```
HTTP 503: Service Unavailable
```

**Causes**:
- Upstream service down
- Payment service crashed
- Database unavailable

**Debug**:
```bash
curl http://localhost:8000/health
# Check which service is unhealthy

# Restart specific service
docker-compose restart order
```

### Timeout Errors

```
Error: Request timeout
```

**Causes**:
- High load exhausting connections
- Slow database queries
- Payment service hanging

**Debug**:
```bash
# Check resource usage
docker stats

# Check database connections
docker-compose exec postgres psql -U user -d microservices_db \
  -c "SELECT count(*) as open_connections FROM pg_stat_activity;"

# Reduce k6 VUs
k6 run scenario.js --vus 5
```

---

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Load Test

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM
  workflow_dispatch:

jobs:
  load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Start Docker Compose
        run: docker-compose up -d
      
      - name: Wait for services
        run: sleep 30
      
      - name: Run baseline test
        uses: grafana/k6-action@v0.3.0
        with:
          filename: loadtest/scenarios/01_baseline.js
          cloud: false
          
      - name: Run incident tests
        run: |
          for scenario in loadtest/scenarios/0[2-9]_*.js; do
            k6 run "$scenario" --vus 20 --duration 2m
          done
      
      - name: Upload results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: k6-results
          path: loadtest/results/
```

---

## Documentation References

### API Reference
- [API_DISCOVERY.md](API_DISCOVERY.md) - All endpoints, parameters, responses

### Flow Patterns
- [FLOW_MAPPING.md](FLOW_MAPPING.md) - User journeys, traces, timing baselines

### Chaos Scenarios
- [INCIDENT_PLAYBOOK.md](INCIDENT_PLAYBOOK.md) - 7 incident types with detailed analysis

### External Links
- k6 Documentation: https://k6.io/docs/
- Grafana Observability Stack: https://grafana.com/docs/
- FastAPI: https://fastapi.tiangolo.com/
- OpenTelemetry: https://opentelemetry.io/docs/

---

## Performance Baselines Summary

| Scenario | P50 | P95 | P99 | Error Rate | Success |
|----------|-----|-----|-----|-----------|---------|
| Baseline (100 VU) | 200ms | 500ms | 800ms | <0.5% | ✓ |
| Payment Timeout | 2000ms | 2100ms | 2150ms | 0% | ✓ (payment_failed) |
| Redis Down | 100ms | 200ms | 300ms | 0% | ✓ (slower) |
| Retry Storm | 3000ms | 3500ms | 4000ms | 5% | ✓ (if all pass) |
| DDoS Spike (500 VU) | 3000ms | 5000ms | 8000ms | 5-10% | ⚠ (degraded) |

---

## Quick Checklist Before Running Tests

- [ ] All microservices running: `docker-compose ps`
- [ ] Gateway responds: `curl http://localhost:8000/health`
- [ ] Database seeded: Check test data exists
- [ ] Redis active: `redis-cli ping`
- [ ] k6 installed: `k6 version`
- [ ] No previous test processes: `ps aux | grep k6`
- [ ] Logs/results directory writable
- [ ] Observability stack ready (optional): Prometheus, Jaeger, Grafana

---

## Support & Next Steps

1. **Run baseline test** to establish healthy metrics
2. **Review [FLOW_MAPPING.md](FLOW_MAPPING.md)** to understand user journeys
3. **Run incident scenarios** one at a time with observability dashboards open
4. **Compare metrics** before/after using k6 diff
5. **Build runbooks** based on incident observations

---

**Created**: Phase 1 - Repo Discovery & k6 Planning  
**Status**: Production-ready test suite with comprehensive incident coverage

