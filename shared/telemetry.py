"""OpenTelemetry setup for all microservices."""

import logging
import os
from typing import Optional

import structlog
from fastapi import FastAPI
from opentelemetry import _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased, ParentBased

# Note: Instrumentation imports re-enabled with updated packages
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

_OTEL_LOGGING_INSTRUMENTED = False


def setup_json_logging():
    """Setup JSON logging with structlog."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger()


def _configure_otlp_logging(resource: Resource, otlp_endpoint: str) -> None:
    """Attach OTLP log export without duplicating handlers across test runs."""
    global _OTEL_LOGGING_INSTRUMENTED

    current_provider = _logs.get_logger_provider()
    if isinstance(current_provider, LoggerProvider):
        logger_provider = current_provider
    else:
        logger_provider = LoggerProvider(resource=resource)
        _logs.set_logger_provider(logger_provider)

    if not getattr(logger_provider, "_verbatim_otlp_enabled", False):
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(OTLPLogExporter(endpoint=otlp_endpoint))
        )
        logger_provider._verbatim_otlp_enabled = True

    root_logger = logging.getLogger()
    if root_logger.level > logging.INFO:
        root_logger.setLevel(logging.INFO)

    handler_attached = any(
        isinstance(handler, LoggingHandler) and getattr(handler, "_verbatim_otlp_handler", False)
        for handler in root_logger.handlers
    )
    if not handler_attached:
        handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
        handler._verbatim_otlp_handler = True
        root_logger.addHandler(handler)

    if not _OTEL_LOGGING_INSTRUMENTED:
        LoggingInstrumentor().instrument(set_logging_format=False)
        _OTEL_LOGGING_INSTRUMENTED = True


def setup_opentelemetry(
    service_name: str,
    otlp_endpoint: Optional[str] = None,
    enable_prometheus_metrics: bool = False,
    sampling_rate: Optional[float] = None,
) -> tuple:
    """
    Initialize OpenTelemetry for a microservice.
    
    Returns:
        Tuple of (tracer, meter, logger)
    """
    if otlp_endpoint is None:
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    if sampling_rate is None:
        sampling_rate = float(os.getenv("OTEL_SAMPLING_RATE", "1.0"))

    # Create resource with service name
    resource = Resource(attributes={SERVICE_NAME: service_name})

    # Setup Tracer Provider with production-ready sampling
    trace_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    
    # Configure sampling: keep this full-fidelity by default for the demo path,
    # but allow an env override if the team wants to reduce trace volume later.
    sampler = ParentBased(root=TraceIdRatioBased(sampling_rate))
    
    trace_provider = TracerProvider(
        resource=resource,
        sampler=sampler
    )
    trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(trace_provider)

    # Export metrics over OTLP so the collector remains the single scrape target.
    metric_readers = []
    if enable_prometheus_metrics:
        logging.getLogger(__name__).warning(
            "enable_prometheus_metrics=True uses a local Prometheus reader and bypasses the collector-first path"
        )
        metric_readers.append(PrometheusMetricReader())
    else:
        otlp_metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint)
        metric_readers.append(PeriodicExportingMetricReader(otlp_metric_exporter))

    metric_provider = MeterProvider(
        resource=resource,
        metric_readers=metric_readers,
    )

    metrics.set_meter_provider(metric_provider)

    # Setup JSON logging plus OTLP export to the collector/Loki pipeline.
    logger = setup_json_logging()
    _configure_otlp_logging(resource, otlp_endpoint)

    # Get tracer and meter
    tracer = trace.get_tracer(__name__)
    meter = metrics.get_meter(__name__)

    return tracer, meter, logger


def instrument_fastapi_app(
    app: FastAPI,
    service_name: str,
) -> None:
    """
    Instrument a FastAPI application with OpenTelemetry.
    Auto-instrumentation enabled for complete trace coverage.
    """
    # Instrument FastAPI for HTTP spans
    FastAPIInstrumentor.instrument_app(app)
    
    # Instrument database calls
    SQLAlchemyInstrumentor().instrument()
    
    # Instrument HTTP client calls (inter-service communication)
    HTTPXClientInstrumentor().instrument()
    
    # Instrument Redis calls
    RedisInstrumentor().instrument()
