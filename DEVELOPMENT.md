"""Development and Deployment Guide"""

# Development Setup

## Prerequisites
- Python 3.10+
- PostgreSQL 13+
- Redis 6+

## Quick Start

1. **Ensure PostgreSQL and Redis are running**:
   ```bash
   # Check PostgreSQL
   pg_isready
   
   # Check Redis
   redis-cli ping
   ```

2. **Install Python dependencies**:
   ```bash
   make install
   ```

3. **Create database**:
   ```bash
   createdb microservices_db
   ```

4. **Configure environment** (optional - defaults work for localhost):
   ```bash
   cp .env.example .env
   ```

5. **Run the application**:
   ```bash
   make dev
   ```

6. **Access API documentation**:
   Open http://localhost:8000/docs in your browser

## Installation

### 1. Clone and Install Dependencies
```bash
git clone <repository>
cd Verbatim
make install
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your settings
export DATABASE_URL="postgresql+asyncpg://user:password@localhost/microservices_db"
export REDIS_URL="redis://localhost:6379/0"
```

### 3. Initialize Database
```bash
# Create PostgreSQL database
createdb microservices_db

# Database tables are created automatically on application startup
```

## Development

### Database Setup

```bash
# Create PostgreSQL database
createdb microservices_db

# Seed with sample data (optional)
python seed_db.py
```

Environment variables are automatically loaded from `.env` file via `python-dotenv`.

### Run in Development Mode
```bash
make dev
```
Then open http://localhost:8000/docs for interactive API docs.

### Run Tests
```bash
# All tests
pytest -v

# Specific test file
pytest tests/test_auth.py -v

# With coverage
pytest --cov=. --cov-report=html -v
```

### Code Quality
```bash
# Lint code
make lint

# Format code
make format

# Clean up
make clean
```

## Deployment

### Production Build
```bash
make run
```

## API Endpoints

### Main Application
- **Root**: http://localhost:8000/
- **Documentation**: http://localhost:8000/docs
- **Health**: http://localhost:8000/health
- **Metrics**: http://localhost:8000/metrics
- **Readiness**: http://localhost:8000/readiness
- **Liveness**: http://localhost:8000/liveness

### Auth Service
- **Login**: POST http://localhost:8000/auth/login
- **Validate**: POST http://localhost:8000/auth/validate

### Catalog Service
- **List Products**: GET http://localhost:8000/products
- **Get Product**: GET http://localhost:8000/products/{id}
- **Cache Status**: GET http://localhost:8000/cache-status/{key}

### Order Service
- **Create Order**: POST http://localhost:8000/orders
- **Get Order**: GET http://localhost:8000/orders/{id}
- **Retry Config**: GET http://localhost:8000/retry-config

### Payment Service
- **Charge**: POST http://localhost:8000/charge
- **Payment Status**: GET http://localhost:8000/charge/{order_id}
- **Simulate Failure**: POST http://localhost:8000/simulate-failure

### API Gateway
- **Gateway Routes**: /api/v1/*

## Troubleshooting

### Database Connection Issues
```bash
# Check PostgreSQL is running
psql -U user -d microservices_db -c "SELECT 1;"

# Verify DATABASE_URL in .env
echo $DATABASE_URL
```

### Redis Connection Issues
```bash
# Check Redis is running
redis-cli ping

# Verify REDIS_URL in .env
echo $REDIS_URL
```

### Test Failures
```bash
# Run with verbose output
pytest -vv

# Run specific test
pytest tests/test_main.py::test_health_endpoint -vv

# Run with traceback
pytest --tb=short

# Run single test file
pytest tests/test_auth.py -v
```

### Common Test Issues

**ModuleNotFoundError for aiosqlite**:
```bash
# Fix: Install missing dependency
pip install aiosqlite==0.19.0
```

**TypeError about duplicate base class (Python 3.11+)**:
- This is fixed by using `redis` instead of deprecated `aioredis`
- Ensure requirements.txt has `redis==5.0.1` and NOT `aioredis`

**Tests using real database instead of in-memory SQLite**:
- Check conftest.py has proper dependency overrides
- Ensure `setup_test_dependencies` fixture is running (marked with `autouse=True`)

## Project Structure
```
.
├── main.py                      # Entry point
├── models.py                    # SQLAlchemy models
├── conftest.py                  # Pytest configuration
├── Makefile                     # Development commands
├── requirements.txt             # Dependencies
├── shared/                      # Shared utilities
│   ├── config.py
│   ├── db.py
│   ├── redis_client.py
│   ├── metrics.py
│   └── health.py
├── auth/                        # Auth service
│   ├── app.py
│   └── main.py
├── catalog/                     # Catalog service
│   ├── app.py
│   └── main.py
├── order/                       # Order service
│   ├── app.py
│   └── main.py
├── payment/                     # Payment service
│   ├── app.py
│   └── main.py
├── gateway/                     # API Gateway
│   ├── app.py
│   └── main.py
└── tests/                       # Test suite
    ├── test_main.py
    ├── test_auth.py
    ├── test_catalog.py
    ├── test_order.py
    └── test_payment.py
```
