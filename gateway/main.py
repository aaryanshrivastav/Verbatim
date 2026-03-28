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
shared.metrics.SERVICE_NAME = "gateway"

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
    """Health check endpoint."""
    return {"status": "ok", "service": "gateway-service"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
