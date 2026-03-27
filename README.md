# FastAPI Microservices Observability Demo

Complete FastAPI microservices architecture with inter-service communication, caching, and payment retry logic.

## Quick Start (Unified Entry Point)

### Using the Main Application (Recommended)

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env

# Create database (tables auto-created on startup)
createdb microservices_db

# Run all services under one app (port 8000)
uvicorn main:app --reload
```

Then open http://localhost:8000/docs for the API documentation.

**Note**: This runs all services under a single FastAPI instance for development. Each service is accessible at `/auth`, `/products`, `/orders`, `/charge`, `/api/v1`, etc.

## Architecture

The application includes 5 microservices integrated into a single FastAPI app:

- **Auth Service**: Token validation and login
- **Catalog Service**: Product catalog with Redis caching
- **Order Service**: Order creation with payment flow and retries
- **Payment Service**: Simulated payment gateway with failures
- **API Gateway**: Central proxy to all services

Each service exposes:
- Health checks (`/health`)
- Prometheus metrics (`/metrics`)
- Service-specific endpoints (e.g., `/auth/login`, `/products`, `/orders`)

## Prerequisites

- Python 3.10+
- PostgreSQL 13+
- Redis 6+

### Tech Stack

- **FastAPI** 0.104.1 - Modern async web framework
- **SQLAlchemy** 2.0.23 - Async ORM with async/await support
- **asyncpg** 0.29.0 - PostgreSQL async driver
- **redis** 5.0.1 - Modern Redis client with async support
- **pytest** 7.4.3 with pytest-asyncio - Async testing framework

### Key Dependencies

- `python-dotenv` - Automatic .env file loading
- `aiosqlite` - Async SQLite for tests (in-memory database isolation)  
- For production: PostgreSQL + Redis are required

### Architecture Notes

- **Cross-database UUID support**: Uses SQLAlchemy 2.0's native `Uuid` type for compatibility with both PostgreSQL and SQLite in tests
- **Redis migration**: Upgraded from `aioredis` (deprecated) to `redis` 5.0.1+ for Python 3.11+ compatibility
- **Mock Redis in tests**: All Redis operations are mocked in-memory for fast test execution

### Setting Up PostgreSQL & Redis Locally

**For macOS (using Homebrew)**:
```bash
brew install postgresql redis
brew services start postgresql
brew services start redis
```

**For Ubuntu/Debian**:
```bash
sudo apt-get install postgresql postgresql-contrib redis-server
sudo systemctl start postgresql
sudo systemctl start redis-server
```

**For Windows**:
- Download PostgreSQL from https://www.postgresql.org/download/windows/ and run the installer
- Download Redis from https://github.com/microsoftarchive/redis/releases (or use WSL2)
- Start PostgreSQL and Redis services

## Installation & Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

### 3. Set Up Database

```bash
# Create PostgreSQL database
createdb microservices_db

# Tables are automatically created on application startup from SQLAlchemy models
```

### 4. Run Unified Application

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Or using make:

```bash
make dev
```

## Testing

The application includes a comprehensive test suite with 20+ tests covering all services.

### Run All Tests
```bash
pytest -v
```

### Run Tests by Module
```bash
# Main application tests (5 tests)
pytest tests/test_main.py -v

# Auth service tests (3 tests)
pytest tests/test_auth.py -v

# Catalog service tests (4 tests)
pytest tests/test_catalog.py -v

# Order service tests (4 tests)
pytest tests/test_order.py -v

# Payment service tests (4 tests)
pytest tests/test_payment.py -v
```

### Test Configuration
- **Test Database**: In-memory SQLite (isolated for each test run)
- **Redis Mock**: All Redis operations mocked for tests
- **Async Support**: Full async/await support via pytest-asyncio

### Generate Coverage Report
```bash
pytest --cov=. --cov-report=html -v
```

**Note**: Tests use:
- `sqlite+aiosqlite:///:memory:` for the test database (isolated, no persistence)
- Mock Redis client (in-memory dictionary)
- Proper dependency injection via FastAPI's `dependency_overrides`

## Alternative: Run Individual Services (Legacy)

If you prefer to run each service separately:

```bash
# Terminal 1: Auth Service
python -m uvicorn auth.main:app --host 0.0.0.0 --port 8001 --reload

# Terminal 2: Catalog Service
python -m uvicorn catalog.main:app --host 0.0.0.0 --port 8002 --reload

# Terminal 3: Order Service
python -m uvicorn order.main:app --host 0.0.0.0 --port 8003 --reload

# Terminal 4: Payment Service
python -m uvicorn payment.main:app --host 0.0.0.0 --port 8004 --reload

# Terminal 5: API Gateway
python -m uvicorn gateway.main:app --host 0.0.0.0 --port 8000 --reload
```

## Access Services

### Unified Application
- **API Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Root**: http://localhost:8000/ (with service links)

### Individual Service Docs
Those services remain accessible at their respective ports if run separately:
- Auth Service: http://localhost:8001/docs
- Catalog Service: http://localhost:8002/docs
- Order Service: http://localhost:8003/docs
- Payment Service: http://localhost:8004/docs
- API Gateway: http://localhost:8000/docs

## Frontend API Routes (via /api/v1 Gateway)

**All frontend requests should use the `/api/v1` gateway prefix:**

### Products (Catalog)
```bash
# List all products
GET /api/v1/products

# Get single product
GET /api/v1/products/{product_id}
```

### Authentication
```bash
# Login
POST /api/v1/auth/login
Headers: Content-Type: application/json
Body: {
  "username": "user",
  "password": "password"
}

# Validate token/credentials
POST /api/v1/auth/validate
Headers: Content-Type: application/json
Body: {
  "token": "token_value"
}
```

### Orders (Cart)
```bash
# Create order (automatically calls payment)
POST /api/v1/orders
Headers: Content-Type: application/json
Body: {
  "user_id": "user_uuid",
  "items": [
    {"product_id": "product_uuid", "quantity": 2}
  ]
}

# Get order status
GET /api/v1/orders/{order_id}
```

### Payment
```bash
# Charge payment (called inside /api/v1/orders, but also available directly)
POST /api/v1/charge
Headers: Content-Type: application/json
Body: {
  "order_id": "order_uuid",
  "amount": 99.99,
  "currency": "USD"
}
```

## Example Frontend Flow

```javascript
// 1. List products
const products = await fetch('http://localhost:8000/api/v1/products').then(r => r.json());

// 2. Validate user
const validation = await fetch('http://localhost:8000/api/v1/auth/validate', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ token: userToken })
}).then(r => r.json());

// 3. Create order (which internally triggers payment)
const order = await fetch('http://localhost:8000/api/v1/orders', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    user_id: userId,
    items: [
      { product_id: productId, quantity: 1 }
    ]
  })
}).then(r => r.json());

// 4. Check order status
const orderStatus = await fetch(`http://localhost:8000/api/v1/orders/${order.id}`).then(r => r.json());
```

## Direct Service Access (Internal Only - Not for Frontend)

These endpoints should **NOT be used by frontends** (they exist for testing/debugging):

# Validate token
curl -X POST http://localhost:8001/auth/validate \
  -H "Content-Type: application/json" \
  -d '{"token": "token_value"}'
```

### Catalog Service

```bash
# List products
curl http://localhost:8002/products

# Get product
curl http://localhost:8002/products/{product_id}
```

### Order Service

```bash
# Create order
curl -X POST http://localhost:8003/orders \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_uuid",
    "items": [
      {"product_id": "product_uuid", "quantity": 2}
    ]
  }'

# Get order
curl http://localhost:8003/orders/{order_id}
```

### Payment Service

```bash
# Charge
curl -X POST http://localhost:8004/charge \
  -H "Content-Type: application/json" \
  -d '{"order_id": "order_uuid", "amount": 99.99, "currency": "USD"}'

# Payment status
curl http://localhost:8004/{order_id}
```

### API Gateway

```bash
# Gateway proxies
curl http://localhost:8000/api/v1/products
curl http://localhost:8000/api/v1/products/{id}
curl http://localhost:8000/api/v1/auth/validate
curl -X POST http://localhost:8000/api/v1/orders ...
```

## Monitoring & Observability

Each service exposes standard monitoring endpoints:

### Health Checks (GET /health)

All services expose a comprehensive health check endpoint that verifies:
- Database connectivity
- Redis connectivity
- (Gateway & Order service) Upstream service availability

```bash
# Check auth service health
curl http://localhost:8001/health

# Check catalog service health
curl http://localhost:8002/health

# Check order service health (also checks payment service)
curl http://localhost:8003/health

# Check payment service health
curl http://localhost:8004/health

# Check gateway health (checks all downstream services)
curl http://localhost:8000/api/v1/health
```

Returns:
```json
{
  "status_code": 200,
  "healthy": true,
  "status": "healthy",
  "checks": {
    "database": {"status": "ok", "service": "database"},
    "redis": {"status": "ok", "service": "redis"}
  }
}
```

### Prometheus Metrics (GET /metrics)

All services expose Prometheus-compatible metrics at `/metrics`:

```bash
# Get metrics from each service
curl http://localhost:8001/metrics
curl http://localhost:8002/metrics
curl http://localhost:8003/metrics
curl http://localhost:8004/metrics
curl http://localhost:8000/api/v1/metrics
```

Metrics tracked:
- `http_requests_total` - Total HTTP requests (labels: service, method, endpoint, status_code)
- `http_request_duration_seconds` - Request duration histogram (labels: service, method, endpoint)

### Demo/Hidden Routes

#### Catalog Service: Cache Status Check

```bash
# Check if a cache key exists and its TTL
curl http://localhost:8002/cache-status/product:12345

# Response:
{
  "key": "product:12345",
  "exists": true,
  "ttl_seconds": 3542
}
```

Useful for demonstrating cache invalidation and inconsistency issues.

#### Order Service: Retry Configuration

```bash
# View current retry configuration
curl http://localhost:8003/retry-config

# Response:
{
  "retry_enabled": true,
  "max_retries": 3,
  "initial_backoff_seconds": 1.0,
  "max_backoff_seconds": 32.0,
  "http_timeout_seconds": 10.0
}
```

#### Payment Service: Simulate Failures

```bash
# Always timeout (504)
curl -X POST http://localhost:8004/simulate-failure \
  -H "Content-Type: application/json" \
  -d '{"always_timeout": true}'

# Always fail (500)
curl -X POST http://localhost:8004/simulate-failure \
  -H "Content-Type: application/json" \
  -d '{"always_fail": true}'

# Return to normal random simulation
curl -X POST http://localhost:8004/simulate-failure \
  -H "Content-Type: application/json" \
  -d '{"normal": true}'

# Response:
{
  "state": {
    "always_timeout": false,
    "always_fail": false,
    "normal": true
  }
}
```

Useful for testing:
- Retry logic with bounded exponential backoff
- Circuit breaker patterns
- Resilience and timeout behavior

## Configuration

### Retry Settings (Order Service)

- `ENABLE_RETRY_STORM`: Enable exponential backoff + jitter for payment failures
- `MAX_RETRIES`: Number of retry attempts (default: 3)
- `INITIAL_BACKOFF_SECONDS`: Starting backoff (default: 1s)
- `MAX_BACKOFF_SECONDS`: Maximum backoff (default: 32s)

### Payment Simulation (Payment Service)

- `PAYMENT_SUCCESS_RATE`: Probability of successful payment (default: 0.8)
- `PAYMENT_TIMEOUT_RATE`: Probability of timeout (default: 0.1)

### Caching

- `REDIS_CACHE_TTL`: Cache TTL in seconds (default: 3600)

## Key Features

✅ **Async/Await**: Full async support with AsyncSession and aioredis
✅ **Dependency Injection**: Database and Redis clients injected via FastAPI dependencies
✅ **Inter-Service Communication**: Service-to-service calls with httpx
✅ **Retry Logic**: Bounded exponential backoff with jitter (toggleable)
✅ **Caching**: Redis cache-aside pattern for products
✅ **Error Handling**: Comprehensive error handling and timeouts
✅ **Payment Simulation**: Realistic failure scenarios (success, timeout, error)
✅ **API Gateway Pattern**: Central proxy with logging
✅ **Prometheus Metrics**: Track HTTP requests and latency per service
✅ **Health Checks**: Comprehensive service health endpoints with dependency checks
✅ **Observability Middleware**: Built-in request tracking and metrics collection
✅ **Demo Routes**: Hidden endpoints for testing failure scenarios and cache status

## Project Structure

```
.
├── models.py                 # SQLAlchemy ORM models
├── requirements.txt          # Python dependencies
├── shared/
│   ├── config.py            # Configuration and env vars
│   ├── db.py                # Database session management
│   ├── redis_client.py      # Redis client wrapper
│   ├── metrics.py           # Prometheus metrics setup
│   └── health.py            # Health check utilities
├── auth/
│   ├── app.py               # Auth router and logic
│   └── main.py              # Auth service entry point
├── catalog/
│   ├── app.py               # Catalog router with caching + cache-status
│   └── main.py              # Catalog service entry point
├── order/
│   ├── app.py               # Order router with payment flow + retry-config
│   └── main.py              # Order service entry point
├── payment/
│   ├── app.py               # Payment router with simulation + simulate-failure
│   └── main.py              # Payment service entry point
└── gateway/
    ├── app.py               # Gateway router for proxying
    └── main.py              # Gateway service entry point
```

## Observability

Each service includes:
- **Health check endpoints** (`/health`) - Verify service and dependency status
- **Prometheus metrics** (`/metrics`) - HTTP request counting and duration histograms
- **Structured logging** - Detailed error and warning logs
- **HTTP timeout handling** - Configurable timeouts for DB, Redis, and upstream calls
- **Error propagation** - Proper HTTP status codes (400, 401, 404, 500, 503, 504)
- **Middleware instrumentation** - Automatic request tracking and latency measurement

## Notes

- Passwords are hashed using SHA-256 (use bcrypt/argon2 in production)
- Session tokens are 32-byte secure random (use JWT in production for stateless auth)
- Payment service simulates external gateway failures for demo/testing
- All timestamps are timezone-aware (TIMESTAMPTZ)
- UUIDs are used as primary keys throughout
- Metrics middleware automatically tracks all endpoints (excluding /metrics itself)

