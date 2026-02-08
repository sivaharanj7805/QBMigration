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
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_APP=QBMigrationServer/app.py \
    FLASK_ENV=production \
    PORT=5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/health || exit 1

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
CMD gunicorn --bind "0.0.0.0:${PORT}" --workers "${GUNICORN_WORKERS}" --threads "${GUNICORN_THREADS}" \
     --worker-class "${GUNICORN_WORKER_CLASS}" --timeout 120 --keep-alive 5 \
     --access-logfile - --error-logfile - \
     "QBMigrationServer.app:create_app()"

# -----------------------------------------------------------------------------
# Stage 3: Development
# -----------------------------------------------------------------------------
FROM production as development

# Switch back to root for dev setup
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

# Switch back to app user
USER qbmigration

# Run Flask development server
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
