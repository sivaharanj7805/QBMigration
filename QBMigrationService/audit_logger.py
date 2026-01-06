import json
import os
import re
from datetime import datetime
from pathlib import Path
from cryptography.fernet import Fernet

class AuditLogger:
    """
    Enhanced audit logger with:
    - SSN sanitization (never log SSNs)
    - Encrypted log storage
    - Structured log formats
    - Log rotation
    """
    
    def __init__(self, log_dir=None, encrypt_logs=True):
        if log_dir is None:
            log_dir = os.path.join(os.path.dirname(__file__), "..", "data", "logs")
        
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Separate log files
        self.security_log = os.path.join(log_dir, "security.log")
        self.access_log = os.path.join(log_dir, "access.log")
        self.data_log = os.path.join(log_dir, "data_operations.log")
        
        # Encryption for sensitive logs
        self.encrypt_logs = encrypt_logs
        if encrypt_logs:
            self.encryption_key = self._get_or_create_encryption_key()
            self.cipher = Fernet(self.encryption_key)
    
    def _get_or_create_encryption_key(self):
        """Get or create encryption key for log files"""
        key_file = os.path.join(self.log_dir, ".log_encryption_key")
        
        if os.path.exists(key_file):
            with open(key_file, 'rb') as f:
                return f.read()
        else:
            # Generate new key
            key = Fernet.generate_key()
            with open(key_file, 'wb') as f:
                f.write(key)
            # Make it read-only
            os.chmod(key_file, 0o400)
            return key
    
    def _sanitize_data(self, data):
        """
        CRITICAL: Sanitize data to remove SSNs and other sensitive info
        
        Patterns removed:
        - SSN: XXX-XX-XXXX
        - TIN/EIN: XX-XXXXXXX
        - Credit card numbers
        """
        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                # Never log SSN fields
                if key.lower() in ['ssn', 'socialsecuritynumber', 'taxid', 'tin', 'ein']:
                    sanitized[key] = "[REDACTED]"
                elif isinstance(value, str):
                    sanitized[key] = self._sanitize_string(value)
                elif isinstance(value, dict):
                    sanitized[key] = self._sanitize_data(value)
                elif isinstance(value, list):
                    sanitized[key] = [self._sanitize_data(item) for item in value]
                else:
                    sanitized[key] = value
            return sanitized
        elif isinstance(data, str):
            return self._sanitize_string(data)
        else:
            return data
    
    def _sanitize_string(self, text):
        """Remove SSNs and sensitive patterns from strings"""
        # SSN pattern: XXX-XX-XXXX
        text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN-REDACTED]', text)
        
        # EIN pattern: XX-XXXXXXX
        text = re.sub(r'\b\d{2}-\d{7}\b', '[EIN-REDACTED]', text)
        
        # Credit card pattern (simple)
        text = re.sub(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', '[CC-REDACTED]', text)
        
        return text
    
    def _write_log(self, log_file, event_type, details):
        """Write log entry with optional encryption"""
        # Sanitize all data before logging
        sanitized_details = self._sanitize_data(details)
        
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": event_type,
            "details": sanitized_details
        }
        
        log_line = json.dumps(entry) + "\n"
        
        # Encrypt security logs
        if self.encrypt_logs and log_file == self.security_log:
            log_line = self.cipher.encrypt(log_line.encode()).decode() + "\n"
        
        with open(log_file, 'a') as f:
            f.write(log_line)
    
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
        # Don't log full file paths in production
        file_name = os.path.basename(file_path)
        
        details = {
            "migration_id": migration_id,
            "file_name": file_name,
            "method": method,
            "message": "File securely deleted"
        }
        self.log_security_event("DATA_DELETION", details)
    
    def log_oauth_refresh(self, success, error=None):
        """Log OAuth token refresh"""
        details = {
            "success": success,
            "error": str(error) if error else None
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
    
    def read_security_log(self, decrypt=True):
        """Read security log (decrypt if needed)"""
        if not os.path.exists(self.security_log):
            return []
        
        entries = []
        with open(self.security_log, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    if self.encrypt_logs and decrypt:
                        decrypted = self.cipher.decrypt(line.encode()).decode()
                        entries.append(json.loads(decrypted))
                    else:
                        entries.append(json.loads(line))
                except Exception as e:
                    print(f"Warning: Could not parse log entry: {e}")
        
        return entries