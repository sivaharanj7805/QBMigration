import os
import time
import threading
import json
import logging
from datetime import datetime, timedelta
from encryption import EncryptionManager
from audit_logger import AuditLogger

# Initialize logger at module level
logger = logging.getLogger(__name__)

# $25M FIX: Try to import Celery for production job queue
try:
    from celery import Celery
    
    # Initialize Celery app
    celery_app = Celery(
        'qb_migration',
        broker=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
        backend=os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    )
    
    celery_app.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
    )
    
    CELERY_AVAILABLE = True
    logger.info("✅ Celery available - using production job queue")
    
except ImportError:
    CELERY_AVAILABLE = False
    celery_app = None
    logger.info("⚠️  Celery not available - using fallback threading")


# Celery task for deletion (only defined if Celery available)
if CELERY_AVAILABLE:
    @celery_app.task(name='qb_migration.execute_deletion')
    def celery_execute_deletion(job_data):
        """Celery task for scheduled deletion (survives server restarts)"""
        from encryption import EncryptionManager
        from audit_logger import AuditLogger
        
        logger = AuditLogger()
        deleted_count = 0
        failed_count = 0
        
        for file_path in job_data['file_paths']:
            if os.path.exists(file_path):
                try:
                    EncryptionManager.secure_delete(file_path)
                    logger.log_deletion(
                        job_data['migration_id'],
                        file_path,
                        method="secure_7pass"
                    )
                    deleted_count += 1
                except Exception as e:
                    logger.info(f"❌ Failed to delete {file_path}: {e}")
                    failed_count += 1
        
        return {
            'deleted_count': deleted_count,
            'failed_count': failed_count,
            'migration_id': job_data['migration_id']
        }

class DataRetentionManager:
    """
    Enhanced data retention with:
    - Automatic deletion scheduling
    - Persistent deletion tracking
    - User-triggered immediate deletion
    - Configurable retention periods
    """
    
    def __init__(self, retention_hours=1):
        self.retention_hours = retention_hours
        self.logger = AuditLogger()
        self.deletion_jobs = []
        self.jobs_file = os.path.join(
            os.path.dirname(__file__), "..", "data", "deletion_jobs.json"
        )
        
        # Load existing jobs
        self._load_jobs()
    
    def _load_jobs(self):
        """Load scheduled deletion jobs from disk"""
        if os.path.exists(self.jobs_file):
            try:
                with open(self.jobs_file, 'r') as f:
                    saved_jobs = json.load(f)
                
                # Resume pending jobs
                now = datetime.now()
                for job_data in saved_jobs:
                    if job_data['status'] == 'scheduled':
                        deletion_time = datetime.fromisoformat(job_data['deletion_time'])
                        
                        if deletion_time > now:
                            # Job still pending
                            self.deletion_jobs.append(job_data)
                            
                            # Restart thread
                            delay_seconds = (deletion_time - now).total_seconds()
                            self._start_deletion_thread(job_data, delay_seconds)
                        else:
                            # Job overdue, delete immediately
                            self._execute_deletion(job_data)
                
                logger.info(f"✓ Resumed {len(self.deletion_jobs)} scheduled deletion jobs")
                
            except Exception as e:
                logger.info(f"Warning: Could not load deletion jobs: {e}")
    
    def _save_jobs(self):
        """Save deletion jobs to disk"""
        try:
            os.makedirs(os.path.dirname(self.jobs_file), exist_ok=True)
            
            with open(self.jobs_file, 'w') as f:
                # Convert datetime to ISO format for JSON
                jobs_data = []
                for job in self.deletion_jobs:
                    job_copy = job.copy()
                    if isinstance(job_copy['deletion_time'], datetime):
                        job_copy['deletion_time'] = job_copy['deletion_time'].isoformat()
                    jobs_data.append(job_copy)
                
                json.dump(jobs_data, f, indent=2)
                
        except Exception as e:
            logger.info(f"Warning: Could not save deletion jobs: {e}")
    
    def schedule_deletion(self, migration_id, file_paths, delay_hours=None):
        """
        $25M FIX: Schedule files for deletion using Celery (if available) or threading.
        
        Celery provides:
        - Persistent job queue (survives server restarts)
        - Distributed execution
        - Automatic retry on failure
        """
        if delay_hours is None:
            delay_hours = self.retention_hours
        
        deletion_time = datetime.now() + timedelta(hours=delay_hours)
        
        job = {
            'migration_id': migration_id,
            'file_paths': file_paths if isinstance(file_paths, list) else [file_paths],
            'deletion_time': deletion_time,
            'status': 'scheduled',
            'scheduled_at': datetime.now().isoformat()
        }
        
        self.deletion_jobs.append(job)
        self._save_jobs()
        
        # Use Celery if available (production), otherwise threading (development)
        if CELERY_AVAILABLE:
            delay_seconds = delay_hours * 3600
            
            # Schedule Celery task with ETA
            celery_execute_deletion.apply_async(
                args=[job],
                eta=deletion_time,
                task_id=f"deletion_{migration_id}"
            )
            
            logger.info(f"✓ Scheduled deletion via Celery in {delay_hours} hour(s) for {len(job['file_paths'])} file(s)")
        else:
            # Fallback to threading
            delay_seconds = delay_hours * 3600
            self._start_deletion_thread(job, delay_seconds)
            logger.info(f"✓ Scheduled deletion via threading in {delay_hours} hour(s) for {len(job['file_paths'])} file(s)")
        
        self.logger.log_security_event("DELETION_SCHEDULED", {
            "migration_id": migration_id,
            "file_count": len(job['file_paths']),
            "deletion_time": deletion_time.isoformat(),
            "method": "celery" if CELERY_AVAILABLE else "threading",
            "message": f"Files scheduled for deletion in {delay_hours} hour(s)"
        })
    
    def _start_deletion_thread(self, job, delay_seconds):
        """Start background thread for deletion"""
        thread = threading.Thread(
            target=self._delete_after_delay,
            args=(job, delay_seconds)
        )
        thread.daemon = True
        thread.start()
    
    def _delete_after_delay(self, job, delay_seconds):
        """Background thread to delete files after delay"""
        # Wait for the delay
        time.sleep(delay_seconds)
        
        # Execute deletion
        self._execute_deletion(job)
    
    def _execute_deletion(self, job):
        """Execute file deletion for a job"""
        deleted_count = 0
        failed_count = 0
        
        for file_path in job['file_paths']:
            if os.path.exists(file_path):
                try:
                    EncryptionManager.secure_delete(file_path)
                    
                    self.logger.log_deletion(
                        job['migration_id'],
                        file_path,
                        method="secure_7pass"
                    )
                    
                    deleted_count += 1
                    
                except Exception as e:
                    logger.info(f"❌ Failed to delete {file_path}: {e}")
                    failed_count += 1
                    
                    self.logger.log_security_event("DELETION_FAILED", {
                        "migration_id": job['migration_id'],
                        "file_path": file_path,
                        "error": str(e)
                    })
        
        job['status'] = 'completed'
        job['completed_at'] = datetime.now().isoformat()
        job['deleted_count'] = deleted_count
        job['failed_count'] = failed_count
        
        self._save_jobs()
        
        logger.info(f"\n✓ Auto-deletion completed for migration {job['migration_id']}")
        logger.info(f"  Deleted: {deleted_count} files")
        if failed_count > 0:
            logger.info(f"  Failed: {failed_count} files")
    
    def delete_immediately(self, migration_id, file_paths):
        """Delete files immediately (no delay)"""
        if not isinstance(file_paths, list):
            file_paths = [file_paths]
        
        deleted_count = 0
        
        for file_path in file_paths:
            if os.path.exists(file_path):
                try:
                    EncryptionManager.secure_delete(file_path)
                    self.logger.log_deletion(migration_id, file_path)
                    logger.info(f"✓ Deleted: {os.path.basename(file_path)}")
                    deleted_count += 1
                except Exception as e:
                    logger.info(f"❌ Failed to delete {file_path}: {e}")
        
        return deleted_count
    
    def cancel_deletion(self, migration_id):
        """Cancel scheduled deletion for a migration"""
        cancelled_count = 0
        
        for job in self.deletion_jobs:
            if job['migration_id'] == migration_id and job['status'] == 'scheduled':
                job['status'] = 'cancelled'
                cancelled_count += 1
        
        self._save_jobs()
        
        if cancelled_count > 0:
            logger.info(f"✓ Cancelled {cancelled_count} deletion job(s) for migration {migration_id}")
            
            self.logger.log_security_event("DELETION_CANCELLED", {
                "migration_id": migration_id,
                "job_count": cancelled_count
            })
        
        return cancelled_count
    
    def get_scheduled_deletions(self, migration_id=None):
        """Get list of scheduled deletion jobs"""
        jobs = []
        
        for job in self.deletion_jobs:
            if migration_id is None or job['migration_id'] == migration_id:
                deletion_time = job['deletion_time']
                if isinstance(deletion_time, str):
                    deletion_time = datetime.fromisoformat(deletion_time)
                
                jobs.append({
                    'migration_id': job['migration_id'],
                    'file_count': len(job['file_paths']),
                    'deletion_time': deletion_time.isoformat(),
                    'status': job['status'],
                    'time_remaining_hours': (deletion_time - datetime.now()).total_seconds() / 3600
                })
        
        return jobs
    
    def cleanup_completed_jobs(self, days_old=7):
        """Remove completed job records older than specified days"""
        cutoff = datetime.now() - timedelta(days=days_old)
        
        original_count = len(self.deletion_jobs)
        
        self.deletion_jobs = [
            job for job in self.deletion_jobs
            if job['status'] != 'completed' or 
               datetime.fromisoformat(job.get('completed_at', datetime.now().isoformat())) > cutoff
        ]
        
        removed_count = original_count - len(self.deletion_jobs)
        
        if removed_count > 0:
            self._save_jobs()
            logger.info(f"✓ Cleaned up {removed_count} old deletion records")
        
        return removed_count