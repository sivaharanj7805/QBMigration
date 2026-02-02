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

import os
import sys
import json
import logging
from datetime import datetime
from celery import Celery
from celery.signals import task_prerun, task_postrun, task_failure

# Add QBMigrationService to path
SERVICE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'QBMigrationService')
if SERVICE_PATH not in sys.path:
    sys.path.insert(0, SERVICE_PATH)

logger = logging.getLogger(__name__)

# Celery configuration
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

celery = Celery(
    'forensicbridge_tasks',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per migration
    task_soft_time_limit=3300,  # Warn at 55 minutes
    worker_prefetch_multiplier=1,  # One task at a time (migrations are heavy)
    task_acks_late=True,  # Acknowledge after completion
)


def update_migration_status(migration_id: str, status: str, progress: int = None,
                           message: str = None, error: str = None):
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
                    migration.error_code = 'TASK_ERROR'

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


@celery.task(bind=True, name='tasks.run_migration')
def run_migration_task(self, migration_id: str, encrypted_file_path: str, 
                       user_id: int = None, oauth_tokens: dict = None):
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
    update_migration_status(migration_id, 'processing', progress=0, 
                           message='Starting migration...')
    
    try:
        # Import QBMigrationService components
        from main import MigrationOrchestrator
        from config import initialize_directories
        
        # Setup environment for OAuth if provided
        if oauth_tokens:
            os.environ['QBO_ACCESS_TOKEN'] = oauth_tokens.get('access_token', '')
            os.environ['QBO_REFRESH_TOKEN'] = oauth_tokens.get('refresh_token', '')
            os.environ['QBO_REALM_ID'] = oauth_tokens.get('realm_id', '')
        
        # Initialize directories
        initialize_directories()
        
        # Create orchestrator with progress callback
        orchestrator = MigrationOrchestrator()
        
        # Update progress periodically
        update_migration_status(migration_id, 'processing', progress=10,
                               message='Decrypting data...')
        
        # Run the actual migration
        success = orchestrator.run_migration(encrypted_file_path)
        
        if success:
            update_migration_status(migration_id, 'completed', progress=100,
                                   message='Migration completed successfully!')
            return {
                'success': True,
                'migration_id': migration_id,
                'completed_at': datetime.now(timezone.utc).isoformat()
            }
        else:
            update_migration_status(migration_id, 'failed', progress=0,
                                   error='Migration failed - see logs for details')
            return {
                'success': False,
                'migration_id': migration_id,
                'error': 'Migration failed'
            }
            
    except Exception as e:
        logger.exception(f"Migration {migration_id} failed with error: {e}")
        update_migration_status(migration_id, 'failed', progress=0,
                               error=str(e))
        raise


@celery.task(bind=True, name='tasks.generate_caseware_export')
def generate_caseware_export_task(self, migration_id: str, output_path: str = None):
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
            'success': True,
            'migration_id': migration_id,
            'export_path': output_path,
            'files_exported': result.get('file_count', 0)
        }
        
    except Exception as e:
        logger.exception(f"Caseware export failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@celery.task(name='tasks.cleanup_expired_files')
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
        return {'deleted': deleted}
        
    except Exception as e:
        logger.exception(f"Cleanup failed: {e}")
        return {'error': str(e)}


# Celery Beat schedule (for periodic tasks)
celery.conf.beat_schedule = {
    'cleanup-expired-files': {
        'task': 'tasks.cleanup_expired_files',
        'schedule': 3600.0,  # Every hour
    },
}


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
