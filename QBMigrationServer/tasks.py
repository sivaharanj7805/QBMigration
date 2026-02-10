"""
Celery Background Tasks for ForensicBridge
==========================================

Handles async migration processing using Celery + Redis.

Usage:
1. Start Redis: redis-server
2. Start Celery: celery -A tasks worker --loglevel=info
3. Trigger migrations via API: POST /api/migrations/<id>/execute

PRODUCTION NOTES:
- Uses Redis as message broker (configure CELERY_BROKER_URL)
- Integrates QBMigrationService for actual QBO push
- Updates migration status in real-time via webhooks
"""

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional

from celery.signals import task_failure, task_postrun, task_prerun

# Add QBMigrationService to path
SERVICE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "QBMigrationService"
)
if SERVICE_PATH not in sys.path:
    sys.path.append(SERVICE_PATH)

logger = logging.getLogger(__name__)

# PRODUCTION FIX: Import shared Celery instance from celery_worker.py
# This ensures all tasks use the same, correctly configured Celery application
# with consistent settings for serialization, timeouts, retry behavior, etc.
# Previously, this file created a duplicate Celery instance with different
# name ('forensicbridge_tasks' vs 'qbmigration') and minimal configuration.
from QBMigrationServer.celery_worker import celery  # noqa: E402


def update_migration_status(
    migration_id: str,
    status: str,
    progress: Optional[int] = None,
    message: Optional[str] = None,
    error: Optional[str] = None,
):
    """
    Update migration status in database and notify via webhook.

    CRITICAL FIX: Use correct field names from Migration model:
    - progress_percent (not progress)
    - current_step (not status_message)
    - Use set_error_message() for encrypted error storage
    - Migration model has no updated_at - use db timestamp

    Args:
        migration_id: UUID of migration (string, not int primary key)
        status: New status value
        progress: Progress percentage (0-100)
        message: Current step/status message
        error: Error message (will be encrypted)
    """
    from app import create_app
    from models.database import db
    from models.migration import Migration

    app = create_app()
    with app.app_context():
        # FIX: Use filter_by with migration_id (UUID string), not query.get (primary key)
        migration = Migration.query.filter_by(migration_id=migration_id).first()

        if migration:
            migration.status = status

            # FIX: Use correct field name progress_percent
            if progress is not None:
                migration.progress_percent = progress

            # FIX: Use correct field name current_step
            if message:
                migration.current_step = message

            # FIX: Use set_error_message() for encrypted storage
            if error:
                try:
                    migration.set_error_message(error)
                except Exception as e:
                    logger.warning(f"Could not encrypt error message: {e}")
                    # Fallback: set error_code at minimum
                    migration.error_code = "TASK_ERROR"

            # NOTE: Migration model doesn't have updated_at - removed
            # Timestamps are handled by created_at, started_at, completed_at

            db.session.commit()
            logger.info(f"Migration {migration_id} status updated to {status}")

            # Trigger webhook if configured
            try:
                from api.webhooks import trigger_webhook

                trigger_webhook(migration, status)
            except Exception as e:
                logger.warning(f"Failed to trigger webhook: {e}")
        else:
            logger.error(f"Migration {migration_id} not found for status update")


@celery.task(bind=True, name="tasks.run_migration")
def run_migration_task(
    self,
    migration_id: str,
    encrypted_file_path: str,
    user_id: Optional[int] = None,
    oauth_tokens: Optional[dict] = None,
):
    """
    Execute QBO migration as background task.

    Args:
        migration_id: UUID of migration record
        encrypted_file_path: Path to encrypted QB data file on S3 or local
        user_id: Optional user ID for OAuth tokens
        oauth_tokens: Optional OAuth tokens for QBO connection

    Returns:
        dict with migration results
    """
    logger.info(f"Starting migration task: {migration_id}")

    # Update status to processing
    update_migration_status(
        migration_id, "processing", progress=0, message="Starting migration..."
    )

    try:
        # Import QBMigrationService components
        from config import initialize_directories
        from main import MigrationOrchestrator

        # SECURITY NOTE: OAuth tokens are temporarily stored in env vars because
        # MigrationOrchestrator reads them from os.environ. This is a security
        # risk as env vars are visible in /proc/<pid>/environ on Linux and may
        # leak into child processes, crash dumps, or logging. A future refactor
        # should pass tokens as arguments through the orchestrator API instead.
        if oauth_tokens:
            os.environ["QBO_ACCESS_TOKEN"] = oauth_tokens.get("access_token", "")
            os.environ["QBO_REFRESH_TOKEN"] = oauth_tokens.get("refresh_token", "")
            os.environ["QBO_REALM_ID"] = oauth_tokens.get("realm_id", "")

        # Initialize directories
        initialize_directories()

        # Create orchestrator with progress callback
        orchestrator = MigrationOrchestrator()

        # Update progress periodically
        update_migration_status(
            migration_id, "processing", progress=10, message="Decrypting data..."
        )

        # Run the actual migration
        success = orchestrator.run_migration(encrypted_file_path)

        if success:
            update_migration_status(
                migration_id,
                "completed",
                progress=100,
                message="Migration completed successfully!",
            )
            return {
                "success": True,
                "migration_id": migration_id,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            update_migration_status(
                migration_id,
                "failed",
                progress=0,
                error="Migration failed - see logs for details",
            )
            return {
                "success": False,
                "migration_id": migration_id,
                "error": "Migration failed",
            }

    except Exception as e:
        logger.exception(f"Migration {migration_id} failed with error: {e}")
        update_migration_status(migration_id, "failed", progress=0, error=str(e))
        raise

    finally:
        # FIX HIGH: Always clean up OAuth tokens from environment variables
        # to minimize the window of exposure for sensitive credentials.
        for env_key in ("QBO_ACCESS_TOKEN", "QBO_REFRESH_TOKEN", "QBO_REALM_ID"):
            os.environ.pop(env_key, None)


@celery.task(bind=True, name="tasks.generate_caseware_export")
def generate_caseware_export_task(
    self, migration_id: str, output_path: Optional[str] = None
):
    """
    Generate Caseware export bundle as background task.

    Args:
        migration_id: UUID of migration record
        output_path: Optional path for output (defaults to temp)

    Returns:
        dict with export file path
    """
    logger.info(f"Starting Caseware export for migration: {migration_id}")

    try:
        from caseware_exporter import CasewareExporter
        from config import OUTPUT_DIR

        if not output_path:
            output_path = str(OUTPUT_DIR / f"{migration_id}_caseware.zip")

        exporter = CasewareExporter()
        result = exporter.export(migration_id, output_path)

        return {
            "success": True,
            "migration_id": migration_id,
            "export_path": output_path,
            "files_exported": result.get("file_count", 0),
        }

    except Exception as e:
        logger.exception(f"Caseware export failed: {e}")
        return {"success": False, "error": str(e)}


@celery.task(name="tasks.cleanup_expired_files")
def cleanup_expired_files_task():
    """
    Periodic task to clean up expired migration files.

    Schedule this with Celery Beat:
    celery -A tasks beat --loglevel=info
    """
    logger.info("Running expired file cleanup...")

    try:
        from data_retention import DataRetentionManager

        retention = DataRetentionManager()
        deleted = retention.cleanup_expired()

        logger.info(f"Cleaned up {deleted} expired files")
        return {"deleted": deleted}

    except Exception as e:
        logger.exception(f"Cleanup failed: {e}")
        return {"error": str(e)}


@celery.task(
    bind=True,
    name="tasks.cleanup_migration_async",
    max_retries=3,
    default_retry_delay=60,
)
def cleanup_migration_async(self, migration_id: str, instance_id: Optional[str] = None):
    """
    Async cleanup of AWS resources after migration completion.

    PRODUCTION FIX: Moved from synchronous webhook handler to async task.
    This prevents webhook response delays and timeouts.

    Args:
        migration_id: Migration UUID
        instance_id: Optional EC2 instance ID to terminate
    """
    from datetime import datetime, timezone

    from app import create_app
    from models.database import db
    from models.migration import Migration

    logger.info(f"Starting async cleanup for migration {migration_id}")

    app = create_app()
    with app.app_context():
        try:
            from utils.aws_manager import AWSMigrationManager

            aws_manager = AWSMigrationManager()

            # Terminate EC2 instance if provided
            if instance_id:
                try:
                    aws_manager.terminate_instance(instance_id)
                    logger.info(
                        f"Terminated EC2 instance {instance_id} for migration {migration_id}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to terminate instance {instance_id}: {e}")

            # Update migration cleanup status
            migration = Migration.query.filter_by(migration_id=migration_id).first()
            if migration:
                migration.cleanup_completed = True
                migration.cleanup_completed_at = datetime.now(timezone.utc)
                if instance_id:
                    migration.ec2_terminated = True
                    migration.ec2_terminated_at = datetime.now(timezone.utc)
                db.session.commit()

            logger.info(f"Cleanup completed for migration {migration_id}")
            return {"status": "success", "migration_id": migration_id}

        except Exception as e:
            logger.error(f"Cleanup failed for migration {migration_id}: {e}")
            # Retry with exponential backoff
            raise self.retry(exc=e, countdown=60 * (2**self.request.retries))


# NOTE: Celery Beat schedule is defined in celery_worker.py
# Task names registered there use full module path: 'QBMigrationServer.tasks.<task_name>'


@celery.task(name="tasks.cleanup_orphaned_resources")
def cleanup_orphaned_resources():
    """
    Periodic task to clean up orphaned AWS resources.
    Finds completed/failed migrations AND stuck processing migrations
    that weren't properly cleaned up.

    PRODUCTION FIX: Also cleans up migrations stuck in intermediate states
    (e.g., 'processing') for too long, which would otherwise leak EC2 instances.
    """
    from datetime import datetime, timedelta, timezone

    from app import create_app
    from models.database import db
    from models.migration import Migration
    from sqlalchemy import or_

    logger.info("Starting orphaned resource cleanup")

    app = create_app()
    with app.app_context():
        try:
            from utils.aws_manager import AWSMigrationManager

            aws_manager = AWSMigrationManager()

            # Thresholds for different scenarios
            completed_threshold = datetime.now(timezone.utc) - timedelta(
                hours=6
            )  # Completed but not cleaned up
            stuck_threshold = datetime.now(timezone.utc) - timedelta(
                hours=2
            )  # Processing for too long

            # PRODUCTION FIX: Find migrations needing cleanup including stuck ones
            # 1. Completed/failed migrations older than 6 hours that weren't cleaned
            # 2. Processing migrations older than 2 hours (likely stuck/orphaned)
            stale_migrations = (
                Migration.query.filter(
                    Migration.cleanup_completed.is_(False),
                    Migration.aws_instance_id.isnot(None),
                    or_(
                        # Case 1: Completed/failed but not cleaned up
                        db.and_(
                            Migration.status.in_(["completed", "failed"]),
                            Migration.created_at < completed_threshold,
                        ),
                        # Case 2: Stuck in processing state for too long
                        db.and_(
                            Migration.status == "processing",
                            Migration.started_at < stuck_threshold,
                        ),
                    ),
                )
                .limit(10)
                .all()
            )

            cleaned_count = 0
            for migration in stale_migrations:
                try:
                    # PRODUCTION FIX: Mark stuck processing migrations as failed
                    if migration.status == "processing":
                        logger.warning(
                            f"Migration {migration.migration_id} stuck in processing state, marking as failed"
                        )
                        migration.status = "failed"
                        migration.error_code = "STUCK_TIMEOUT"
                        try:
                            migration.set_error_message(
                                "Migration timed out after 2 hours in processing state"
                            )
                        except Exception as e:
                            logger.warning("Error message encryption failed for migration %s: %s", migration.migration_id, e)

                    if migration.aws_instance_id:
                        aws_manager.terminate_instance(migration.aws_instance_id)
                        migration.ec2_terminated = True
                        migration.ec2_terminated_at = datetime.now(timezone.utc)

                    migration.cleanup_completed = True
                    migration.cleanup_completed_at = datetime.now(timezone.utc)
                    db.session.commit()
                    cleaned_count += 1
                    logger.info(
                        f"Cleaned orphaned resources for migration"
                        f" {migration.migration_id}"
                        f" (status: {migration.status})"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to clean migration {migration.migration_id}: {e}"
                    )
                    db.session.rollback()

            logger.info(
                f"Orphaned resource cleanup complete: {cleaned_count} migrations cleaned"
            )
            return {"cleaned": cleaned_count}

        except Exception as e:
            logger.error(f"Orphaned resource cleanup failed: {e}")
            return {"error": str(e)}


# Signal handlers for logging
@task_prerun.connect
def task_prerun_handler(task_id, task, *args, **kwargs):
    logger.info(f"Task {task.name}[{task_id}] starting")


@task_postrun.connect
def task_postrun_handler(task_id, task, retval, state, *args, **kwargs):
    logger.info(f"Task {task.name}[{task_id}] completed with state: {state}")


@task_failure.connect
def task_failure_handler(task_id, exception, traceback, *args, **kwargs):
    logger.error(f"Task {task_id} failed: {exception}")
