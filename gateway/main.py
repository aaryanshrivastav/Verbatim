"""API Gateway main entry point with OpenTelemetry."""

import logging
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import os as _os

# Try loading .env.local for local testing, fall back to .env
if _os.path.exists('.env.local'):
    load_dotenv('.env.local')
else:
    load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# OpenTelemetry setup
from shared.telemetry import setup_opentelemetry, instrument_fastapi_app
from shared.otel_metrics import init_metrics

tracer, meter, otel_logger = setup_opentelemetry(
    service_name="gateway-service",
    otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
)
otel_metrics = init_metrics(meter, "gateway-service")

from gateway.app import router as gateway_router
from shared.redis_client import init_redis, close_redis
from shared.metrics import MetricsMiddleware
from shared.health import build_health_response, check_redis, check_upstream_service
from shared.redis_client import get_redis_client
from shared.config import AUTH_SERVICE_URL, CATALOG_SERVICE_URL, ORDER_SERVICE_URL, PAYMENT_SERVICE_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("Starting API Gateway")
    await init_redis()
    yield
    logger.info("Shutting down API Gateway")
    await close_redis()


# Set service name for metrics
import shared.metrics
shared.metrics.SERVICE_NAME = "gateway-service"

app = FastAPI(
    title="API Gateway",
    description="Central gateway for microservices",
    version="1.0.0",
    lifespan=lifespan,
)

# Instrument with OpenTelemetry
instrument_fastapi_app(app, "gateway-service")

# Add metrics middleware
app.add_middleware(MetricsMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(gateway_router)

# Health check endpoint
@app.get("/health")
async def health():
    """Dependency-aware health check for container probes and operators."""
    checks = {}

    try:
        redis_client = await get_redis_client()
        checks["redis"] = await check_redis(redis_client)
    except Exception as exc:
        checks["redis"] = {"status": "down", "service": "redis", "error": str(exc)}

    checks["auth_service"] = await check_upstream_service("auth", AUTH_SERVICE_URL)
    checks["catalog_service"] = await check_upstream_service("catalog", CATALOG_SERVICE_URL)
    checks["order_service"] = await check_upstream_service("order", ORDER_SERVICE_URL)
    checks["payment_service"] = await check_upstream_service("payment", PAYMENT_SERVICE_URL)

    is_healthy, response = build_health_response(checks)
    return JSONResponse(content=response, status_code=200 if is_healthy else 503)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
