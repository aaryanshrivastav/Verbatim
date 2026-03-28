# Incident Playbook - Chaos Engineering Scenarios

**Scope**: 7 incident scenarios aligned with real failure modes, with k6 test strategies and observability correlations.  
**Goal**: Demonstrate system behavior under stress, validate observability, and practice incident response.

---

## Incident Matrix

| Incident | Type | Trigger | Health Status | Observable Signal | Recovery |
|----------|------|---------|---|---|---|
| 1. Payment Timeout | External Service | `/charge/simulate-failure` | 503 | P95 latency spike, external_call_errors ↑ | Toggle off |
| 2. Payment Service Down | Service Down | Stop container | 503 | Health check fails, timeout errors | Restart |
| 3. Database Connection Pool Exhausted | Resource | Connection leak | 500 | DB query errors, pool exhaustion | Restart services |
| 4. Redis Cache Failure | Cache | Redis down | 200 (degraded) | cache_misses ↑ dramatically | Restart Redis |
| 5. Retry Storm | Cascading | Enable + injection | 503/timeout spike | external_call_total ×3, latency ↑↑ | Disable toggle |
| 6. DDoS Load Spike | Capacity | k6 high VUs | 503/timeout | Error rate spike, resource saturation | Scale down |
| 7. Cascading Failure | Multi-Service | Chain reaction | 503 | Multiple service health checks fail | Manual intervention |

---

## Incident 1: Payment Timeout Scenario

### Story
During peak hours, payment gateway becomes slow. System must gracefully degrade: accept orders but mark them payment_failed.

### Trigger Strategy

**Pre-test**:
```bash
# Inject incident
curl -X POST http://localhost:8004/charge/simulate-failure \
  -H "Content-Type: application/json" \
  -d '{"always_timeout": true}'

# Verify
curl http://localhost:8003/orders/retry-config
# Expected: {"retry_enabled": false, "max_retries": 3, ...}
# If retry_enabled=false, timeout orders will fail immediately
```

### k6 Test Script Structure

```javascript
// 1. Setup phase
export const setup = () => {
  // Inject incident
  POST /charge/simulate-failure → {"always_timeout": true}
  
  // Get test data
  GET /products → extract product_ids
  POST /auth/login → extract token & user_id
  
  return {product_ids, user_id, token};
};

// 2. Main test
export default (data) => {
  // 3. Create order (expects timeout)
  let response = POST /orders with product_ids, expect status 201
  
  // 4. Verify: order status should be "payment_failed"
  check(response, {
    'order created despite timeout': (r) => r.body.includes('payment_failed'),
  });
  
  // 5. Optional: Get order to confirm
  GET /orders/{order_id} → verify status
};

// 6. Cleanup phase
export const teardown = () => {
  // Disable incident
  POST /charge/simulate-failure → {"normal": true}
};
```

### Expected Behavior

**Request Timeline**:
```
t=0ms:   POST /orders starts
t=50ms:  Order INSERT (pending status)
t=50ms:  Payment call starts (timeout=true in simulator)
t=2050ms: Payment call times out (2s delay in simulator)
t=2070ms: HTTP 504 caught
t=2080ms: Order status updated to payment_failed
t=2100ms: Response returned with status=payment_failed
```

**Response**:
```json
{
  "data": {
    "id": "order-uuid",
    "user_id": "user-uuid",
    "total_amount": "1337.97",
    "status": "payment_failed",
    "items": [...]
  }
}
```

**HTTP Status**: 201 (not 503, order creation succeeded)

### Observable Signals

**Metrics** (query in Prometheus):
```promql
# Spike in external call duration
increase(external_call_duration_seconds_bucket{service="payment",le="+Inf"}[1m])

# Error rate increase for payment calls
increase(external_call_errors_total{service="payment"}[1m])

# HTTP request duration spike for /orders endpoint
increase(http_request_duration_seconds_bucket{path="/orders",le="+Inf"}[1m])

# Specific increase in timeout errors
increase(external_call_errors_total{service="payment",error_type="timeout"}[1m])
```

**Expected Metric Values** (during incident):
- `external_call_duration_seconds`: 2000-2100ms per call (vs normal ~50ms)
- `external_call_errors_total{error_type="timeout"}`: increments by 1 per order
- `http_request_duration_seconds{path="/orders"}`: shifts from 500-800ms to 2000-2200ms percentiles

**Traces** (in Jaeger):
- Root span: POST /orders
  - Payment call span: 2000ms duration
  - Status: ERROR (timeout)
  - Error message: "Upstream service timeout"

**Logs** (JSON format):
```json
{"timestamp": "...", "level": "WARNING", "message": "Timeout calling Payment Service", "url": "http://localhost:8004/charge", "trace_id": "..."}
{"timestamp": "...", "level": "INFO", "message": "Order created with payment_failed status", "order_id": "...", "trace_id": "..."}
```

### Health Check Behavior

```bash
# During incident
curl http://localhost:8000/health
# Response:
{
  "healthy": false,
  "checks": {
    "auth": {"status": "ok"},
    "catalog": {"status": "ok"},
    "order": {"status": "ok"},
    "payment": {"status": "unhealthy", "error": "Timeout contacting service"},
    "database": {"status": "ok"},
    "redis": {"status": "ok"}
  }
}
# Status code: 503 (not healthy overall)
```

### k6 Success Criteria

```javascript
check(result, {
  'status is 201': (r) => r.status === 201,
  'order has payment_failed status': (r) => r.body.includes('payment_failed'),
  'latency < 3s': (r) => r.timings.duration < 3000,
  'response time increases': (r) => r.timings.duration > 1500,
});
```

### Recovery

```bash
# Disable incident
curl -X POST http://localhost:8004/charge/simulate-failure \
  -H "Content-Type: application/json" \
  -d '{"normal": true}'

# Verify payment works again
curl -X GET http://localhost:8003/orders/retry-config
# Response shows normal simulation state
```

---

## Incident 2: Payment Service Down

### Story
Payment service crashes due to bug. Orders fail completely until service restarts.

### Trigger Strategy

```bash
# Simulate by stopping the payment service container
docker-compose stop payment

# Verify failure
curl http://localhost:8004/charge/health
# Connection refused
```

### k6 Test Script

```javascript
export const setup = () => {
  // Don't actually stop service, instead:
  // 1. Take baseline metrics
  // 2. Record current health status
  POST /health → baseline
};

export default () => {
  // Attempt to create order
  let response = POST /orders
  
  // Expect 503 or timeout
  check(response, {
    'error received': (r) => r.status >= 500 || r.timings.duration > 10000,
    'not 201': (r) => r.status !== 201,
  });
};

export const teardown = () => {
  // In real scenario: docker-compose up payment
  // For test: verify recovery metrics
};
```

### Expected Behavior

**Order Creation Response**:
```json
{
  "detail": "Gateway Error",
  "status_code": 503
}
```

**OR (timeout after 10s)**:
```
Connection timeout / Network error
```

### Observable Signals

**Metrics**:
- `http_request_total{path="/orders", status="503"}` increases
- `external_call_errors_total{service="payment", error_type="unavailable"}` increases
- `http_request_duration_seconds{path="/orders"}`: increases to timeout value (~10s)

**Health Check**:
```bash
curl http://localhost:8000/health
# Status code: 503
# checks.payment: "unhealthy: Connection refused to http://localhost:8004"
```

**Traces** (if propagated):
- Root span: POST /orders
  - Payment call span: marked as ERROR
  - Error: "Connection refused"

---

## Incident 3: Database Connection Pool Exhaustion

### Story
Slow queries accumulate and exhaust the connection pool. New requests fail with "no more connections".

### Trigger Strategy

```bash
# Simulate by introducing artificial slow queries
# OR by creating many concurrent connections that hold locks

# In code: Add debug endpoint that creates slow query
curl -X POST http://localhost:8000/debug/slow-query \
  -d '{"duration_seconds": 30}'

# Repeat 10x to exhaust pool (default pool_size=10)
```

### k6 Test

```javascript
// 1. First, exhaust pool with slow queries
for (let i = 0; i < 10; i++) {
  POST /debug/slow-query → with 30s delay (in background)
}

// 2. Then try normal request
let response = POST /orders

// 3. Expect failure: no connections available
check(response, {
  'error due to pool exhaustion': (r) => 
    r.status >= 500 && r.body.includes('connection'),
});
```

### Observable Signals

**Metrics**:
- `db_query_duration_seconds`: spikes to 30s+
- `http_request_duration_seconds{path="/orders"}`: increases >30s
- `http_error_total{error_type="no_available_connections"}`: increases

**Traces**:
- Root span: POST /orders (>30s)
- Database query span: BLOCKED, waiting for connection

**Logs**:
```json
{"level": "ERROR", "message": "Unable to acquire database connection", "error": "SQLAlchemy: QueuePool limit exceeded", "trace_id": "..."}
```

### Recovery

```bash
# Option 1: Restart services to clear connections
docker-compose restart auth catalog order

# Option 2: Wait 30s for slow queries to complete naturally

# Verify
curl http://localhost:8000/health → should return healthy
```

---

## Incident 4: Redis Cache Failure

### Story
Redis goes offline. Catalog service still works but hits database on every request → performance degradation.

### Trigger Strategy

```bash
# Stop Redis
docker-compose stop redis

# Verify failure
curl http://localhost:8000/health
# redis check should show unhealthy
```

### k6 Test

```javascript
export default () => {
  // Perform repeated GET /products calls
  for (let i = 0; i < 5; i++) {
    let response = GET /products
    
    check(response, {
      'status ok': (r) => r.status === 200,
      'slower than before': (r) => r.timings.duration > 100, // normally ~15ms
    });
    
    sleep(0.5);
  }
};
```

### Expected Behavior

**Response**: Still returns 200 (catalog works without cache)

**Performance**:
- First call: ~80ms (DB query)
- Subsequent calls: ~80ms each (no caching benefit)
- vs. normal: ~10-20ms with cache

### Observable Signals

**Metrics**:
```promql
# Cache miss rate increases to 100%
increase(cache_misses_total{service="catalog"}[1m])
# Cache hit rate drops to 0
increase(cache_hits_total{service="catalog"}[1m]) → 0

# Database query count increases proportionally
increase(db_query_total{query_type="select"}[1m]) → ×5
```

**Traces**:
- Product lookup spans: no Redis cache lookup child span
- Direct DB query immediately follows

**Logs**:
```json
{"level": "WARNING", "message": "Redis connection failed", "error": "Connection refused", "trace_id": "..."}
{"level": "INFO", "message": "Fallback to database for product lookup", "product_id": "...", "trace_id": "..."}
```

**Health Check**:
```json
{
  "healthy": false,
  "checks": {
    "database": {"status": "ok"},
    "redis": {"status": "unhealthy", "error": "Connection refused"}
  }
}
```

### k6 Success Criteria

```javascript
check(result, {
  'catalog still responds': (r) => r.status === 200,
  'response slower': (r) => r.timings.duration > 80,
  'arrays match': (r) => r.body.length === 4, // 4 products
});
```

### Recovery

```bash
docker-compose up redis

# Verify
curl http://localhost:8000/health → redis check passes
```

---

## Incident 5: Retry Storm

### Story
Payment service has high failure rate. Order service retries aggressively, creating 3x traffic spike.

### Trigger Strategy

```bash
# 1. Enable retry storm feature
export ENABLE_RETRY_STORM=true
export MAX_RETRIES=3
export INITIAL_BACKOFF_SECONDS=1

# 2. Inject 50% payment failure rate (in simulation)
curl -X POST http://localhost:8004/charge/simulate-failure \
  -H "Content-Type: application/json" \
  -d '{"normal": true}'  # Reset to probabilistic (80% success)

# Actually, for predictable storm, set always_fail:
curl -X POST http://localhost:8004/charge/simulate-failure \
  -H "Content-Type: application/json" \
  -d '{"always_fail": true}'

# Now every payment will fail, triggering retries
```

### k6 Test

```javascript
export const setup = () => {
  POST /charge/simulate-failure → {"always_fail": true}
  return {triggered: true};
};

export default () => {
  // Create order - should see retries
  let response = POST /orders
  
  check(response, {
    'order created': (r) => r.status === 201,
    'long latency due to retries': (r) => r.timings.duration > 3000,
    'status still pending after all retries': (r) => r.body.includes('payment_failed'),
  });
};

export const teardown = () => {
  POST /charge/simulate-failure → {"normal": true}
};
```

### Expected Timeline

**For single order**:
```
t=0ms:     Order INSERT (status=pending)
t=50ms:    Retry attempt 1 → fails
t=50ms:    Sleep 1.0s + jitter
t=1100ms:  Retry attempt 2 → fails
t=1100ms:  Sleep 2.0s + jitter
t=3200ms:  Retry attempt 3 → fails (max reached)
t=3200ms:  Order status updated to payment_failed
t=3220ms:  Response returned

Total time: ~3.2 seconds per order (vs ~1s normal)
```

### Observable Signals

**Metrics** (dramatic):
```promql
# Payment service traffic increases 3x
external_call_total{service="payment"} → +3 per order

# HTTP request latency for /orders triples
http_request_duration_seconds_bucket{path="/orders"} → P95: 3000-3500ms

# Payment error rate increases
external_call_errors_total{service="payment"} → +3 per order

# Trace count per order increases
traces_created_total → +3 child spans per order
```

**Traces** (in Jaeger):
```
POST /orders (3200ms)
├─ Order creation (50ms)
├─ Payment attempt 1 (50ms) [error]
├─ Backoff sleep 1 (1000ms)
├─ Payment attempt 2 (50ms) [error]
├─ Backoff sleep 2 (2000ms)
├─ Payment attempt 3 (50ms) [error]
├─ Status update (20ms)
└─ Total: 3200ms
```

**Logs** (each retry):
```json
{"level": "WARNING", "message": "Payment call failed with 500, retrying in 1.05s (attempt 1/3)", "order_id": "...", "trace_id": "..."}
{"level": "WARNING", "message": "Payment call failed with 500, retrying in 2.18s (attempt 2/3)", "order_id": "...", "trace_id": "..."}
{"level": "WARNING", "message": "Payment call failed with 500, retrying in 4.32s (attempt 3/3)", "order_id": "...", "trace_id": "..."}
```

### k6 Scenarios

**Scenario A: Gradual Load**
- Ramp VUs from 1 to 50 over 5 minutes
- Each order takes 3.2s
- @ 50 VUs ≈ 15 orders/second = 45 payment calls/sec
- Observe queue buildup, latency increase

**Scenario B: Sustained Load**
- Hold 100 VUs for 10 minutes
- Stress test retry loop sustainability
- Monitor error rates, memory usage

### Recovery

```bash
# Disable retries
export ENABLE_RETRY_STORM=false

# OR disable payment failures
curl -X POST http://localhost:8004/charge/simulate-failure \
  -H "Content-Type: application/json" \
  -d '{"normal": true}'

# Monitor: order response times should drop back to 1s
```

---

## Incident 6: DDoS / Load Spike

### Story
Sudden traffic spike (e.g., marketing campaign). System becomes slow, some requests timeout.

### Trigger Strategy

**k6 test ramping**:
```javascript
import http from 'k6/http';

export const options = {
  stages: [
    { duration: '2m', target: 100 },   // Ramp to 100 VUs
    { duration: '5m', target: 100 },   // Stay at 100 VUs
    { duration: '2m', target: 500 },   // Spike to 500 VUs
    { duration: '3m', target: 500 },   // Sustain 500 VUs
    { duration: '2m', target: 0 },     // Ramp down
  ],
};

export default () => {
  // Heavy flow: browse + checkout
  GET /products
  POST /login
  POST /orders
};
```

### Observable Signals

**Metrics During Ramp**:
```
t=0-2min:   100 VUs
  - http_request_duration_seconds P95: ~500ms
  - error rate: <1%

t=2-7min:   100 VUs (stable)
  - same metrics

t=7-9min:   500 VUs (spike)
  - http_request_duration_seconds P95: 2000-3000ms (spike!)
  - http_error_total: increases
  - resource utilization: CPU/memory saturated

t=9-12min:  500 VUs (sustained)
  - some recovery as connections stabilize
  - P99: 3000-5000ms

t=12-14min: Ramp down
  - latencies improve
```

**Key Metrics**:
```promql
# Request duration increase
histogram_quantile(0.95, http_request_duration_seconds)
  Before spike: 500ms
  During spike: 3000ms

# Error rate spike
rate(http_error_total[1m])
  Before: 0.5%
  During spike: 5-10%

# Requests per second
rate(http_request_total[1m])
  Increases proportionally with VU count

# DB connection pool saturation
db_connections_in_use
  Approaches max (10 by default)

# Memory usage
container_memory_usage_bytes
  Increases significantly
```

**Health Check**:
```bash
curl http://localhost:8000/health

# During spike: 503 (degraded)
{
  "healthy": false,
  "checks": {
    "database": {
      "status": "unhealthy",
      "error": "Connection pool exhausted"
    },
    ...
  }
}
```

### k6 Assertions

```javascript
check(result, {
  'most requests succeed': (r) => responses.filter(r => r.status < 400).length > 0.95 * responses.length,
  'p95 under 5s': (stats) => stats.http_req_duration.p(95) < 5000,
  'error rate < 5%': (stats) => stats.http_req_failed.value < 0.05,
});
```

### Recovery (Scaling)

**Option 1: Horizontal Scaling**
```bash
# Increase DB pool size
export DB_POOL_SIZE=50

# Add more backend instances
docker-compose scale order=3 payment=3
```

**Option 2: Rate Limiting**
```bash
# Implement token bucket / sliding window
# (Would need code changes)
```

**Option 3: Manual Scaling Down**
```bash
# Reduce traffic by stopping attack
# Metrics should recover within 30s
```

---

## Incident 7: Cascading Failure

### Story
Payment service times out → Order service retries (if enabled) → Creates load spike on Payment → Payment service crashes from overload → Orders fail → Order service health check fails → Gateway marks Order service unhealthy → All checkout requests fail → Frontend shows errors.

### Trigger Strategy

**Sequence**:
1. Enable retry storm: `ENABLE_RETRY_STORM=true`
2. Slow payment service: `POST /charge/simulate-failure {"always_timeout": true}`
3. Spin up high concurrent load: k6 with 100+ VUs
4. Watch cascade unfold
5. Optional: Stop payment service entirely to complete cascade

### k6 Test

```javascript
export const setup = () => {
  // Trigger: Enable retry storm in environment
  POST /charge/simulate-failure → {"always_timeout": true}
  
  // Record metric baseline
  GET /health → baseline
};

export const options = {
  stages: [
    { duration: '1m', target: 50 },    // Ramp up
    { duration: '5m', target: 50 },    // Sustain to observe cascade
    { duration: '1m', target: 0 },     // Ramp down
  ],
};

export default () => {
  // Attempt full checkout (triggers payment calls)
  let response = POST /orders
  
  // First few requests should get payment_failed
  // As Payment service gets overwhelmed, might get 503
  check(response, {
    'response received': (r) => r.status >= 200,
  });
};

export const teardown = () => {
  POST /charge/simulate-failure → {"normal": true}
  
  // Wait for system to recover
  sleep(5);
  
  GET /health → verify recovery
};
```

### Timeline of Cascading Failure

```
t=0s:   k6 ramps to 50 VUs, POST /orders calls begin
        Payment service normal, but simulator returns timeout
        
t=30s:  Order service makes retry 1, retry 2, retry 3
        Each order takes 3.2s due to retries
        Payment service receives 3×50 = 150 payment calls/sec

t=60s:  Payment service becomes saturated
        Response times increase: 50ms → 500ms → 5s+
        Order service HTTP client timeouts (HTTP_TIMEOUT_SECONDS=10s)
        Orders start failing with "upstream timeout"
        
t=90s:  Payment service health check starts failing
        Order service /health endpoint detects payment service down
        
t=120s: Gateway health check detects Order service unhealthy
        Gateway /api/v1/orders endpoint returns 503
        
t=150s: Cascade complete
        - Frontend unable to create orders
        - All services report unhealthy
        - Error rate: 100%
        
If payment service container crashes at t=120s:
  - Connection refused errors
  - Order service still attempts retries (but fails immediately)
  - Cascade resolves if retries stopped, but latency remains high
```

### Observable Signals (Multi-layer)

**Layer 1: Payment Service Degradation**
```
external_call_duration_seconds{service="payment"} → increases from 2s to 10s+
external_call_errors_total{service="payment", error_type="timeout"} → increases
```

**Layer 2: Order Service Overload**
```
http_request_duration_seconds{path="/orders"} → P95: 15-30s (retries × timeouts)
db_connections_in_use → remains high (open connections waiting)
```

**Layer 3: Gateway Degradation**
```
http_request_total{path="/api/v1/orders", status="503"} → increases
http_error_total{error_type="upstream_unavailable"} → increases
```

**Health Checks** (sequential):
```
t=90s:  /orders/health:        503 (payment upstream fails)
t=120s: /health:               503 (order service marked unhealthy)
t=150s: /api/v1/orders:        503 (gateway can't route)
```

**Traces** (complexity increases):
```
t=30s (first request):
  ROOT POST /orders (3200ms)
  └─ Payment attempts 1, 2, 3 (timeout each)

t=90s (under load):
  ROOT POST /orders (>30 seconds, may timeout)
  ├─ Retries pending
  ├─ DB connection held open
  └─ Pending upstream calls
```

**Logs** (escalation):
```
t=30s:  WARNING "Payment call timeout, retrying"
t=60s:  WARNING "Multiple retries pending, delayed response"
t=90s:  ERROR "Order service health check failed: cannot contact Payment"
t=120s: ERROR "Gateway detected Order service unhealthy"
t=150s: ERROR "All Checkout requests failing"
```

### k6 Success Criteria (for cascade test)

```javascript
// Verify cascade occurred
check(aggregated_stats, {
  'early requests partially succeed': () => 
    success_rate_0min > 0.5,  // 50% success initially
  
  'late requests fail': () => 
    success_rate_3min < 0.05,  // <5% success at peak cascade
  
  'latencies increase dramatically': () => 
    p95_late > p95_early × 10,

  'health checks detect failure': () => 
    health_check_failures_detected,
});
```

### Recovery from Cascading Failure

**Automated Recovery**:
- Disable retry storm: `ENABLE_RETRY_STORM=false`
- Payment service recovers: `POST /charge/simulate-failure {"normal": true}`
- System gradually recovers (30-60s)

**Manual Recovery**:
```bash
# Option 1: Reduce load
# Stop k6 test

# Option 2: Restart payment service
docker-compose restart payment

# Option 3: Increase timeouts
export HTTP_TIMEOUT_SECONDS=30
docker-compose restart order

# Verify recovery
curl http://localhost:8000/health
# Should report healthy within 60s
```

---

## k6 Test Suite Structure

### File Organization

```
loadtest/
├── API_DISCOVERY.md
├── FLOW_MAPPING.md
├── INCIDENT_PLAYBOOK.md (this file)
├── README.md (setup & run instructions)
│
├── scenarios/
│   ├── 01_baseline.js          # Healthy load test
│   ├── 02_payment_timeout.js   # Incident 1
│   ├── 03_service_down.js      # Incident 2
│   ├── 04_db_exhaustion.js     # Incident 3
│   ├── 05_redis_failure.js     # Incident 4
│   ├── 06_retry_storm.js       # Incident 5
│   ├── 07_ddos_spike.js        # Incident 6
│   ├── 08_cascading.js         # Incident 7
│   └── 09_mixed_traffic.js     # All scenarios mixed
│
├── modules/
│   ├── helpers.js              # Shared utilities
│   ├── auth.js                 # Login/validate flows
│   ├── catalog.js              # Product browse flows
│   ├── orders.js               # Order creation flows
│   └── observability.js        # Metric extraction
│
└── config/
    ├── environments.js         # Dev/staging/prod URLs
    └── test-data.js           # Seeded user/product IDs
```

### Execution Commands

```bash
# Run baseline (healthy)
k6 run scenarios/01_baseline.js -o json=results/baseline.json

# Run single incident (e.g., payment timeout)
k6 run scenarios/02_payment_timeout.js --vus 50 --duration 5m

# Run all incidents in sequence
for scenario in scenarios/*.js; do
  k6 run $scenario --vus 50 --duration 5m
done

# Run with custom environment
k6 run scenarios/01_baseline.js --env GATEWAY_URL=http://staging:8000

# Compare results
k6 diff results/baseline.json results/payment_timeout.json
```

---

## Success Metrics

### Per-Incident Validation

| Incident | Expected Outcome | Validation |
|----------|---|---|
| 1. Payment Timeout | Orders created with payment_failed status | Check response status & order.status field |
| 2. Service Down | Orders return 503 | Check response status code |
| 3. DB Pool Exhaustion | Requests timeout or fail with pool error | Check response status & error message |
| 4. Redis Failure | Catalog slower but functional | Check latency spike + cache metrics |
| 5. Retry Storm | Visible request latency spike (3x) | Check P95 duration & retry count metrics |
| 6. DDoS Load | Error rate < 10%, P95 < 5s | Check thresholds met under load |
| 7. Cascading | Multi-layer failure visible in traces | Check health cascade in Jaeger |

### Observable Signal Checklist

- [ ] Metrics correlate with incident (Prometheus)
- [ ] Traces show incident path (Jaeger)
- [ ] Logs document issue escalation (Loki)
- [ ] Health endpoints report degradation
- [ ] Error messages specific to incident
- [ ] Recovery metrics confirm resolution

---

**Next Steps**:

1. Implement k6 scenario files based on incident descriptions
2. Set up result comparison workflows
3. Create runbooks for each incident
4. Integrate with CI/CD for continuous testing
5. Build incident response playbooks for oncall team

