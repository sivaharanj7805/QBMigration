"""
OpenTelemetry Distributed Tracing Integration
==============================================

Provides distributed tracing for debugging and performance analysis.
Supports export to Jaeger, Zipkin, Datadog, New Relic, and OTLP collectors.

Features:
- Automatic Flask request tracing
- Database query tracing
- External HTTP call tracing
- Celery task tracing
- Custom span creation for business logic

Configuration (Environment Variables):
    ENABLE_TRACING=true                    # Enable/disable tracing
    OTEL_SERVICE_NAME=qbmigration          # Service name in traces
    OTEL_EXPORTER_TYPE=otlp                # otlp, jaeger, zipkin, console
    OTEL_EXPORTER_OTLP_ENDPOINT=...        # OTLP collector endpoint
    OTEL_EXPORTER_JAEGER_ENDPOINT=...      # Jaeger endpoint
    OTEL_TRACES_SAMPLER=parentbased_traceidratio
    OTEL_TRACES_SAMPLER_ARG=0.1            # Sample 10% of traces

Usage:
    from utils.tracing import init_tracing, trace_span

    # In app.py
    init_tracing(app)

    # Custom spans
    with trace_span("process_migration") as span:
        span.set_attribute("migration_id", migration_id)
        # ... business logic ...

Author: ForensicBridge Team
Version: 1.0.0
"""

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

from utils.env_helper import get_env

logger = logging.getLogger(__name__)

# Tracing enabled flag
TRACING_ENABLED = os.getenv("ENABLE_TRACING", "true").lower() == "true"

# Try to import OpenTelemetry, gracefully degrade if not available
try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.trace import Status, StatusCode
    from opentelemetry.trace.propagation.tracecontext import (
        TraceContextTextMapPropagator,
    )

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False
    logger.info("opentelemetry not installed - tracing disabled")

# Global tracer instance
_tracer: Optional[Any] = None


def get_tracer():
    """Get the global tracer instance."""
    return _tracer


@contextmanager
def trace_span(
    name: str, attributes: Optional[Dict[str, Any]] = None, kind: Optional[Any] = None
) -> Generator:
    """
    Create a traced span for a block of code.

    Args:
        name: Name of the span
        attributes: Optional attributes to add to the span
        kind: Optional span kind (CLIENT, SERVER, INTERNAL, etc.)

    Yields:
        The span object (or a no-op if tracing is disabled)

    Example:
        with trace_span("database_query", {"table": "migrations"}) as span:
            result = db.execute(query)
            span.set_attribute("row_count", len(result))
    """
    if not OPENTELEMETRY_AVAILABLE or not TRACING_ENABLED or _tracer is None:
        # Return a no-op context manager
        class NoOpSpan:
            def set_attribute(self, key, value):
                pass

            def set_status(self, status):
                pass

            def record_exception(self, exception):
                pass

            def add_event(self, name, attributes=None):
                pass

        yield NoOpSpan()
        return

    span_kind = kind or trace.SpanKind.INTERNAL

    with _tracer.start_as_current_span(name, kind=span_kind) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        try:
            yield span
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise


def trace_function(
    name: Optional[str] = None, attributes: Optional[Dict[str, Any]] = None
):
    """
    Decorator to trace a function.

    Args:
        name: Optional span name (defaults to function name)
        attributes: Optional attributes to add to the span

    Example:
        @trace_function("process_customer")
        def process_customer(customer_id):
            # ... business logic ...
    """

    def decorator(func):
        if not OPENTELEMETRY_AVAILABLE or not TRACING_ENABLED:
            return func

        from functools import wraps

        @wraps(func)
        def wrapper(*args, **kwargs):
            span_name = name or func.__name__
            with trace_span(span_name, attributes) as span:
                span.set_attribute("function.name", func.__name__)
                span.set_attribute("function.module", func.__module__)
                return func(*args, **kwargs)

        return wrapper

    return decorator


def init_tracing(app):  # noqa: C901
    """
    Initialize OpenTelemetry tracing for the Flask application.

    Args:
        app: Flask application instance
    """
    global _tracer

    if not OPENTELEMETRY_AVAILABLE:
        logger.info("OpenTelemetry not available - tracing disabled")
        return

    if not TRACING_ENABLED:
        logger.info("Tracing disabled via ENABLE_TRACING=false")
        return

    try:
        # Service name from environment or config
        service_name = os.getenv("OTEL_SERVICE_NAME", "qbmigration")
        environment = get_env()

        # Create resource with service info
        resource = Resource.create(
            {
                SERVICE_NAME: service_name,
                "service.version": "4.3.0",
                "deployment.environment": environment,
                "service.namespace": "forensicbridge",
            }
        )

        # Create tracer provider
        provider = TracerProvider(resource=resource)

        # Configure exporter based on environment
        exporter_type = os.getenv("OTEL_EXPORTER_TYPE", "otlp").lower()

        if exporter_type == "console":
            # Console exporter for development
            exporter = ConsoleSpanExporter()
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("OpenTelemetry console exporter configured")

        elif exporter_type == "jaeger":
            # Jaeger exporter
            try:
                from opentelemetry.exporter.jaeger.thrift import JaegerExporter

                jaeger_endpoint = os.getenv(
                    "OTEL_EXPORTER_JAEGER_ENDPOINT", "http://localhost:14268/api/traces"
                )
                exporter = JaegerExporter(
                    collector_endpoint=jaeger_endpoint,
                )
                provider.add_span_processor(BatchSpanProcessor(exporter))
                logger.info(
                    f"OpenTelemetry Jaeger exporter configured: {jaeger_endpoint}"
                )
            except ImportError:
                logger.warning("Jaeger exporter not installed, falling back to console")
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        elif exporter_type == "zipkin":
            # Zipkin exporter
            try:
                from opentelemetry.exporter.zipkin.json import ZipkinExporter

                zipkin_endpoint = os.getenv(
                    "OTEL_EXPORTER_ZIPKIN_ENDPOINT",
                    "http://localhost:9411/api/v2/spans",
                )
                exporter = ZipkinExporter(endpoint=zipkin_endpoint)
                provider.add_span_processor(BatchSpanProcessor(exporter))
                logger.info(
                    f"OpenTelemetry Zipkin exporter configured: {zipkin_endpoint}"
                )
            except ImportError:
                logger.warning("Zipkin exporter not installed, falling back to console")
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        else:
            # OTLP exporter (default) - works with Datadog, New Relic, Grafana, etc.
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )

                otlp_endpoint = os.getenv(
                    "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
                )
                exporter = OTLPSpanExporter(
                    endpoint=otlp_endpoint,
                    insecure=os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "false").lower()
                    == "true",
                )
                provider.add_span_processor(BatchSpanProcessor(exporter))
                logger.info(f"OpenTelemetry OTLP exporter configured: {otlp_endpoint}")
            except ImportError:
                logger.warning("OTLP exporter not installed, falling back to console")
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        # Set the global tracer provider
        trace.set_tracer_provider(provider)

        # Get a tracer
        _tracer = trace.get_tracer(__name__, "1.0.0")

        # Instrument Flask
        try:
            from opentelemetry.instrumentation.flask import FlaskInstrumentor

            FlaskInstrumentor().instrument_app(app)
            logger.info("Flask instrumented with OpenTelemetry")
        except ImportError:
            logger.info("Flask instrumentation not available")

        # Instrument SQLAlchemy
        try:
            from models.database import db
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

            SQLAlchemyInstrumentor().instrument(engine=db.engine)
            logger.info("SQLAlchemy instrumented with OpenTelemetry")
        except ImportError:
            logger.debug("SQLAlchemy instrumentation not available")
        except Exception as e:
            logger.debug(f"SQLAlchemy instrumentation failed: {e}")

        # Instrument requests library
        try:
            from opentelemetry.instrumentation.requests import RequestsInstrumentor

            RequestsInstrumentor().instrument()
            logger.info("Requests library instrumented with OpenTelemetry")
        except ImportError:
            logger.debug("Requests instrumentation not available")

        # Instrument Redis
        try:
            from opentelemetry.instrumentation.redis import RedisInstrumentor

            RedisInstrumentor().instrument()
            logger.info("Redis instrumented with OpenTelemetry")
        except ImportError:
            logger.debug("Redis instrumentation not available")

        logger.info(f"OpenTelemetry tracing initialized for service: {service_name}")

    except Exception as e:
        logger.warning(f"Failed to initialize OpenTelemetry: {e}")
        _tracer = None


def setup_celery_tracing():
    """
    Setup OpenTelemetry tracing for Celery tasks.

    Call this after Celery is initialized.
    """
    if not OPENTELEMETRY_AVAILABLE or not TRACING_ENABLED:
        return

    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        CeleryInstrumentor().instrument()
        logger.info("Celery instrumented with OpenTelemetry")
    except ImportError:
        logger.debug("Celery instrumentation not available")
    except Exception as e:
        logger.debug(f"Celery instrumentation failed: {e}")


def get_trace_context() -> Dict[str, str]:
    """
    Get the current trace context for propagation to external services.

    Returns:
        Dictionary with trace context headers
    """
    if not OPENTELEMETRY_AVAILABLE or not TRACING_ENABLED:
        return {}

    carrier: dict[str, str] = {}
    TraceContextTextMapPropagator().inject(carrier)
    return carrier


def inject_trace_context(headers: Dict[str, str]):
    """
    Inject trace context into outgoing request headers.

    Args:
        headers: Dictionary to inject trace context into
    """
    if not OPENTELEMETRY_AVAILABLE or not TRACING_ENABLED:
        return

    TraceContextTextMapPropagator().inject(headers)
