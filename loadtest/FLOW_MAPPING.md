# Flow Mapping - User Journeys & Trace Propagation

**Scope**: End-to-end user flows through the microservices system with observability integration points.  
**Focus**: Real user behavior patterns, inter-service communication, and how traces propagate.

---

## User Journey 1: Browse & Checkout (Happy Path)

### Scenario
New user discovers products, logs in, and purchases items.

### Flow Diagram

```
┌───────────────────────────────────────────────────────┐
│                    k6 Load Test                       │
└─────────────────────┬─────────────────────────────────┘
                      │
                      ▼
        ┌─────────────────────────────────┐
        │  (1) GET /api/v1/products       │  List all products
        │      [trace_id: TID-001]        │
        └──────────┬──────────────────────┘
                   │
                   └──► Catalog Service
                       ├─ Redis cache miss
                       ├─ SELECT * FROM products
                       ├─ Cache each product
                       └─ Return [Product, Product, ...]
                           ↓ extract product_id for later
                      
        ┌─────────────────────────────────┐
        │  (2) POST /api/v1/auth/login    │  Login with test user
        │      {username, password}       │
        │      [trace_id: TID-002]        │
        │      [parent_span_id: ...]      │
        └──────────┬──────────────────────┘
                   │
                   └──► Auth Service
                       ├─ SELECT User WHERE username=?
                       ├─ verify_password(password, hash)
                       ├─ INSERT INTO sessions (token, expires_at)
                       └─ Return {token, user_id}
                           ↓ extract token & user_id
                      
        ┌─────────────────────────────────┐
        │  (3) POST /api/v1/orders        │  Checkout
        │      {user_id, items: [...]}    │
        │      [trace_id: TID-003]        │
        └──────────┬──────────────────────┘
                   │
                   └──► Order Service
                       ├─ SELECT User WHERE id=?
                       ├─ FOR each item:
                       │  ├─ SELECT Product WHERE id=?
                       │  ├─ Validate stock >= qty
                       │  └─ Calculate total
                       ├─ INSERT INTO orders (status=pending)
                       ├─ INSERT INTO order_items × N
                       │
                       ├─ CALL Payment Service
                       │  ├─ POST /charge 
                       │  │  {order_id, amount, currency}
                       │  │  [trace_context propagated]
                       │  │
                       │  └─ Payment Service (nested span)
                       │     ├─ Validate UUID
                       │     ├─ Check simulation state
                       │     ├─ Simulate outcome (80% success)
                       │     ├─ INSERT INTO payments
                       │     └─ Return {success: true, transaction_id}
                       │
                       ├─ UPDATE orders SET status=confirmed
                       └─ Return OrderResponse
                           ↓ extract order_id
                      
        ┌─────────────────────────────────┐
        │  (4) GET /api/v1/orders/{id}    │  Order confirmation
        │      [trace_id: TID-004]        │
        └──────────┬──────────────────────┘
                   │
                   └──► Order Service
                       ├─ SELECT Order WHERE id=?
                       ├─ SELECT OrderItems WHERE order_id=?
                       └─ Return OrderResponse
```

### Trace Context Propagation

**Trace ID**: Unique per initial user request  
**Span Context**: Propagated via `traceparent` header (W3C format)

```
GET /api/v1/products
  traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
  
  Generated: trace_id=4bf92f3577b34da6a3ce929d0e0e4736
            span_id=00f067aa0ba902b7
            
Client → Gateway → Catalog Service
  (trace propagated in HTTP headers)
```

### Expected Timings

| Step | Component | Duration | Notes |
|------|-----------|----------|-------|
| 1. List products | Catalog → Redis/DB | 50-200ms | First call slower (cache miss) |
| 2. Login | Auth → DB | 100-300ms | Password verification, session creation |
| 3. Checkout | Order → DB + Payment | 500-2000ms | Payment call adds latency |
| 4. Get order | Order → DB | 50-100ms | Simple lookup |
| **Total** | **Full journey** | **1-3 seconds** | Varies by cache state & payment |

### Observable Signals

**Metrics Produced**:
- `http_request_total{path="/api/v1/products", status="200"}` += 1
- `http_request_duration_seconds{path="/api/v1/products"}` observe ~100ms
- `cache_misses_total{service="catalog"}` += 4 (1 per product)
- `cache_hits_total{service="catalog"}` += 0
- `http_request_total{path="/api/v1/auth/login", status="200"}` += 1
- `http_request_duration_seconds{path="/api/v1/auth/login"}` observe ~150ms
- `http_request_total{path="/api/v1/orders", status="201"}` += 1
- `http_request_duration_seconds{path="/api/v1/orders"}` observe ~1000ms
- `external_call_duration_seconds{service="payment", endpoint="/charge"}` observe ~50ms
- `http_request_total{path="/api/v1/orders/{id}", status="200"}` += 1

**Traces Created**:
- Root span: POST /orders (1000ms, trace_id: TID-003)
  - Nested span: User validation (DB query, 10ms)
  - Nested span: Product lookup (DB query × 2, 20ms)
  - Nested span: Payment call (external, 50ms)

**Logs Generated**:
```json
{"level": "INFO", "message": "Order created", "order_id": "...", "user_id": "...", "total": "1337.97", "status": "confirmed", "trace_id": "TID-003"}
{"level": "DEBUG", "message": "Payment charge successful", "amount": "1337.97", "transaction_id": "txn_...", "trace_id": "TID-003"}
```

---

## User Journey 2: Repeat Login & Browse

### Scenario
Returning user logs in again, browses products, but doesn't purchase.

### Flow

```
(1) POST /api/v1/auth/login [trace_id: TID-005]
    → Auth Service: SELECT/INSERT session
    ← {token, user_id}
    
(2) POST /api/v1/auth/validate [trace_id: TID-006] (optional, for some UI flows)
    → Auth Service: SELECT Session WHERE token=?
    ← {valid: true, user_id}
    
(3) GET /api/v1/products [trace_id: TID-007]
    → Catalog Service: Check Redis (HIT! from previous user)
    ← [Product × 4] (cached, ~10ms)
```

### Duration & Observable Signals

| Step | Duration | Notes |
|------|----------|-------|
| Login | ~150ms | Same as Journey 1 |
| Validate token | ~50ms | Session lookup |
| List products | ~10ms | **Redis cache hit** |
| **Total** | ~210ms | Much faster than initial browse |

**Metrics**:
- `cache_hits_total{service="catalog"}` += 4 (Redis hit for all products)

---

## User Journey 3: Failed Login Attempt

### Scenario
User attempts login with wrong password.

### Flow

```
POST /api/v1/auth/login [trace_id: TID-008]
  {"username": "john_doe", "password": "wrong_password"}
  
  → Auth Service:
    ├─ SELECT User WHERE username = "john_doe" ✓
    ├─ verify_password("wrong_password", user.password_hash) ✗
    └─ Return {valid: false, message: "Invalid credentials"}
    
← {"data": {"valid": false, ...}}
  Status: 401
```

**Metrics**:
- `http_request_total{path="/api/v1/auth/login", status="401"}` += 1
- `auth_failures_total{reason="invalid_credentials"}` += 1

---

## User Journey 4: Order With Insufficient Stock

### Scenario
User creates order but product stock is depleted.

### Flow

```
POST /api/v1/orders [trace_id: TID-009]
  {"user_id": "...", "items": [{"product_id": "laptop_id", "quantity": 1000}]}
  
  → Order Service:
    ├─ SELECT User WHERE id=? ✓
    ├─ FOR item:
    │  ├─ SELECT Product WHERE id=? (stock_quantity: 50) ✓
    │  └─ Validate: 50 < 1000 ✗
    └─ Return "Insufficient stock" error
    
← {"status_code": 400, "detail": "Insufficient stock for product Laptop"}
```

**Metrics**:
- `http_request_total{path="/api/v1/orders", status="400"}` += 1

---

## User Journey 5: Payment Timeout Incident

### Scenario
User creates order, but payment service times out (incident enabled).

### Configuration
```bash
# Inject incident
curl -X POST http://localhost:8000/charge/simulate-failure \
  -H "Content-Type: application/json" \
  -d '{"always_timeout": true}'
```

### Flow

```
POST /api/v1/orders [trace_id: TID-010]
  
  → Order Service:
    ├─ Validate user ✓
    ├─ Validate items ✓
    ├─ CREATE order (status=pending)
    │
    ├─ CALL Payment Service [child_trace propagated]
    │  POST /charge {order_id, amount}
    │  
    │  → Payment Service (nested span, TID-010-child-001):
    │     ├─ Check simulation state → always_timeout=true
    │     ├─ Sleep 2 seconds
    │     └─ Return 504 Gateway Timeout
    │
    ├─ Catch timeout exception
    ├─ UPDATE orders SET status=payment_failed
    └─ Return OrderResponse {status: "payment_failed"}
    
← {"data": {"id": "...", "status": "payment_failed", ...}}
  Status: 201 (order created, but payment failed)
```

**Timeline**:
- t=0ms: Order creation starts
- t=50ms: Database writes complete
- t=50-2050ms: Payment call (timeout waiting)
- t=2050ms: Timeout caught, order updated to failed status
- t=2070ms: Response returned

**Metrics**:
- `http_request_total{path="/api/v1/orders", status="201"}` += 1
- `http_request_duration_seconds{path="/api/v1/orders"}` observe ~2050ms (spike!)
- `external_call_duration_seconds{service="payment", endpoint="/charge"}` observe ~2000ms (timeout)
- `external_call_errors_total{service="payment", error_type="timeout"}` += 1
- `payment_failures_total{reason="timeout"}` += 1

**Traces** (visible in Jaeger):
- Root: POST /orders (2000ms)
  - Child: DB writes (50ms)
  - Child: Payment call (2000ms) ✗ marked as error
  - Child: Status update (10ms)

**Logs**:
```json
{"level": "WARNING", "message": "Payment call timeout", "order_id": "...", "trace_id": "TID-010"}
{"level": "INFO", "message": "Order created with payment_failed status", "order_id": "...", "trace_id": "TID-010"}
```

---

## User Journey 6: Payment with Retry Storm

### Scenario
User creates order, payment fails initially, automatic retries applied.

### Configuration
```bash
export ENABLE_RETRY_STORM=true
export MAX_RETRIES=3
export INITIAL_BACKOFF_SECONDS=1
export MAX_BACKOFF_SECONDS=32
```

Also, inject 50% failure rate:
```bash
curl -X POST http://localhost:8004/charge/simulate-failure \
  -H "Content-Type: application/json" \
  -d '{"normal": true}' # Reset to normal with 80% success
# Or set PAYMENT_SUCCESS_RATE=0.5
```

### Flow

```
POST /api/v1/orders [trace_id: TID-011]
  
  → Order Service:
    ├─ Validate & create order (status=pending)
    │
    ├─ CALL Payment Service (attempt 1) [retry-attempt: 0]
    │  POST /charge → Payment Service
    │  Response: 500 Error (random failure) ✗
    │
    ├─ RETRY DECISION: 500 error, attempt 1 < max_retries(3)?
    │  YES → sleep exponential_backoff(0) ≈ 1.0s + jitter(0-0.1s)
    │
    ├─ CALL Payment Service (attempt 2) [retry-attempt: 1]
    │  POST /charge → Payment Service  
    │  Response: 500 Error ✗
    │
    ├─ RETRY: sleep exponential_backoff(1) ≈ 2.0s + jitter
    │
    ├─ CALL Payment Service (attempt 3) [retry-attempt: 2]
    │  POST /charge → Payment Service
    │  Response: 200 Success ✓
    │
    ├─ UPDATE orders SET status=confirmed
    └─ Return OrderResponse {status: "confirmed"}
```

### Timeline

```
t=0ms:            Order created (status=pending)
t=0-50ms:         First payment call (fails)
t=50-1150ms:      Backoff sleep (1s)
t=1150-1200ms:    Second payment call (fails)
t=1200-3400ms:    Backoff sleep (2s)
t=3400-3450ms:    Third payment call (succeeds) ✓
t=3450-3470ms:    Status update
t=3470ms:         Response returned
```

**Total Duration**: ~3.5 seconds

**Metrics** (shows retry behavior):
- `http_request_total{path="/api/v1/orders", status="201"}` += 1
- `http_request_duration_seconds{path="/api/v1/orders"}` observe ~3500ms (very high!)
- `external_call_duration_seconds{service="payment", endpoint="/charge"}` observed 3 times:
  - Attempt 1: ~50ms
  - Attempt 2: ~50ms
  - Attempt 3: ~50ms
- `external_call_errors_total{service="payment"}` += 2 (first two attempts)
- `payment_failures_total{reason="error"}` += 2
- **Key metric**: Number of payment calls **3x** higher than without retry storm

**Traces** (Jaeger view):
```
Root span: POST /orders (3500ms, trace_id: TID-011)
├─ Span: Order creation (50ms)
├─ Span: Payment attempt 1 (50ms) [status=error]
├─ Span: Backoff wait (1000ms)
├─ Span: Payment attempt 2 (50ms) [status=error]
├─ Span: Backoff wait (2000ms)
├─ Span: Payment attempt 3 (50ms) [status=ok]
└─ Span: Status update (20ms)
```

**Logs**:
```json
{"level": "WARNING", "message": "Payment call failed with 500, retrying in 1.05s (attempt 1/3)", "order_id": "...", "trace_id": "TID-011"}
{"level": "WARNING", "message": "Payment call failed with 500, retrying in 2.18s (attempt 2/3)", "order_id": "...", "trace_id": "TID-011"}
{"level": "INFO", "message": "Order created with confirmed status after retry", "order_id": "...", "trace_id": "TID-011"}
```

---

## Frontend Flow Distribution (for Load Testing)

### User Behavior Percentages

Based on typical e-commerce patterns:

| Flow | Percentage | Scenario |
|------|-----------|----------|
| Browse only (Journey 2) | 40% | Casual browsing, no purchase |
| Browse → Checkout (Journey 1) | 50% | Intent to buy, complete purchase |
| Failed login (Journey 3) | 5% | User enters wrong password |
| Insufficient stock (Journey 4) | 3% | Supply issue |
| Payment failure (Journey 5/6) | 2% | Incident or system failure |

### k6 Weighted Distribution

```javascript
// VU allocation
const users = {
  browsers: 40,      // 40% of VUs do browse flow
  buyers: 50,        // 50% of VUs do full checkout
  failed_login: 5,   // 5% attempt login failure
  stock_issues: 3,   // 3% trigger stock error
  payment_fail: 2,   // 2% experience payment failure
};
```

---

## Service Call Graph

### Direct Service Calls (per user request flow)

```
Gateway
├─ /products
│  └─ Catalog Service
│     ├─ Redis (cache check)
│     ├─ Database (product query)
│     └─ Redis (cache set)
│
├─ /auth/login
│  └─ Auth Service
│     ├─ Database (user lookup)
│     └─ Database (session insert)
│
├─ /auth/validate
│  └─ Auth Service
│     └─ Database (session lookup)
│
└─ /orders
   └─ Order Service
      ├─ Database (user lookup)
      ├─ FOR each item:
      │  └─ Database (product lookup)
      ├─ Database (order + order_items insert)
      ├─ Redis (optional caching)
      │
      └─ Payment Service (external call)
         ├─ Database (payment record)
         └─ (retry loop if enabled)
```

### Database Load per Flow

| Flow | SELECT Queries | INSERT Queries | UPDATE Queries |
|------|-------|-------|-------|
| Browse products (1 call) | 4 (product list) | 0 | 0 |
| Login (1 call) | 1 (user lookup) | 1 (session) | 0 |
| Validate token (1 call) | 1 (session lookup) | 0 | 0 |
| Checkout (1 call) | 3 (user + 2 products min) | 3 (order + items min) | 1 (order status) |
| Get order (1 call) | 2 (order + items) | 0 | 0 |
| **Total (full journey)** | **11** | **5** | **1** |

---

## Performance Baselines (Single User)

| Operation | Min | P50 | P95 | P99 | Max |
|-----------|-----|-----|-----|-----|-----|
| GET /products (cache hit) | 8ms | 15ms | 25ms | 35ms | 50ms |
| GET /products (cache miss) | 80ms | 120ms | 180ms | 250ms | 500ms |
| POST /login | 80ms | 150ms | 250ms | 350ms | 600ms |
| POST /validate | 30ms | 60ms | 100ms | 150ms | 200ms |
| POST /orders (payment ok) | 300ms | 800ms | 1500ms | 2000ms | 3000ms |
| POST /orders (payment timeout) | 2000ms | 2050ms | 2100ms | 2150ms | 2200ms |
| GET /orders/{id} | 30ms | 60ms | 100ms | 150ms | 200ms |

---

## Observability Alerts Mapping

### Alert Conditions (Prometheus)

| Alert | Condition | Incident Type |
|-------|-----------|---|
| `HighHTTPErrorRate` | error_rate(5m) > 5% | General failure |
| `PaymentTimeoutSpike` | external_call_duration_seconds{service="payment"} > 1000ms consistently | Payment incident |
| `RetryStormDetected` | external_call_errors_total{service="payment"} increasing rapidly | Retry storm active |
| `CacheMissRate` | cache_misses_total / cache_hits_total > 2 | Redis failure |
| `DatabaseSlowQueries` | db_query_duration_seconds > 500ms | DB bottleneck |
| `ServiceUnavailable` | check_upstream_service == down | Service down |

---

## k6 Test Mapping

### Scenario 1: Happy Path Load Test  
Uses Journey 1 (Browse → Checkout)

### Scenario 2: Login Spike  
Uses Journey 2 (Repeat Login)

### Scenario 3: Payment Timeout Incident  
Uses Journey 5 (with `/charge/simulate-failure` pre-test)

### Scenario 4: Retry Storm  
Uses Journey 6 (with `ENABLE_RETRY_STORM=true` pre-test)

### Scenario 5: Mixed Traffic  
Uses all journeys with percentages

---

**Next**: Create INCIDENT_PLAYBOOK.md with specific chaos scenarios and k6 implementation strategies.
