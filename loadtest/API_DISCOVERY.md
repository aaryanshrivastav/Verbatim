# API Discovery - Microservices Observability Demo

**Scope**: Complete inventory of all HTTP endpoints across gateway and 5 microservices, extracted from production code.  
**Date Generated**: Phase 1 - Repo Discovery  
**Infrastructure**: Python FastAPI, SQLAlchemy 2.0 async, PostgreSQL + SQLite (tests), Redis 5.0.1, httpx

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Frontend / k6 Load Tester                      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                    /api/v1 (gateway)
                           │
        ┌──────────────────┴──────────────────┬───────────────────┐
        │                                     │                   │
    ┌───▼────┐                          ┌────▼────┐            ┌──▼────┐
    │ Auth   │                          │ Catalog │            │ Order │
    │Service │                          │ Service │            │Service│
    └───┬────┘                          └───┬─────┘            └──┬────┘
        │ GET /auth/validate                │ GET /products       │
        │ POST /auth/login                  │ GET /products/{id}  │
        │ GET /health                       │ GET /health         │
        │ GET /metrics                      │ GET /metrics        │
        │                                   │                     │ POST /orders
        │                                   │                     │ GET /orders/{id}
        │                                   │                     │ GET /health
        │                                   │                     │ GET /metrics
        │                                   │                     │ GET /retry-config
        │                                   │                     │
        └──────────────────────────────────┴─────────────────────┤
                                                                 │
                            ┌──────────────┬───────────┬─────────┘
                            │              │           │
                       ┌────▼──┐      ┌────▼──┐  ┌───▼────┐
                       │Payment│      │ Redis │  │Database│
                       │Service│      │ Cache │  │ (PgSQL)│
                       └────┬──┘      └───────┘  └────────┘
                            │
                   POST /charge (retry storm)
                   GET /charge/{order_id}
                   POST /charge/simulate-failure
```

---

## Gateway Endpoints

**Base URL**: `http://localhost:8000/api/v1`  
**Proxy Behavior**: Wraps internal service responses in `{"data": ...}` envelope

### 1. GET /api/v1/products
- **Description**: List all products (from catalog service)
- **Method**: GET
- **Query Parameters**: None
- **Auth**: Optional token validation
- **Response**:
  ```json
  {
    "data": [
      {
        "id": "uuid",
        "name": "Laptop",
        "description": "High-performance laptop",
        "price": "1299.99",
        "stock_quantity": 50
      },
      ...
    ]
  }
  ```
- **Status Codes**: 
  - 200: Success
  - 503: Catalog service unavailable
- **Cache**: Redis (TTL: 3600s), 1 key per product: `product:{product_id}`
- **Observability**:
  - Trace: Spans for GET request to catalog, Redis cache lookup, DB query
  - Metrics: http_request_total, http_request_duration_seconds, cache_hits_total, cache_misses_total
- **Service Call**: `catalog-service:GET /products`

### 2. GET /api/v1/products/{product_id}
- **Description**: Get single product by ID
- **Method**: GET
- **Path Params**: 
  - `product_id` (UUID)
- **Response**:
  ```json
  {
    "data": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Laptop",
      "description": "High-performance laptop",
      "price": "1299.99",
      "stock_quantity": 50
    }
  }
  ```
- **Status Codes**: 
  - 200: Success
  - 400: Invalid UUID format
  - 404: Product not found
  - 503: Service unavailable
- **Cache**: Redis, key: `product:{product_id}`
- **Observability**: Same as list products
- **Service Call**: `catalog-service:GET /products/{product_id}`

### 3. POST /api/v1/auth/login
- **Description**: Authenticate user, return token
- **Method**: POST
- **Content-Type**: application/json
- **Request Body**:
  ```json
  {
    "username": "john_doe",
    "password": "secret"
  }
  ```
- **Response**:
  ```json
  {
    "data": {
      "token": "secure_token_32bytes_generated_via_secrets.token_urlsafe(32)",
      "user_id": "550e8400-e29b-41d4-a716-446655440000"
    }
  }
  ```
- **Status Codes**: 
  - 200: Success
  - 401: Invalid credentials
  - 500: Server error
  - 503: Auth service unavailable
- **Authentication**: None (login endpoint)
- **Database**: 
  - Query: SELECT User WHERE username = ?
  - Insert: INSERT INTO sessions (user_id, token, expires_at) (if ENABLE_SESSIONS=true)
  - Token exp: 24 hours
- **Observability**:
  - Traces: Login route, DB query, password verification span, session create span
  - Metrics: auth_failures_total (on failed login)
  - Logs: Login attempt (structlog JSON)
- **Service Call**: `auth-service:POST /auth/login`
- **Test Data**: `username: john_doe` or `jane_smith`, `password: secret`

### 4. POST /api/v1/auth/validate
- **Description**: Validate token OR username/password
- **Method**: POST
- **Request Body** (3 variants):
  - Token validation:
    ```json
    {
      "token": "secure_token_from_login"
    }
    ```
  - Credentials validation:
    ```json
    {
      "username": "john_doe",
      "password": "secret"
    }
    ```
  - Invalid (both missing):
    ```json
    {}
    ```
- **Response**:
  ```json
  {
    "data": {
      "valid": true,
      "user_id": "550e8400-e29b-41d4-a716-446655440000",
      "message": "Token valid" OR "Credentials valid"
    }
  }
  ```
- **Status Codes**: 
  - 200: Success (valid OR invalid credential response)
  - 500: Server error
  - 503: Service unavailable
- **Database**: 
  - Token path: SELECT Session WHERE token=? AND expires_at > NOW()
  - Credentials path: SELECT User WHERE username=? AND password=hash(?)
- **Observability**: Traces, metrics, logs similar to login
- **Service Call**: `auth-service:POST /auth/validate`

### 5. POST /api/v1/orders
- **Description**: Create checkout order (complex orchestration)
- **Method**: POST
- **Content-Type**: application/json
- **Request Body**:
  ```json
  {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "items": [
      {
        "product_id": "660e8400-e29b-41d4-a716-446655440001",
        "quantity": 2
      },
      {
        "product_id": "660e8400-e29b-41d4-a716-446655440002",
        "quantity": 1
      }
    ]
  }
  ```
- **Response**:
  ```json
  {
    "data": {
      "id": "770e8400-e29b-41d4-a716-446655440000",
      "user_id": "550e8400-e29b-41d4-a716-446655440000",
      "total_amount": "3099.97",
      "status": "confirmed",
      "items": [
        {
          "id": "item_uuid_1",
          "product_id": "660e8400-e29b-41d4-a716-446655440001",
          "quantity": 2,
          "unit_price": "1299.99"
        },
        ...
      ]
    }
  }
  ```
- **Status Codes**: 
  - 201: Order created successfully
  - 400: Invalid input (bad UUID format, product not found, insufficient stock)
  - 500: Server error
  - 503: Order or payment service unavailable
- **Order Status Flow**:
  - `pending` → (payment call) → `confirmed` (success) OR `payment_failed` (timeout/error)
- **Internal Flow**:
  1. Validate user exists (DB query)
  2. For each item:
     - Validate product exists (DB query)
     - Check stock >= quantity
     - Calculate line total
  3. Create Order record (status="pending")
  4. Create OrderItem records for each item
  5. **Call payment service** (POST /charge) with retry logic
  6. Update order status based on payment result
  7. Return order with final status
- **Payment Service Calls** (retry logic if ENABLE_RETRY_STORM=true):
  - Method: POST
  - Path: `payment-service:POST /charge`
  - Payload: `{"order_id": str(order.id), "amount": str(total_amount), "currency": "USD"}`
  - Retry: exponential backoff (1s, 2s, 4s, 8s, 16s, 32s cap)
  - Max attempts: MAX_RETRIES (default: 3) if ENABLE_RETRY_STORM else 1
- **Database Writes**:
  - INSERT INTO orders (user_id, total_amount, status, created_at)
  - INSERT INTO order_items (order_id, product_id, quantity, unit_price) x N
  - Insert/Update INTO payments (see payment service)
- **Observability**:
  - Traces: 
    - Root span: POST /orders
    - Nested: user validation, product lookups, payment call with retries
  - Metrics:
    - http_request_total (orders endpoint)
    - external_call_duration_seconds (payment call)
    - external_call_errors_total (failed payment calls)
  - Logs: Order creation, payment call attempts and results
- **Service Calls**: 
  - `catalog-service:GET /products` (via SELECT Product from DB, but also validates via payment flow)
  - `payment-service:POST /charge` (retry logic if enabled)
- **Test Data Requirements**:
  - Valid user_id from DB
  - Valid product_ids from DB (seeded: Laptop, Monitor, Keyboard, Mouse)
  - Stock > 0
  - Item quantities

### 6. GET /api/v1/orders/{order_id}
- **Description**: Get order details with items
- **Method**: GET
- **Path Params**: 
  - `order_id` (UUID)
- **Response**:
  ```json
  {
    "data": {
      "id": "770e8400-e29b-41d4-a716-446655440000",
      "user_id": "550e8400-e29b-41d4-a716-446655440000",
      "total_amount": "3099.97",
      "status": "confirmed",
      "items": [...]
    }
  }
  ```
- **Status Codes**: 
  - 200: Success
  - 400: Invalid UUID format
  - 404: Order not found
  - 503: Service unavailable
- **Cache**: None (orders are mutable, real-time queries)
- **Service Call**: `order-service:GET /orders/{order_id}`

---

## Internal Service Endpoints

### Catalog Service

**Base URL**: `http://localhost:8002` (internal, not via gateway)

#### GET /products
- Same as gateway endpoint
- **Port**: 8002
- **Response Type**: Array of ProductResponse

#### GET /products/{product_id}
- Same as gateway endpoint
- **Port**: 8002

#### GET /products/health
- **Description**: Health check (database + Redis)
- **Response**:
  ```json
  {
    "status_code": 200,
    "healthy": true,
    "checks": {
      "database": {"status": "ok", ...},
      "redis": {"status": "ok", ...}
    }
  }
  ```
- **Status Codes**: 
  - 200: All healthy
  - 503: One or more unhealthy

#### GET /products/metrics
- **Description**: Prometheus-format metrics
- **Response**: Plain text (Prometheus format)
- **Example**:
  ```
  # HELP http_requests_total Total HTTP requests
  # TYPE http_requests_total counter
  http_requests_total{method="GET",path="/products",status="200"} 1234
  ...
  ```

---

### Auth Service

**Base URL**: `http://localhost:8001` (internal)

#### POST /auth/login
- Same as gateway endpoint
- **Port**: 8001
- **Database Tables**: users, sessions
- **Session TTL**: 24 hours

#### POST /auth/validate
- Same as gateway endpoint
- **Port**: 8001

#### GET /auth/health
- Same structure as catalog health
- **Checks**: database only (no Redis dependency)

#### GET /auth/metrics
- Prometheus format metrics
- **Metrics**: auth_failures_total, http_requests_total, etc.

---

### Order Service

**Base URL**: `http://localhost:8003` (internal)

#### POST /orders
- Same as gateway endpoint (but direct call)
- **Port**: 8003

#### GET /orders/{order_id}
- Same as gateway endpoint
- **Port**: 8003

#### GET /orders/health
- **Description**: Health check (database, Redis, payment service upstream)
- **Response**:
  ```json
  {
    "status_code": 200,
    "healthy": true,
    "checks": {
      "database": {...},
      "redis": {...},
      "payment_service": {...}
    }
  }
  ```
- **Upstream Check**: Calls `PAYMENT_SERVICE_URL/health`

#### GET /orders/metrics
- Prometheus format

#### GET /orders/retry-config
- **Description**: Hidden endpoint - returns current retry configuration (useful for retry-storm demo)
- **Response**:
  ```json
  {
    "retry_enabled": false,
    "max_retries": 3,
    "initial_backoff_seconds": 1.0,
    "max_backoff_seconds": 32.0,
    "http_timeout_seconds": 10.0
  }
  ```
- **Status Code**: 200
- **Use Case**: Load test verification, documentation of current config

---

### Payment Service

**Base URL**: `http://localhost:8004` (internal)

#### POST /charge
- **Description**: Process payment, simulated with configurable success/failure/timeout rates
- **Method**: POST
- **Request Body**:
  ```json
  {
    "order_id": "770e8400-e29b-41d4-a716-446655440000",
    "amount": "3099.97",
    "currency": "USD"
  }
  ```
- **Response** (Success):
  ```json
  {
    "success": true,
    "order_id": "770e8400-e29b-41d4-a716-446655440000",
    "transaction_id": "txn_770e8400e29b",
    "status": "completed",
    "message": "Payment processed successfully"
  }
  ```
- **Response** (Failure):
  ```json
  {
    "success": false,
    "order_id": "770e8400-e29b-41d4-a716-446655440000",
    "transaction_id": null,
    "status": "failed",
    "message": "Payment gateway error" OR "Payment gateway timeout"
  }
  ```
- **Status Codes**: 
  - 200: Payment processed (check success field)
  - 400: Invalid order ID format
  - 500: Payment gateway error (failure scenario)
  - 504: Payment gateway timeout (failure scenario)
- **Simulation Modes** (controlled by POST /charge/simulate-failure):
  - `normal` (default): 80% success, 10% timeout, 10% error (configurable)
  - `always_timeout`: All requests return 504 after 2s delay
  - `always_fail`: All requests return 500
- **Database**: INSERT/UPDATE INTO payments table
- **Retry Behavior**: Order service calls this with exponential backoff if ENABLE_RETRY_STORM=true

#### GET /charge/{order_id}
- **Description**: Get payment status for order
- **Method**: GET
- **Response**:
  ```json
  {
    "success": true/false,
    "order_id": "...",
    "transaction_id": "...",
    "status": "completed" OR "failed" OR "pending",
    "message": "..."
  }
  ```
- **Status Codes**: 
  - 200: Success
  - 400: Invalid UUID format
  - 404: No payment found
  - 503: Service error

#### POST /charge/simulate-failure
- **Description**: Toggle payment simulation mode (for incident testing)
- **Method**: POST
- **Request Body** (mutually exclusive):
  ```json
  {
    "always_timeout": true
  }
  ```
  OR
  ```json
  {
    "always_fail": true
  }
  ```
  OR
  ```json
  {
    "normal": true
  }
  ```
- **Response**:
  ```json
  {
    "message": "Payment simulation updated",
    "state": {
      "always_timeout": true,
      "always_fail": false,
      "normal": false
    }
  }
  ```
- **Status Code**: 200
- **Use Case**: Incident injection, chaos engineering

#### GET /charge/health
- Same structure as other services

#### GET /charge/metrics
- Prometheus format

---

### Main Application

**Base URL**: `http://localhost:8000` (unified entry point)

#### GET /
- **Description**: Service info and documentation links
- **Response**:
  ```json
  {
    "service": "Microservices Observability Demo",
    "version": "1.0.0",
    "docs": {
      "swagger": "/docs",
      "openapi": "/openapi.json"
    },
    "services": [
      {"name": "Auth", "url": "http://localhost:8001"},
      {"name": "Catalog", "url": "http://localhost:8002"},
      {"name": "Order", "url": "http://localhost:8003"},
      {"name": "Payment", "url": "http://localhost:8004"},
      {"name": "Gateway", "url": "http://localhost:8000/api/v1"}
    ]
  }
  ```
- **Status Code**: 200

#### GET /health
- **Description**: Aggregate health check (all services)
- **Response**:
  ```json
  {
    "healthy": true,
    "checks": {
      "auth": {"status": "ok", ...},
      "catalog": {"status": "ok", ...},
      "order": {"status": "ok", ...},
      "payment": {"status": "ok", ...},
      "database": {"status": "ok", ...},
      "redis": {"status": "ok", ...}
    }
  }
  ```
- **Status Codes**: 
  - 200: All healthy
  - 503: One or more unhealthy

#### GET /readiness
- **Description**: Readiness probe (for orchestration, like Kubernetes)
- **Response**: 
  ```json
  {
    "ready": true,
    "details": {...}
  }
  ```
- **Status Codes**: 
  - 200: Ready to accept traffic
  - 503: Not ready

#### GET /liveness
- **Description**: Liveness probe (process is alive)
- **Response**:
  ```json
  {
    "alive": true
  }
  ```
- **Status Code**: 200

#### GET /metrics
- **Description**: Prometheus metrics from all services aggregated
- **Response**: Plain text Prometheus format

---

## Key Configuration & Failure Modes

### Environment Variables (from `shared/config.py`)

| Variable | Default | Purpose | Impact |
|----------|---------|---------|--------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection | All services |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis cache | Catalog product cache |
| `REDIS_CACHE_TTL` | 3600 | Cache TTL seconds | Product cache refresh |
| `AUTH_SERVICE_URL` | `http://localhost:8001` | Internal auth service URL | Gateway routing |
| `CATALOG_SERVICE_URL` | `http://localhost:8002` | Internal catalog service URL | Gateway routing |
| `ORDER_SERVICE_URL` | `http://localhost:8003` | Internal order service URL | Gateway routing |
| `PAYMENT_SERVICE_URL` | `http://localhost:8004` | Internal payment service URL | Order → payment calls |
| `ENABLE_RETRY_STORM` | false | Enable retry logic in orders | Payment call behavior |
| `MAX_RETRIES` | 3 | Max retry attempts | Retry storm incident |
| `INITIAL_BACKOFF_SECONDS` | 1.0 | Initial backoff duration | Retry timing |
| `MAX_BACKOFF_SECONDS` | 32.0 | Max backoff duration | Retry timing |
| `HTTP_TIMEOUT_SECONDS` | 10.0 | HTTP request timeout | Inter-service calls |
| `PAYMENT_SUCCESS_RATE` | 0.8 | Probability of success | Payment simulation (normal mode) |
| `PAYMENT_TIMEOUT_RATE` | 0.1 | Probability of timeout | Payment simulation (normal mode) |

### Incident Injection Points

1. **Payment Timeout Incident**: 
   - Toggle: `ENABLE_RETRY_STORM=true` + `PAYMENT_TIMEOUT_RATE=1.0`
   - OR: `POST /charge/simulate-failure` → `{"always_timeout": true}`
   - Effect: All payment calls timeout → Order creates with `payment_failed` status

2. **Payment Error Incident**: 
   - Toggle: `POST /charge/simulate-failure` → `{"always_fail": true}`
   - Effect: All payment calls return 500

3. **Retry Storm Incident**:
   - Toggle: `ENABLE_RETRY_STORM=true`
   - Effect: Failed payments retry with exponential backoff (up to 3 times)
   - Observability: external_call_total increments 3x per order, traces show retry spans

4. **Database Failure**: 
   - Stop PostgreSQL
   - Effect: All endpoints return 500, health endpoint returns 503

5. **Redis Failure**:
   - Stop Redis
   - Effect: Catalog reads hit DB every time (slower), cache_misses_total increases

6. **Upstream Service Failure** (e.g., payment service down):
   - Stop payment service
   - Effect: Order creation returns 503 or hangs (timeout)

7. **DDoS / High Load**:
   - Increase k6 concurrent users
   - Monitor: http_request_duration_seconds increase, error rates, trace latency

---

## Test Data & Seeding

### Default Seeded Data

**Users**:
- `john_doe` (password: `secret`)
- `jane_smith` (password: `secret`)

**Products**:
- Laptop: $1299.99 (stock: 50)
- Monitor: $599.99 (stock: 100)
- Keyboard: $199.99 (stock: 200)
- Mouse: $49.99 (stock: 300)

### UUID Format

- User IDs: UUID4
- Product IDs: UUID4
- Order IDs: UUID4
- Session tokens: `secrets.token_urlsafe(32)` (~43 chars)
- Transaction IDs: `txn_{order_uuid.hex[:12]}`

---

## Database Schema

```sql
-- Users
CREATE TABLE users (
  id UUID PRIMARY KEY,
  username VARCHAR UNIQUE NOT NULL,
  email VARCHAR UNIQUE NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);

-- Sessions (if ENABLE_SESSIONS=true)
CREATE TABLE sessions (
  id UUID PRIMARY KEY,
  user_id UUID FOREIGN KEY,
  token VARCHAR UNIQUE NOT NULL,
  expires_at TIMESTAMP NOT NULL,
  created_at TIMESTAMP NOT NULL
);

-- Products
CREATE TABLE products (
  id UUID PRIMARY KEY,
  name VARCHAR UNIQUE NOT NULL,
  description TEXT,
  price NUMERIC(10,2) NOT NULL,
  stock_quantity INT NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);

-- Orders
CREATE TABLE orders (
  id UUID PRIMARY KEY,
  user_id UUID FOREIGN KEY NOT NULL,
  total_amount NUMERIC(12,2) NOT NULL,
  status VARCHAR(50) NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);

-- Order Items
CREATE TABLE order_items (
  id UUID PRIMARY KEY,
  order_id UUID FOREIGN KEY NOT NULL,
  product_id UUID FOREIGN KEY NOT NULL,
  quantity INT NOT NULL,
  unit_price NUMERIC(10,2) NOT NULL,
  created_at TIMESTAMP NOT NULL
);

-- Payments
CREATE TABLE payments (
  id UUID PRIMARY KEY,
  order_id UUID FOREIGN KEY NOT NULL,
  amount NUMERIC(12,2) NOT NULL,
  status VARCHAR(50) NOT NULL,
  payment_method VARCHAR(100) NOT NULL,
  transaction_id VARCHAR(255) UNIQUE,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);

-- Cache Invalidation Log
CREATE TABLE cache_invalidation_log (
  id UUID PRIMARY KEY,
  entity_type VARCHAR(100) NOT NULL,
  entity_id UUID NOT NULL,
  reason VARCHAR(255),
  created_at TIMESTAMP NOT NULL
);
```

---

## Redis Cache Structure

| Key Pattern | Value Type | TTL | Description |
|------------|-----------|-----|-------------|
| `product:{product_id}` | JSON (ProductResponse) | 3600s | Cached product details |

---

## Observable Signals (OpenTelemetry)

### Metrics (Prometheus format)

**HTTP Metrics**:
- `http_request_total{method, path, status}` - Counter
- `http_request_duration_seconds{method, path}` - Histogram
- `http_error_total{method, path, error_type}` - Counter

**External Call Metrics**:
- `external_call_duration_seconds{service, endpoint}` - Histogram
- `external_call_errors_total{service, endpoint, error_type}` - Counter

**Database Metrics**:
- `db_query_duration_seconds{query_type}` - Histogram
- `db_query_errors_total{query_type}` - Counter

**Cache Metrics**:
- `cache_hits_total{service}` - Counter
- `cache_misses_total{service}` - Counter

**Service-Specific Metrics**:
- `auth_failures_total{reason}` - Counter (invalid creds, token expired)
- `payment_failures_total{reason}` - Counter (timeout, error)

### Traces

**Root Spans**:
- POST /api/v1/orders (parent span)
  - Child: User validation (DB query)
  - Child: Product lookups (DB queries) × N
  - Child: Payment call (external call, possibly with retry spans)
  - Context: trace_id, span_id propagated across services

**Trace Propagation**:
- W3C Trace Context headers: traceparent, tracestate
- Order service → Payment service calls include trace context

### Logs

**Format**: JSON (via structlog)

**Examples**:
```json
{"timestamp": "...", "level": "INFO", "message": "Order created", "order_id": "...", "user_id": "...", "trace_id": "..."}
{"timestamp": "...", "level": "WARNING", "message": "Payment call failed", "attempt": 1, "retry_in": 1.5, "trace_id": "..."}
```

---

## k6 Load Testing Integration Points

### Data Extraction for k6

1. **Static Test Data**:
   - User IDs: Query DB or hardcode from seeding
   - Product IDs: Query GET /products
   - UUIDs: Generate via k6 utility libraries

2. **Dynamic Extraction**:
   - Login response: Extract token for subsequent /validate calls
   - Product IDs: Extract from list_products response
   - Order IDs: Extract from create_order response for get_order calls

3. **Correlation**:
   - User ID + token from login → use in orders
   - Order ID from create → use in get order, payment status

### Service Chain Testing

1. **Happy Path**:
   - GET /products
   - POST /login → extract token
   - POST /validate with token
   - POST /orders with product_ids → observe payment service interaction

2. **Error Paths**:
   - GET /products/{invalid_id} → 400
   - POST /orders with non-existent user → 400
   - POST /login with invalid credentials → 401

3. **Incident Simulation** (covered in INCIDENT_PLAYBOOK.md):
   - Payment timeout
   - Payment error
   - Retry storm
   - etc.

---

## Summary Statistics

| Item | Count | Notes |
|------|-------|-------|
| Gateway Endpoints | 6 | /products (list, get), /auth (login, validate), /orders (create, get) |
| Catalog Service Endpoints | 4 | /products (list, get), /health, /metrics |
| Auth Service Endpoints | 4 | /login, /validate, /health, /metrics |
| Order Service Endpoints | 6 | POST /orders, GET /orders/{id}, /health, /metrics, /retry-config + hidden |
| Payment Service Endpoints | 5 | POST /charge, GET /charge/{id}, /simulate-failure, /health, /metrics |
| Main App Endpoints | 5 | /, /health, /readiness, /liveness, /metrics |
| **Total Endpoints** | **30+** | Across all services |
| **Test Data Requirements** | 2 users, 4 products | Seeded in seed_db.py |
| **Database Tables** | 7 | users, sessions, products, orders, order_items, payments, cache_log |
| **Incident Types** | 7 | Payment timeout, payment error, retry storm, DB failure, Redis failure, service down, DDoS |
| **Observable Metrics** | 12+ | HTTP, external calls, DB, cache, auth, payment |

---

**Next**: Create FLOW_MAPPING.md with end-to-end user journeys and k6 test scenarios.
