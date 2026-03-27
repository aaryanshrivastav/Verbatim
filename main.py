"""Main application entry point - combines all microservices into one FastAPI app."""

import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# OpenTelemetry imports
from shared.telemetry import setup_opentelemetry, instrument_fastapi_app
from shared.otel_metrics import init_metrics

# Import routers from all services
from auth.app import router as auth_router
from catalog.app import router as catalog_router
from order.app import router as order_router
from payment.app import router as payment_router
from gateway.app import router as gateway_router

# Import shared utilities
from shared.db import engine
from shared.redis_client import init_redis, close_redis
from shared.metrics import MetricsMiddleware, SERVICE_NAME
from shared.health import check_database, check_redis, build_health_response
from shared.config import DATABASE_URL, REDIS_URL
from models import Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup OpenTelemetry
tracer, meter, otel_logger = setup_opentelemetry(
    service_name="microservices-demo",
    otlp_endpoint="http://localhost:4317",
    enable_prometheus_metrics=True,
)
otel_metrics = init_metrics(meter, "microservices-demo")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic for the main application."""
    logger.info("=" * 60)
    logger.info("Starting Microservices Observability Demo")
    logger.info("=" * 60)
    logger.info(f"Database: {DATABASE_URL}")
    logger.info(f"Redis: {REDIS_URL}")
    
    # Initialize database
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✓ Database initialized")
    except Exception as e:
        logger.error(f"✗ Database initialization failed: {e}")

    # Initialize Redis
    try:
        await init_redis()
        logger.info("✓ Redis initialized")
    except Exception as e:
        logger.error(f"✗ Redis initialization failed: {e}")

    logger.info("=" * 60)
    logger.info("Services ready:")
    logger.info("  - Auth Service: http://localhost:8000/auth/docs")
    logger.info("  - Catalog Service: http://localhost:8000/products/docs")
    logger.info("  - Order Service: http://localhost:8000/orders/docs")
    logger.info("  - Payment Service: http://localhost:8000/charge/docs")
    logger.info("  - API Gateway: http://localhost:8000/api/v1/docs")
    logger.info("  - Health: http://localhost:8000/health")
    logger.info("  - Metrics: http://localhost:8000/metrics")
    logger.info("=" * 60)

    yield

    logger.info("Shutting down Microservices Observability Demo")
    await close_redis()
    await engine.dispose()
    logger.info("✓ Cleanup completed")


# Set service name for metrics
import shared.metrics
shared.metrics.SERVICE_NAME = "main"

# Create main FastAPI app
app = FastAPI(
    title="Microservices Observability Demo",
    description="Complete microservices architecture with monitoring and resilience",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Instrument FastAPI with OpenTelemetry
instrument_fastapi_app(app, "microservices-demo")

# Add metrics middleware (must be first)
app.add_middleware(MetricsMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include all service routers
app.include_router(auth_router, tags=["auth"])
app.include_router(catalog_router, tags=["catalog"])
app.include_router(order_router, tags=["orders"])
app.include_router(payment_router, tags=["payment"])
app.include_router(gateway_router, tags=["gateway"])


@app.get("/", tags=["root"])
async def root():
    """Root endpoint with API documentation links."""
    return {
        "service": "Microservices Observability Demo",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi_schema": "/openapi.json",
        "health": "/health",
        "metrics": "/metrics",
        "services": {
            "auth": "/auth/docs",
            "catalog": "/products/docs",
            "orders": "/orders/docs",
            "payment": "/charge/docs",
            "gateway": "/api/v1/docs",
        },
    }


@app.get("/health", tags=["monitoring"])
async def health_check(
    db = None,  # These would normally be injected but for main app we do manual checks
    redis_client = None,
):
    """
    Comprehensive health check for the main application.
    Verifies all critical dependencies.
    """
    from shared.db import AsyncSessionLocal
    from shared.redis_client import get_redis_client

    checks = {}

    # Check database
    try:
        async with AsyncSessionLocal() as session:
            checks["database"] = await check_database(session)
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        checks["database"] = {"status": "down", "service": "database", "error": str(e)}

    # Check Redis
    try:
        redis_client = await get_redis_client()
        checks["redis"] = await check_redis(redis_client)
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        checks["redis"] = {"status": "down", "service": "redis", "error": str(e)}

    is_healthy, response = build_health_response(checks)
    status_code = 200 if is_healthy else 503

    return {"status_code": status_code, **response}


@app.get("/metrics", tags=["monitoring"])
async def metrics():
    """Return Prometheus metrics."""
    from shared.metrics import get_metrics_text
    return get_metrics_text()


@app.get("/readiness", tags=["monitoring"])
async def readiness():
    """Readiness probe for Kubernetes/container orchestration."""
    try:
        from shared.db import AsyncSessionLocal
        from shared.redis_client import get_redis_client
        
        # Quick checks
        async with AsyncSessionLocal() as session:
            await check_database(session)
        
        redis_client = await get_redis_client()
        await check_redis(redis_client)
        
        return {"ready": True}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {"ready": False, "error": str(e)}


@app.get("/liveness", tags=["monitoring"])
async def liveness():
    """Liveness probe for Kubernetes/container orchestration."""
    return {"alive": True}


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting server on 0.0.0.0:8000")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
