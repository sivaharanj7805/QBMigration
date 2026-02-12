# =============================================================================
# QBMigration Dockerfile
# =============================================================================
# Multi-stage build for optimized production image
#
# Build: docker build -t qbmigration .
# Run:   docker run -p 5000:5000 qbmigration
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder
# -----------------------------------------------------------------------------
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    pkg-config \
    libcairo2-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY QBMigrationServer/requirements.txt /tmp/server-requirements.txt
COPY QBMigrationService/requirements.txt /tmp/service-requirements.txt

RUN pip install --no-cache-dir --upgrade pip wheel && \
    pip install --no-cache-dir -r /tmp/server-requirements.txt && \
    pip install --no-cache-dir -r /tmp/service-requirements.txt

# -----------------------------------------------------------------------------
# Stage 2: Production
# -----------------------------------------------------------------------------
FROM python:3.11-slim as production

# Security: Run as non-root user
RUN groupadd -r qbmigration && useradd -r -g qbmigration qbmigration

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    postgresql-client \
    curl \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy application code
COPY QBMigrationServer /app/QBMigrationServer
COPY QBMigrationService /app/QBMigrationService

# Create necessary directories
RUN mkdir -p /app/data /app/logs /app/backups && \
    chown -R qbmigration:qbmigration /app

# Environment variables
# PYTHONPATH must include QBMigrationServer/ so absolute imports
# (from utils..., from config..., from api..., etc.) resolve correctly
# when Gunicorn loads the app as "QBMigrationServer.app:create_app()"
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/QBMigrationServer" \
    FLASK_APP=QBMigrationServer/app.py \
    FLASK_ENV=production \
    FLASK_DEBUG=0 \
    LOG_DIR=/app/logs \
    PORT=5000

# Health check
# L-11 FIX: Use explicit port for reliability (PORT defaults to 5000 above)
# FIX: Increased start-period to 60s — Gunicorn with multiple workers needs
# time to import the app, run DB migrations, and initialize all services.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# Switch to non-root user
USER qbmigration

# Expose port
EXPOSE 5000

# AUDIT FIX P3-06: Configurable Gunicorn workers via environment variables
# HIGH-07 FIX: Worker class configurable via env (default gthread, .env.example recommends gevent)
ENV GUNICORN_WORKERS=4 \
    GUNICORN_THREADS=2 \
    GUNICORN_WORKER_CLASS=gthread

# Run with gunicorn for production
# L-12 FIX: Added --max-requests to recycle workers after 1000 requests,
# preventing memory leaks from accumulating. --max-requests-jitter adds
# randomness to avoid all workers restarting simultaneously.
# FIX: Use module-level "app" variable instead of factory "create_app()" to
# avoid double app creation (module import creates app, then factory creates
# another). Each worker imports the module once, getting one app instance.
CMD gunicorn --bind "0.0.0.0:${PORT}" --workers "${GUNICORN_WORKERS}" --threads "${GUNICORN_THREADS}" \
     --worker-class "${GUNICORN_WORKER_CLASS}" --timeout 120 --keep-alive 5 \
     --max-requests 1000 --max-requests-jitter 100 \
     --access-logfile - --error-logfile - \
     "QBMigrationServer.app:app"

# -----------------------------------------------------------------------------
# Stage 3: Development
# -----------------------------------------------------------------------------
FROM production as development

# FIX: Install dev dependencies as root but switch back to non-root for runtime.
# Previously the dev stage stayed as root which is a security risk if the
# dev image is accidentally deployed to production.
USER root

# Install development dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Install dev Python packages
RUN pip install --no-cache-dir \
    pytest \
    pytest-cov \
    black \
    flake8 \
    mypy

# Set development environment
ENV FLASK_ENV=development \
    FLASK_DEBUG=1

# FIX: Switch back to non-root user for development runtime
USER qbmigration

# FIX: Add guard against accidental production use of dev image
CMD ["sh", "-c", "if [ \"$FLASK_ENV\" = 'production' ]; then echo 'ERROR: Development image used in production! Use production stage instead.' && exit 1; fi && flask run --host=0.0.0.0 --port=5000"]
