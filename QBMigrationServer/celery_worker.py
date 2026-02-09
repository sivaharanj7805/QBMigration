"""
Celery worker configuration for background tasks.

This module creates and configures the Celery instance for handling
background tasks like AWS resource cleanup, email notifications, etc.

Usage:
    celery -A QBMigrationServer.celery_worker worker --loglevel=info
    celery -A QBMigrationServer.celery_worker beat --loglevel=info
"""

import logging
import os

from celery import Celery
from flask import Flask

logger = logging.getLogger(__name__)


def make_celery(app: Flask = None) -> Celery:
    """
    Create and configure Celery instance.

    Args:
        app: Optional Flask application for context integration

    Returns:
        Configured Celery instance
    """
    # Get broker URL from environment
    broker_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    result_backend = os.getenv("CELERY_RESULT_BACKEND", broker_url)

    celery = Celery(
        "qbmigration",
        broker=broker_url,
        backend=result_backend,
        include=["QBMigrationServer.tasks"],
    )

    # Celery configuration
    celery.conf.update(
        # Serialization
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        # Timezone
        timezone="UTC",
        enable_utc=True,
        # Task settings
        task_track_started=True,
        task_time_limit=3600,  # 1 hour max per task
        task_soft_time_limit=3300,  # Soft limit at 55 minutes
        # Worker settings
        worker_prefetch_multiplier=1,  # Fair task distribution
        task_acks_late=True,  # Acknowledge after completion for reliability
        # Result expiration
        result_expires=86400,  # 24 hours
        # Retry settings
        task_default_retry_delay=60,  # 1 minute
        task_max_retries=3,
        # Beat schedule for periodic tasks
        beat_schedule={
            "cleanup-orphaned-resources": {
                "task": "QBMigrationServer.tasks.cleanup_orphaned_resources",
                "schedule": 900.0,  # Every 15 minutes
            },
            "cleanup-expired-uploads": {
                "task": "QBMigrationServer.tasks.cleanup_expired_upload_sessions",
                "schedule": 3600.0,  # Every hour
            },
        },
    )

    if app:
        # FIX HIGH: Only pass Celery-relevant keys from Flask config.
        # Previously used celery.conf.update(app.config) which dumped the
        # ENTIRE Flask config (including SECRET_KEY, database credentials,
        # API tokens, etc.) into Celery's configuration namespace.
        CELERY_CONFIG_WHITELIST = [
            "CELERY_BROKER_URL",
            "CELERY_RESULT_BACKEND",
            "CELERY_TASK_SERIALIZER",
            "CELERY_ACCEPT_CONTENT",
            "CELERY_RESULT_SERIALIZER",
            "CELERY_TIMEZONE",
            "CELERY_ENABLE_UTC",
            "CELERY_TASK_TRACK_STARTED",
            "CELERY_TASK_TIME_LIMIT",
            "CELERY_TASK_SOFT_TIME_LIMIT",
            "CELERY_WORKER_PREFETCH_MULTIPLIER",
            "CELERY_TASK_ACKS_LATE",
            "CELERY_RESULT_EXPIRES",
            "CELERY_TASK_DEFAULT_RETRY_DELAY",
            "CELERY_TASK_MAX_RETRIES",
        ]
        celery_config = {
            k: v for k, v in app.config.items() if k in CELERY_CONFIG_WHITELIST
        }
        celery.conf.update(celery_config)

        # Create a task base class that runs within Flask app context
        class ContextTask(celery.Task):  # type: ignore[name-defined]
            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)

        celery.Task = ContextTask

    return celery


# Create default celery instance
celery = make_celery()


def init_celery(app: Flask) -> Celery:
    """
    Initialize Celery with Flask application context.

    Call this from your Flask app factory to integrate Celery.

    Args:
        app: Flask application instance

    Returns:
        Configured Celery instance
    """
    global celery
    celery = make_celery(app)
    return celery
