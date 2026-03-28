"""Payment service main entry point with OpenTelemetry."""

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
    service_name="payment-service",
    otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
)
otel_metrics = init_metrics(meter, "payment-service")

from payment.app import router as payment_router
from shared.redis_client import init_redis, close_redis
from shared.metrics import MetricsMiddleware
from shared.db import engine
from models import Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("Starting Payment Service")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✓ Database initialized")
    except Exception as e:
        logger.error(f"✗ Database initialization failed: {e}")
    
    await init_redis()
    yield
    logger.info("Shutting down Payment Service")
    await close_redis()


# Set service name for metrics
import shared.metrics
shared.metrics.SERVICE_NAME = "payment"

app = FastAPI(
    title="Payment Service",
    description="Payment processing service with simulated gateway",
    version="1.0.0",
    lifespan=lifespan,
)

# Instrument with OpenTelemetry
instrument_fastapi_app(app, "payment-service")

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
app.include_router(payment_router)

# Health check endpoint
@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "payment-service"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8004)
