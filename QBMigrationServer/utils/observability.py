"""
Observability Module - OpenTelemetry Integration

FIX 100/100: Implements distributed tracing, metrics, and logging correlation
for production observability requirements.

This module initializes:
1. OpenTelemetry tracing with auto-instrumentation
2. Prometheus metrics export
3. Structured logging with trace correlation

Usage:
    from utils.observability import init_observability
    init_observability(app)
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Tracing state
_tracer_provider = None
_meter_provider = None


def init_observability(app) -> bool:
    """
    Initialize OpenTelemetry observability for the Flask application.

    Args:
        app: Flask application instance

    Returns:
        bool: True if initialization succeeded, False otherwise

    Environment Variables:
        OTEL_SERVICE_NAME: Service name for traces (default: forensicbridge-server)
        OTEL_EXPORTER_OTLP_ENDPOINT: OTLP collector endpoint
        OTEL_TRACES_ENABLED: Enable tracing (default: true in production)
        OTEL_METRICS_ENABLED: Enable metrics (default: true)
    """
    global _tracer_provider, _meter_provider

    # Check if observability is enabled
    flask_env = os.getenv('FLASK_ENV', 'development')
    traces_enabled = os.getenv('OTEL_TRACES_ENABLED', 'true' if flask_env == 'production' else 'false').lower() == 'true'
    metrics_enabled = os.getenv('OTEL_METRICS_ENABLED', 'true').lower() == 'true'

    if not traces_enabled and not metrics_enabled:
        logger.info("Observability disabled via environment configuration")
        return False

    try:
        # Import OpenTelemetry components
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        # Import auto-instrumentation
        from opentelemetry.instrumentation.flask import FlaskInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor

        # Service resource
        service_name = os.getenv('OTEL_SERVICE_NAME', 'forensicbridge-server')
        resource = Resource.create({
            SERVICE_NAME: service_name,
            "deployment.environment": flask_env,
            "service.version": app.config.get('VERSION', '1.0.0'),
        })

        if traces_enabled:
            # Initialize tracer provider
            _tracer_provider = TracerProvider(resource=resource)

            # Configure exporter
            otlp_endpoint = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT')
            if otlp_endpoint:
                exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
                _tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
                logger.info(f"OpenTelemetry tracing enabled, exporting to {otlp_endpoint}")
            else:
                logger.info("OpenTelemetry tracing enabled (no exporter configured)")

            trace.set_tracer_provider(_tracer_provider)

            # Auto-instrument Flask
            FlaskInstrumentor().instrument_app(app)

            # Auto-instrument SQLAlchemy (if db is configured)
            if hasattr(app, 'extensions') and 'sqlalchemy' in app.extensions:
                SQLAlchemyInstrumentor().instrument(
                    engine=app.extensions['sqlalchemy'].engine
                )
                logger.info("SQLAlchemy instrumentation enabled")

            # Auto-instrument outgoing HTTP requests
            RequestsInstrumentor().instrument()
            logger.info("Requests instrumentation enabled")

        if metrics_enabled:
            _init_metrics(app, resource)

        logger.info(f"Observability initialized for {service_name}")
        return True

    except ImportError as e:
        logger.warning(f"OpenTelemetry packages not available: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to initialize observability: {e}")
        return False


def _init_metrics(app, resource) -> None:
    """
    Initialize Prometheus metrics.

    Uses prometheus_flask_exporter for automatic Flask metrics.
    """
    global _meter_provider

    try:
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

        # Check for OTLP metrics endpoint
        otlp_endpoint = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT')
        if otlp_endpoint:
            exporter = OTLPMetricExporter(endpoint=otlp_endpoint)
            reader = PeriodicExportingMetricReader(exporter, export_interval_millis=60000)
            _meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
            metrics.set_meter_provider(_meter_provider)
            logger.info("OpenTelemetry metrics enabled")

    except ImportError:
        logger.debug("OpenTelemetry metrics exporter not available")
    except Exception as e:
        logger.warning(f"Failed to initialize OpenTelemetry metrics: {e}")

    # Also initialize prometheus_flask_exporter if available
    try:
        from prometheus_flask_exporter import PrometheusMetrics

        # Initialize with custom settings
        metrics_instance = PrometheusMetrics(
            app,
            path='/metrics',
            group_by='endpoint',
            default_labels={'service': 'forensicbridge-server'}
        )

        # Add custom metrics
        metrics_instance.info('app_info', 'Application info', version=app.config.get('VERSION', '1.0.0'))

        logger.info("Prometheus Flask metrics enabled at /metrics")

    except ImportError:
        logger.debug("prometheus_flask_exporter not available")
    except Exception as e:
        logger.warning(f"Failed to initialize Prometheus metrics: {e}")


def get_tracer(name: str = __name__):
    """
    Get a tracer instance for manual instrumentation.

    Args:
        name: Tracer name (typically __name__)

    Returns:
        Tracer instance or no-op tracer if not initialized
    """
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        # Return a no-op tracer
        class NoOpTracer:
            def start_as_current_span(self, name, **kwargs):
                from contextlib import contextmanager
                @contextmanager
                def no_op_context():
                    yield None
                return no_op_context()
        return NoOpTracer()


def add_span_attributes(attributes: dict) -> None:
    """
    Add attributes to the current span.

    Args:
        attributes: Dictionary of attributes to add
    """
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span:
            for key, value in attributes.items():
                span.set_attribute(key, value)
    except ImportError:
        pass


def record_exception(exception: Exception, attributes: Optional[dict] = None) -> None:
    """
    Record an exception in the current span.

    Args:
        exception: The exception to record
        attributes: Optional additional attributes
    """
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span:
            span.record_exception(exception)
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)
    except ImportError:
        pass


def shutdown_observability() -> None:
    """
    Gracefully shutdown observability providers.

    Call this during application shutdown to flush pending traces/metrics.
    """
    global _tracer_provider, _meter_provider

    if _tracer_provider:
        try:
            _tracer_provider.shutdown()
            logger.info("Tracer provider shut down")
        except Exception as e:
            logger.warning(f"Error shutting down tracer: {e}")

    if _meter_provider:
        try:
            _meter_provider.shutdown()
            logger.info("Meter provider shut down")
        except Exception as e:
            logger.warning(f"Error shutting down meter: {e}")
