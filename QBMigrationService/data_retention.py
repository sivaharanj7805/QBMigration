import os
import time
import threading
from datetime import datetime, timedelta
from encryption import EncryptionManager
from audit_logger import AuditLogger

class DataRetentionManager:
    """Manage automatic data deletion"""
    
    def __init__(self, retention_hours=1):
        self.retention_hours = retention_hours
        self.logger = AuditLogger()
        self.deletion_jobs = []
    
    def schedule_deletion(self, migration_id, file_paths, delay_hours=None):
        """Schedule files for deletion after delay"""
        if delay_hours is None:
            delay_hours = self.retention_hours
        
        deletion_time = datetime.now() + timedelta(hours=delay_hours)
        
        job = {
            'migration_id': migration_id,
            'file_paths': file_paths if isinstance(file_paths, list) else [file_paths],
            'deletion_time': deletion_time,
            'status': 'scheduled'
        }
        
        self.deletion_jobs.append(job)
        
        # Start background thread to delete
        thread = threading.Thread(
            target=self._delete_after_delay,
            args=(job, delay_hours * 3600)
        )
        thread.daemon = True
        thread.start()
        
        print(f"✓ Scheduled deletion in {delay_hours} hour(s) for {len(job['file_paths'])} file(s)")
        
        self.logger.log_security_event("DELETION_SCHEDULED", {
            "migration_id": migration_id,
            "file_count": len(job['file_paths']),
            "deletion_time": deletion_time.isoformat(),
            "message": f"Files scheduled for deletion in {delay_hours} hour(s)"
        })
    
    def _delete_after_delay(self, job, delay_seconds):
        """Background thread to delete files after delay"""
        # Wait for the delay
        time.sleep(delay_seconds)
        
        # Delete files
        for file_path in job['file_paths']:
            if os.path.exists(file_path):
                try:
                    EncryptionManager.secure_delete(file_path)
                    
                    self.logger.log_deletion(
                        job['migration_id'],
                        file_path,
                        method="secure_7pass"
                    )
                    
                except Exception as e:
                    print(f"❌ Failed to delete {file_path}: {e}")
                    self.logger.log_security_event("DELETION_FAILED", {
                        "migration_id": job['migration_id'],
                        "file_path": file_path,
                        "error": str(e)
                    })
        
        job['status'] = 'completed'
        
        print(f"\n✓ Auto-deletion completed for migration {job['migration_id']}")
    
    def delete_immediately(self, migration_id, file_paths):
        """Delete files immediately (no delay)"""
        if not isinstance(file_paths, list):
            file_paths = [file_paths]
        
        for file_path in file_paths:
            if os.path.exists(file_path):
                try:
                    EncryptionManager.secure_delete(file_path)
                    self.logger.log_deletion(migration_id, file_path)
                    print(f"✓ Deleted: {file_path}")
                except Exception as e:
                    print(f"❌ Failed to delete {file_path}: {e}")
    
    def get_scheduled_deletions(self):
        """Get list of scheduled deletion jobs"""
        return [
            {
                'migration_id': job['migration_id'],
                'file_count': len(job['file_paths']),
                'deletion_time': job['deletion_time'].isoformat(),
                'status': job['status']
            }
            for job in self.deletion_jobs
        ]