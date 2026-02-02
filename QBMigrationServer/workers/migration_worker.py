from celery import Celery
from models.database import db
from models.migration import Migration
from datetime import datetime, timedelta
import os
import sys
import json
import logging

# SECURITY FIX: Initialize logger to prevent NameError
logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'QBMigrationService'))

from encryption import EncryptionManager
from data_retention import DataRetentionManager
from audit_logger import AuditLogger

# Initialize Celery
celery = Celery('migration_worker')

def init_celery(app):
    """Initialize Celery with Flask app"""
    celery.conf.update(app.config)
    
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
    return celery


@celery.task(bind=True, max_retries=3)
def process_migration(self, db_id):
    """
    Background task to process migration.
    
    Args:
        db_id: Database primary key of migration record
    """
    from app import app
    from orchestrator import MigrationOrchestrator
    
    with app.app_context():
        migration = Migration.query.get(db_id)
        if not migration:
            logger.error(f"Migration record {db_id} not found")
            return
            
        try:
            # Mark as processing
            migration.status = 'processing'
            migration.started_at = datetime.utcnow()
            db.session.commit()
            
            # Progress callback for orchestrator
            def update_progress(percent, message):
                migration.progress_percent = percent
                migration.current_step = message
                db.session.commit()
            
            # Initialize Orchestrator
            # Using env vars as fallback if not provided in migration record
            orchestrator = MigrationOrchestrator(
                qbo_client_id=app.config.get('QBO_CLIENT_ID'),
                qbo_client_secret=app.config.get('QBO_CLIENT_SECRET'),
                qbo_refresh_token=app.config.get('QBO_REFRESH_TOKEN'),
                realm_id=app.config.get('QBO_REALM_ID'),
                qbo_environment=app.config.get('QBO_ENVIRONMENT', 'sandbox'),
                progress_callback=update_progress
            )
            
            # Run migration from S3
            result = orchestrator.run_migration_from_s3(
                s3_uri=migration.s3_uri,
                aws_region=app.config.get('AWS_REGION', 'us-east-1')
            )
            
            if result['success']:
                migration.status = 'completed'
                migration.completed_at = datetime.utcnow()
                migration.progress_percent = 100
            else:
                migration.status = 'failed'
                # CRITICAL FIX: Use set_error_message() to encrypt error data
                # Direct assignment bypasses encryption and could leak sensitive QB data
                migration.set_error_message(result.get('error', 'Unknown error'))

            db.session.commit()
            return result

        except Exception as e:
            logger.exception(f"Fatal error in worker for migration {db_id}: {str(e)}")
            migration.status = 'failed'
            # CRITICAL FIX: Use set_error_message() to encrypt error data
            # Direct assignment bypasses encryption and could leak sensitive QB data
            migration.set_error_message(str(e))
            db.session.commit()
            
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e, countdown=60)
            raise
