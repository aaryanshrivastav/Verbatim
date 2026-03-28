"""Catalog service main entry point with OpenTelemetry."""

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
    service_name="catalog-service",
    otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
)
otel_metrics = init_metrics(meter, "catalog-service")

from catalog.app import router as catalog_router
from shared.redis_client import init_redis, close_redis
from shared.metrics import MetricsMiddleware
from shared.db import engine
from models import Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("Starting Catalog Service")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✓ Database initialized")
    except Exception as e:
        logger.error(f"✗ Database initialization failed: {e}")
    
    await init_redis()
    yield
    logger.info("Shutting down Catalog Service")
    await close_redis()


# Set service name for metrics
import shared.metrics
shared.metrics.SERVICE_NAME = "catalog"

app = FastAPI(
    title="Catalog Service",
    description="Product catalog service with caching",
    version="1.0.0",
    lifespan=lifespan,
)

# Instrument with OpenTelemetry
instrument_fastapi_app(app, "catalog-service")

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
app.include_router(catalog_router)

# Health check endpoint
@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "catalog-service"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
