"""
Prometheus Metrics Integration
==============================

Provides application metrics for monitoring and alerting.
Exposes metrics at /metrics endpoint for Prometheus scraping.

Metrics Exported:
- Request latency histogram
- Request counter by endpoint and status
- Active requests gauge
- Database connection pool stats
- Celery task metrics
- Migration metrics (in-progress, completed, failed)
- Error rate counter

Usage:
    from utils.metrics import init_metrics, track_request

    # In app.py
    init_metrics(app)

    # Metrics automatically collected via middleware

Author: ForensicBridge Team
Version: 1.0.0
"""

import logging
import os
import time

logger = logging.getLogger(__name__)

# Metrics collection enabled flag
METRICS_ENABLED = os.getenv("ENABLE_PROMETHEUS_METRICS", "true").lower() == "true"

# Try to import prometheus_client, gracefully degrade if not available
try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        REGISTRY,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        Info,
        generate_latest,
        multiprocess,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client not installed - metrics disabled")


# =============================================================================
# METRIC DEFINITIONS
# =============================================================================

if PROMETHEUS_AVAILABLE and METRICS_ENABLED:
    # Request metrics
    REQUEST_COUNT = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status_code"],
    )

    REQUEST_LATENCY = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "endpoint"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    )

    ACTIVE_REQUESTS = Gauge("http_requests_active", "Number of active HTTP requests")

    # Database metrics
    DB_POOL_SIZE = Gauge("db_connection_pool_size", "Database connection pool size")

    DB_POOL_CHECKED_OUT = Gauge(
        "db_connections_checked_out", "Database connections currently in use"
    )

    DB_POOL_OVERFLOW = Gauge(
        "db_connections_overflow", "Database connections in overflow"
    )

    # Migration metrics
    MIGRATIONS_TOTAL = Counter(
        "migrations_total", "Total migrations by status", ["status"]
    )

    MIGRATIONS_IN_PROGRESS = Gauge(
        "migrations_in_progress", "Number of migrations currently in progress"
    )

    MIGRATION_DURATION = Histogram(
        "migration_duration_seconds",
        "Migration duration in seconds",
        ["destination"],
        buckets=[60, 300, 600, 1800, 3600, 7200, 14400],
    )

    # Celery task metrics
    CELERY_TASKS_TOTAL = Counter(
        "celery_tasks_total",
        "Total Celery tasks by name and status",
        ["task_name", "status"],
    )

    CELERY_TASK_DURATION = Histogram(
        "celery_task_duration_seconds",
        "Celery task duration in seconds",
        ["task_name"],
        buckets=[1, 5, 10, 30, 60, 300, 600, 1800],
    )

    # Error metrics
    ERROR_COUNT = Counter(
        "errors_total", "Total errors by type and endpoint", ["error_type", "endpoint"]
    )

    # Authentication metrics
    AUTH_ATTEMPTS = Counter(
        "auth_attempts_total", "Authentication attempts", ["method", "result"]
    )

    # Rate limiting metrics
    RATE_LIMIT_HITS = Counter(
        "rate_limit_hits_total", "Rate limit hits by endpoint", ["endpoint"]
    )

    # Upload metrics
    UPLOAD_SIZE_BYTES = Histogram(
        "upload_size_bytes",
        "Upload file sizes in bytes",
        buckets=[1024, 10240, 102400, 1048576, 10485760, 104857600, 1073741824],
    )

    UPLOADS_IN_PROGRESS = Gauge(
        "uploads_in_progress", "Number of uploads currently in progress"
    )

    # Application info
    APP_INFO = Info("qbmigration_app", "Application information")


# =============================================================================
# MIDDLEWARE AND DECORATORS
# =============================================================================


def track_request_metrics():
    """
    Flask middleware to track request metrics.

    Returns before_request and after_request handlers.
    """
    if not PROMETHEUS_AVAILABLE or not METRICS_ENABLED:
        return lambda: None, lambda r: r

    def before_request():
        from flask import g

        g.start_time = time.time()
        ACTIVE_REQUESTS.inc()

    def after_request(response):
        from flask import g, request

        # Skip metrics endpoint to avoid recursion
        if request.path == "/metrics":
            return response

        # Calculate latency
        latency = time.time() - getattr(g, "start_time", time.time())

        # Normalize endpoint for cardinality control
        endpoint = _normalize_endpoint(request.path)

        # Record metrics
        REQUEST_COUNT.labels(
            method=request.method, endpoint=endpoint, status_code=response.status_code
        ).inc()

        REQUEST_LATENCY.labels(method=request.method, endpoint=endpoint).observe(
            latency
        )

        ACTIVE_REQUESTS.dec()

        return response

    return before_request, after_request


def _normalize_endpoint(path: str) -> str:
    """
    Normalize endpoint path to reduce cardinality.

    Replaces UUIDs, IDs, and other variable path segments with placeholders.
    """
    import re

    # Replace UUIDs
    path = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "{id}",
        path,
        flags=re.IGNORECASE,
    )

    # Replace numeric IDs
    path = re.sub(r"/\d+(?=/|$)", "/{id}", path)

    # Replace upload IDs (alphanumeric with underscores)
    path = re.sub(r"/upload_[a-zA-Z0-9_]+", "/upload_{id}", path)

    return path


def track_error(error_type: str, endpoint: str = "unknown"):
    """Track an error occurrence."""
    if PROMETHEUS_AVAILABLE and METRICS_ENABLED:
        ERROR_COUNT.labels(error_type=error_type, endpoint=endpoint).inc()


def track_auth_attempt(method: str, success: bool):
    """Track an authentication attempt."""
    if PROMETHEUS_AVAILABLE and METRICS_ENABLED:
        AUTH_ATTEMPTS.labels(
            method=method, result="success" if success else "failure"
        ).inc()


def track_rate_limit_hit(endpoint: str):
    """Track a rate limit hit."""
    if PROMETHEUS_AVAILABLE and METRICS_ENABLED:
        RATE_LIMIT_HITS.labels(endpoint=endpoint).inc()


def track_upload(size_bytes: int):
    """Track an upload."""
    if PROMETHEUS_AVAILABLE and METRICS_ENABLED:
        UPLOAD_SIZE_BYTES.observe(size_bytes)


def track_migration_start():
    """Track a migration start."""
    if PROMETHEUS_AVAILABLE and METRICS_ENABLED:
        MIGRATIONS_IN_PROGRESS.inc()
        MIGRATIONS_TOTAL.labels(status="started").inc()


def track_migration_complete(destination: str, duration_seconds: float, success: bool):
    """Track a migration completion."""
    if PROMETHEUS_AVAILABLE and METRICS_ENABLED:
        MIGRATIONS_IN_PROGRESS.dec()
        status = "completed" if success else "failed"
        MIGRATIONS_TOTAL.labels(status=status).inc()
        MIGRATION_DURATION.labels(destination=destination).observe(duration_seconds)


def track_celery_task(task_name: str, status: str, duration_seconds: float = None):
    """Track a Celery task."""
    if PROMETHEUS_AVAILABLE and METRICS_ENABLED:
        CELERY_TASKS_TOTAL.labels(task_name=task_name, status=status).inc()
        if duration_seconds is not None:
            CELERY_TASK_DURATION.labels(task_name=task_name).observe(duration_seconds)


# =============================================================================
# DATABASE METRICS COLLECTION
# =============================================================================


def collect_db_metrics(app):
    """Collect database connection pool metrics."""
    if not PROMETHEUS_AVAILABLE or not METRICS_ENABLED:
        return

    try:
        from models.database import db

        with app.app_context():
            engine = db.engine
            pool = engine.pool

            DB_POOL_SIZE.set(pool.size())
            DB_POOL_CHECKED_OUT.set(pool.checkedout())
            DB_POOL_OVERFLOW.set(pool.overflow())
    except Exception as e:
        logger.debug(f"Failed to collect DB metrics: {e}")


# =============================================================================
# INITIALIZATION
# =============================================================================


def init_metrics(app):
    """
    Initialize Prometheus metrics for the Flask application.

    Args:
        app: Flask application instance
    """
    if not PROMETHEUS_AVAILABLE:
        logger.warning("Prometheus metrics disabled - prometheus_client not installed")
        return

    if not METRICS_ENABLED:
        logger.info("Prometheus metrics disabled via ENABLE_PROMETHEUS_METRICS=false")
        return

    # Set application info
    APP_INFO.info(
        {
            "version": "4.3.0",
            "environment": os.getenv("FLASK_ENV", "development"),
            "aws_region": os.getenv("AWS_REGION", "ca-central-1"),
        }
    )

    # Register request tracking middleware
    before_request, after_request = track_request_metrics()
    app.before_request(before_request)
    app.after_request(after_request)

    # Add metrics endpoint
    @app.route("/metrics")
    def metrics():
        """Prometheus metrics endpoint."""
        from flask import Response, request

        # FIX HIGH: Authenticate metrics endpoint if METRICS_AUTH_TOKEN is set
        metrics_auth_token = os.getenv("METRICS_AUTH_TOKEN")
        if metrics_auth_token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header != metrics_auth_token:
                return Response("Unauthorized", status=401, mimetype="text/plain")

        # Collect DB metrics before generating output
        collect_db_metrics(app)

        # Check for multiprocess mode (gunicorn with multiple workers)
        prometheus_multiproc_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR")
        if prometheus_multiproc_dir:
            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(registry)
            metrics_output = generate_latest(registry)
        else:
            metrics_output = generate_latest(REGISTRY)

        return Response(metrics_output, mimetype=CONTENT_TYPE_LATEST)

    logger.info("Prometheus metrics initialized at /metrics")


# =============================================================================
# CELERY SIGNAL HANDLERS
# =============================================================================


def setup_celery_metrics():
    """
    Setup Celery task metrics collection via signals.

    Call this after Celery is initialized.
    """
    if not PROMETHEUS_AVAILABLE or not METRICS_ENABLED:
        return

    try:
        from celery.signals import task_failure, task_postrun, task_prerun

        @task_prerun.connect
        def task_prerun_handler(task_id, task, *args, **kwargs):
            """Track task start."""
            task.start_time = time.time()

        @task_postrun.connect
        def task_postrun_handler(task_id, task, retval, state, *args, **kwargs):
            """Track task completion."""
            duration = time.time() - getattr(task, "start_time", time.time())
            track_celery_task(task.name, "success", duration)

        @task_failure.connect
        def task_failure_handler(task_id, exception, traceback, *args, **kwargs):
            """Track task failure."""
            task = kwargs.get("sender")
            if task:
                duration = time.time() - getattr(task, "start_time", time.time())
                track_celery_task(task.name, "failure", duration)

        logger.info("Celery metrics signals registered")

    except ImportError:
        logger.debug("Celery not available - skipping Celery metrics")
