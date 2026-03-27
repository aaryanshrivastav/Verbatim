"""OpenTelemetry setup for all microservices."""

import logging
import os
from typing import Optional

import structlog
from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


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


def setup_opentelemetry(
    service_name: str,
    otlp_endpoint: Optional[str] = None,
    enable_prometheus_metrics: bool = True,
) -> tuple:
    """
    Initialize OpenTelemetry for a microservice.
    
    Returns:
        Tuple of (tracer, meter, logger)
    """
    if otlp_endpoint is None:
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    # Create resource with service name
    resource = Resource(attributes={SERVICE_NAME: service_name})

    # Setup Tracer Provider
    trace_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(trace_provider)

    # Setup Meter Provider
    if enable_prometheus_metrics:
        prometheus_reader = PrometheusMetricReader()
        metric_provider = MeterProvider(
            resource=resource,
            metric_readers=[prometheus_reader],
        )
    else:
        otlp_metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint)
        metric_reader = PeriodicExportingMetricReader(otlp_metric_exporter)
        metric_provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader],
        )

    metrics.set_meter_provider(metric_provider)

    # Setup JSON logging
    logger = setup_json_logging()

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
    """
    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(
        app,
        server_request_hook=lambda span, scope: None,
        client_request_hook=lambda span, request: None,
    )

    # Instrument requests library for outbound HTTP calls
    RequestsInstrumentor().instrument()

    # Instrument logging
    LoggingInstrumentor().instrument(set_logging_format=True)
