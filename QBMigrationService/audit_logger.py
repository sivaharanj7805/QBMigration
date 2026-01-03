import json
import os
from datetime import datetime
from pathlib import Path

class AuditLogger:
    """Log all security-relevant events"""
    
    def __init__(self, log_dir=None):
        if log_dir is None:
            log_dir = os.path.join(os.path.dirname(__file__), "..", "data", "logs")
        
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Separate log files
        self.security_log = os.path.join(log_dir, "security.log")
        self.access_log = os.path.join(log_dir, "access.log")
        self.data_log = os.path.join(log_dir, "data_operations.log")
    
    def _write_log(self, log_file, event_type, details):
        """Write log entry"""
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": event_type,
            "details": details
        }
        
        with open(log_file, 'a') as f:
            f.write(json.dumps(entry) + "\n")
    
    def log_security_event(self, event_type, details):
        """Log security event"""
        self._write_log(self.security_log, event_type, details)
        print(f"[SECURITY] {event_type}: {details.get('message', '')}")
    
    def log_access(self, user_id, action, resource, ip_address=None):
        """Log access event"""
        details = {
            "user_id": user_id,
            "action": action,
            "resource": resource,
            "ip_address": ip_address,
            "success": True
        }
        self._write_log(self.access_log, "ACCESS", details)
    
    def log_data_operation(self, operation, entity_type, entity_count, migration_id):
        """Log data operation"""
        details = {
            "operation": operation,
            "entity_type": entity_type,
            "entity_count": entity_count,
            "migration_id": migration_id
        }
        self._write_log(self.data_log, "DATA_OPERATION", details)
    
    def log_encryption(self, migration_id, action, file_size=None):
        """Log encryption/decryption"""
        details = {
            "migration_id": migration_id,
            "action": action,
            "file_size": file_size
        }
        self.log_security_event("ENCRYPTION", details)
    
    def log_deletion(self, migration_id, file_path, method="secure_7pass"):
        """Log file deletion"""
        details = {
            "migration_id": migration_id,
            "file_path": file_path,
            "method": method,
            "message": "File securely deleted"
        }
        self.log_security_event("DATA_DELETION", details)
    
    def log_oauth_refresh(self, success, error=None):
        """Log OAuth token refresh"""
        details = {
            "success": success,
            "error": error
        }
        self.log_security_event("OAUTH_REFRESH", details)
    
    def log_migration_start(self, migration_id, company_name, data_counts):
        """Log migration start"""
        details = {
            "migration_id": migration_id,
            "company_name": company_name,
            "data_counts": data_counts,
            "message": "Migration started"
        }
        self.log_security_event("MIGRATION_START", details)
    
    def log_migration_complete(self, migration_id, success, duration_seconds):
        """Log migration completion"""
        details = {
            "migration_id": migration_id,
            "success": success,
            "duration_seconds": duration_seconds,
            "message": "Migration completed"
        }
        self.log_security_event("MIGRATION_COMPLETE", details)