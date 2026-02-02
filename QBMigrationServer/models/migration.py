from models.database import db
from datetime import datetime, timedelta
from flask import current_app
import uuid
import json
from cryptography.fernet import Fernet, InvalidToken
import hashlib
import logging

# Configuration constants (CQ-05: Extracted from magic numbers)
MIGRATION_EXPIRY_HOURS = 48
WEBHOOK_ID_LIMIT = 50
STUCK_TIMEOUT_HOURS = 6
BALANCE_TOLERANCE = 0.01

logger = logging.getLogger(__name__)


class Migration(db.Model):
    """Migration model - tracks AWS-based ephemeral migrations with full audit trail"""
    __tablename__ = 'migrations'

    # Indexes for query performance
    __table_args__ = (
        db.Index('idx_migration_user_status', 'user_id', 'status'),
        db.Index('idx_migration_user_created', 'user_id', 'created_at'),
        db.Index('idx_migration_status_created', 'status', 'created_at'),
        # PERFORMANCE FIX: Composite index for filtered pagination query
        # Supports: WHERE user_id = X AND status = Y ORDER BY created_at DESC
        db.Index('idx_migration_user_status_created', 'user_id', 'status', 'created_at'),
        db.Index('idx_migration_cleanup', 'cleanup_completed', 'status'),
        db.Index('idx_migration_file_hash', 'user_id', 'file_hash'),
        # FIX CRIT-01: Index for session_id to support project-migration queries
        db.Index('idx_migration_session_id', 'session_id'),
    )

    # Primary identifiers
    id = db.Column(db.Integer, primary_key=True)
    migration_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    # FIX #48: CASCADE delete migrations when user is deleted (GDPR compliance)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)

    # Project linkage - session_id links to Project.session_id
    # FIX CRIT-01: Added session_id column to link migrations to projects
    # This field is used by api/projects.py and api/file_upload.py to associate migrations with projects
    session_id = db.Column(db.String(50), index=True)  # References Project.session_id (not FK for flexibility)

    # Company info (metadata only)
    company_name = db.Column(db.String(255))
    qb_file_name = db.Column(db.String(255))
    
    # File metadata (NO actual data stored)
    file_hash = db.Column(db.String(64), index=True)  # SHA-256 hash for duplicate detection
    data_size_bytes = db.Column(db.BigInteger)
    
    # AWS Resources
    s3_uri = db.Column(db.String(500))
    s3_bucket = db.Column(db.String(255))
    s3_key = db.Column(db.String(500))
    aws_instance_id = db.Column(db.String(50))
    aws_region = db.Column(db.String(50), default='us-east-1')
    
    # Migration status
    status = db.Column(db.String(50), default='pending', nullable=False, index=True)
    # Status values: pending, uploading, uploaded, provisioning, processing, completed, failed, cleanup, cleaned
    
    # Progress tracking
    progress_percent = db.Column(db.Integer, default=0)
    current_step = db.Column(db.String(255))
    
    # Results (metadata only)
    customers_migrated = db.Column(db.Integer, default=0)
    vendors_migrated = db.Column(db.Integer, default=0)
    invoices_migrated = db.Column(db.Integer, default=0)
    bills_migrated = db.Column(db.Integer, default=0)
    items_migrated = db.Column(db.Integer, default=0)
    total_records_migrated = db.Column(db.Integer, default=0)
    
    # Error handling (ENCRYPTED)
    error_message_encrypted = db.Column(db.Text)
    error_code = db.Column(db.String(50))
    retry_count = db.Column(db.Integer, default=0)
    max_retries = db.Column(db.Integer, default=3)
    
    # Cleanup tracking
    cleanup_completed = db.Column(db.Boolean, default=False)
    cleanup_completed_at = db.Column(db.DateTime)
    s3_file_deleted = db.Column(db.Boolean, default=False)
    s3_file_deleted_at = db.Column(db.DateTime)
    ec2_terminated = db.Column(db.Boolean, default=False)
    ec2_terminated_at = db.Column(db.DateTime)
    
    # MEDIUM FIX: Cost tracking overflow - increased from Numeric(12,6) to Numeric(14,6)
    # Allows up to $99,999,999.999999 - handles enterprise migrations exceeding $1M
    estimated_cost_usd = db.Column(db.Numeric(14, 6))  # Increased from (12, 6) - prevents overflow
    actual_cost_usd = db.Column(db.Numeric(14, 6))     # Increased from (12, 6) - handles large migrations
    cost_breakdown = db.Column(db.Text)  # JSON: {ec2: X, s3: Y, data_transfer: Z}
    
    # Forensic Data (Stored as JSON Text)
    trial_balance_data = db.Column(db.Text) # JSON: Source/Dest balances, variance, hash
    live_status_data = db.Column(db.Text)   # JSON: Detailed phase tracking, logs
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
    
    # Audit trail
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))
    request_id = db.Column(db.String(36))  # For tracing
    
    # QuickBooks Online details
    qbo_company_id = db.Column(db.String(50))
    qbo_company_name = db.Column(db.String(255))
    
    # Destination mode: 'qbo' (QuickBooks Online) or 'caseware' (Caseware Working Papers)
    destination = db.Column(db.String(20), default='qbo', nullable=False)
    
    # Caseware export path (when destination='caseware')
    caseware_bundle_path = db.Column(db.String(500))
    caseware_bundle_ready = db.Column(db.Boolean, default=False)
    
    # Webhook tracking (prevent replay attacks)
    webhook_processed_ids = db.Column(db.Text)  # JSON array of processed webhook IDs
    last_webhook_at = db.Column(db.DateTime)

    # CRITICAL FIX: Add verification_results field for trial balance verification
    # This stores the complete verification data including trial balance, hash verification, etc.
    verification_results = db.Column(db.Text)  # JSON: Full verification results
    
    def __init__(self, **kwargs):
        super(Migration, self).__init__(**kwargs)
        if not self.migration_id:
            self.migration_id = str(uuid.uuid4())
        if not self.expires_at:
            self.expires_at = datetime.utcnow() + timedelta(hours=MIGRATION_EXPIRY_HOURS)
    
    # ============================================================================
    # ERROR MESSAGE ENCRYPTION (prevent leaking QB data in errors)
    # ============================================================================
    
    def set_error_message(self, message):
        """Set encrypted error message - CRITICAL: Fail-closed if encryption unavailable"""
        if not message:
            self.error_message_encrypted = None
            return

        import os
        try:
            key = current_app.config.get('BACKUP_ENCRYPTION_KEY')
            if not key:
                # CRITICAL FIX: Fail-closed instead of storing unencrypted
                # Storing unencrypted error messages could leak sensitive QB data
                is_production = os.getenv('FLASK_ENV', 'development') == 'production'

                if is_production:
                    # In production, raise an exception - encryption is mandatory
                    raise ValueError(
                        "BACKUP_ENCRYPTION_KEY not configured - cannot store error messages securely. "
                        "This is a critical configuration error in production."
                    )
                else:
                    # In development, store a sanitized placeholder, not the actual error
                    current_app.logger.warning(
                        "BACKUP_ENCRYPTION_KEY not configured - storing sanitized error message"
                    )
                    self.error_message_encrypted = "[REDACTED - encryption key not configured]"
                    return

            f = Fernet(key.encode() if isinstance(key, str) else key)
            self.error_message_encrypted = f.encrypt(message.encode()).decode()
        except ValueError:
            # Re-raise configuration errors
            raise
        except Exception as e:
            # CRITICAL FIX: Fail-closed on encryption errors
            current_app.logger.error(f"Failed to encrypt error message: {str(e)}")
            # Do not store unencrypted - store a placeholder instead
            self.error_message_encrypted = "[ENCRYPTION FAILED - message redacted]"
    
    def get_error_message(self):
        """Get decrypted error message"""
        if not self.error_message_encrypted:
            return None
        
        try:
            key = current_app.config.get('BACKUP_ENCRYPTION_KEY')
            if not key:
                return self.error_message_encrypted
            
            f = Fernet(key.encode() if isinstance(key, str) else key)
            return f.decrypt(self.error_message_encrypted.encode()).decode()
        except (InvalidToken, ValueError, TypeError) as e:
            logger.warning(f"Error message decryption failed: {e}")
            return "Error message decryption failed"
    
    # ============================================================================
    # FILE HASH (duplicate detection)
    # ============================================================================
    
    def calculate_file_hash(self, data):
        """Calculate SHA-256 hash of file data"""
        self.file_hash = hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()
    
    @classmethod
    def find_duplicate(cls, user_id, file_hash):
        """Find duplicate upload by hash"""
        return cls.query.filter_by(
            user_id=user_id,
            file_hash=file_hash
        ).filter(
            cls.status.in_(['uploaded', 'processing', 'completed'])
        ).first()
    
    # ============================================================================
    # COST ESTIMATION & TRACKING
    # ============================================================================
    
    def estimate_cost(self):
        """Estimate migration cost based on file size"""
        if not self.data_size_bytes:
            return
        
        # Get cost config
        s3_cost_per_gb = current_app.config.get('S3_COST_PER_GB', 0.023)
        ec2_cost_per_hour = current_app.config.get('EC2_COST_PER_HOUR', 0.0416)
        
        # S3 storage cost (for 24 hours)
        size_gb = self.data_size_bytes / (1024 ** 3)
        s3_cost = size_gb * s3_cost_per_gb * (24 / 30 / 24)  # Cost for 24 hours
        
        # EC2 cost (estimate 5 hours)
        ec2_cost = ec2_cost_per_hour * 5
        
        # Data transfer cost (estimate 2x file size)
        data_transfer_cost = (size_gb * 2) * 0.09
        
        total = s3_cost + ec2_cost + data_transfer_cost
        
        self.estimated_cost_usd = round(total, 4)
        self.cost_breakdown = json.dumps({
            's3_storage': round(s3_cost, 4),
            'ec2_compute': round(ec2_cost, 4),
            'data_transfer': round(data_transfer_cost, 4)
        })
    
    def set_actual_cost(self, cost_dict):
        """
        Set actual cost from AWS Cost Explorer
        
        Args:
            cost_dict: {'ec2': X, 's3': Y, 'data_transfer': Z}
        """
        total = sum(cost_dict.values())
        self.actual_cost_usd = round(total, 4)
        self.cost_breakdown = json.dumps({
            k: round(v, 4) for k, v in cost_dict.items()
        })
    
    # ============================================================================
    # STATUS MANAGEMENT
    # ============================================================================
    
    def mark_as_uploading(self):
        """Mark migration as uploading to S3 (idempotent)"""
        # Only update if current status is pending
        if self.status == 'pending':
            self.status = 'uploading'
            db.session.commit()
            return True
        return False

    def mark_as_uploaded(self, s3_uri, s3_bucket, s3_key):
        """Mark migration as uploaded to S3 (idempotent)"""
        # Only update if current status is uploading or pending
        if self.status in ['pending', 'uploading']:
            self.status = 'uploaded'
            self.s3_uri = s3_uri
            self.s3_bucket = s3_bucket
            self.s3_key = s3_key
            db.session.commit()
            return True
        return False

    def mark_as_provisioning(self):
        """Mark as provisioning EC2 instance (idempotent)"""
        # Only update if currently uploaded
        if self.status == 'uploaded':
            self.status = 'provisioning'
            self.current_step = 'Creating AWS instance'
            db.session.commit()
            return True
        return False

    def mark_as_processing(self, instance_id):
        """Mark as processing on EC2 instance (idempotent)"""
        # Only update if currently provisioning or uploaded
        if self.status in ['provisioning', 'uploaded']:
            self.status = 'processing'
            self.aws_instance_id = instance_id
            self.started_at = datetime.utcnow()
            self.current_step = 'Running migration on AWS'
            db.session.commit()
            return True
        return False

    def mark_as_completed(self, results=None):
        """
        Mark migration as completed (idempotent)
        FORENSIC REQUIREMENT: Enforces $0.00 trial balance variance
        """
        # Only update if currently processing (prevent overwriting completed state)
        if self.status == 'processing':
            # FORENSIC ENFORCEMENT: Check trial balance reconciliation
            if results and 'trial_balance' in results:
                tb = results['trial_balance']
                is_balanced = tb.get('is_balanced', False)
                discrepancy = abs(tb.get('source_total', 0) - tb.get('destination_total', 0))

                # CRITICAL: Enforce $0.00 variance for forensic integrity
                if not is_balanced or discrepancy > BALANCE_TOLERANCE:  # Allow 1 cent rounding tolerance
                    error_msg = (
                        f"Trial balance reconciliation failed. "
                        f"Discrepancy: ${discrepancy:.2f}. "
                        f"Source: ${tb.get('source_total', 0):.2f}, "
                        f"Destination: ${tb.get('destination_total', 0):.2f}. "
                        f"Migration cannot be marked complete without $0.00 variance."
                    )
                    self.status = 'failed'
                    self.set_error_message(error_msg)
                    self.error_code = 'TRIAL_BALANCE_MISMATCH'
                    self.completed_at = datetime.utcnow()

                    # Store verification data even on failure
                    if results:
                        self.verification_results = json.dumps(results)

                    db.session.commit()
                    raise ValueError(error_msg)

            # If no trial balance provided, require it for completion
            elif results and not results.get('skip_trial_balance_check'):
                error_msg = (
                    "Trial balance verification data missing. "
                    "Forensic migration requires trial balance reconciliation. "
                    "Migration cannot be marked complete without verification."
                )
                self.status = 'failed'
                self.set_error_message(error_msg)
                self.error_code = 'TRIAL_BALANCE_MISSING'
                self.completed_at = datetime.utcnow()
                db.session.commit()
                raise ValueError(error_msg)

            # Trial balance verified - proceed with completion
            self.status = 'completed'
            self.completed_at = datetime.utcnow()
            self.progress_percent = 100
            self.current_step = 'Completed - Trial Balance Verified'

            if results:
                self.customers_migrated = results.get('customers', 0)
                self.vendors_migrated = results.get('vendors', 0)
                self.invoices_migrated = results.get('invoices', 0)
                self.bills_migrated = results.get('bills', 0)
                self.items_migrated = results.get('items', 0)
                self.total_records_migrated = results.get('total', 0)

                # Store verification results
                if 'trial_balance' in results or 'verification_data' in results:
                    self.verification_results = json.dumps(results)

            db.session.commit()
            return True
        return False

    def mark_as_failed(self, error_message, error_code=None):
        """Mark migration as failed (idempotent)"""
        # Allow marking as failed from any non-terminal state
        if self.status not in ['completed', 'cleaned']:
            self.status = 'failed'
            self.set_error_message(error_message)
            self.error_code = error_code
            self.completed_at = datetime.utcnow()
            db.session.commit()
            return True
        return False
    
    # ============================================================================
    # RETRY LOGIC
    # ============================================================================
    
    def can_retry(self):
        """Check if migration can be retried"""
        return self.retry_count < self.max_retries
    
    def increment_retry(self):
        """Increment retry counter"""
        self.retry_count += 1
        db.session.commit()
    
    # ============================================================================
    # CLEANUP TRACKING
    # ============================================================================
    
    def mark_cleanup_started(self):
        """Mark cleanup as started"""
        self.status = 'cleanup'
        self.current_step = 'Cleaning up AWS resources'
        db.session.commit()
    
    def mark_s3_deleted(self):
        """Mark S3 file as deleted"""
        self.s3_file_deleted = True
        self.s3_file_deleted_at = datetime.utcnow()
        db.session.commit()
    
    def mark_ec2_terminated(self):
        """Mark EC2 instance as terminated"""
        self.ec2_terminated = True
        self.ec2_terminated_at = datetime.utcnow()
        db.session.commit()
    
    def mark_cleanup_completed(self):
        """Mark cleanup as fully completed"""
        self.status = 'cleaned'
        self.cleanup_completed = True
        self.cleanup_completed_at = datetime.utcnow()
        self.current_step = 'All resources deleted'
        db.session.commit()
    
    # ============================================================================
    # WEBHOOK REPLAY PREVENTION
    # ============================================================================
    
    def is_webhook_processed(self, webhook_id):
        """Check if webhook was already processed"""
        if not self.webhook_processed_ids:
            return False
        
        try:
            processed = json.loads(self.webhook_processed_ids)
            return webhook_id in processed
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to parse webhook_processed_ids: {e}")
            return False
    
    def mark_webhook_processed(self, webhook_id):
        """
        Mark webhook as processed with proper race condition handling.

        CRITICAL FIX: Uses SELECT FOR UPDATE to prevent race conditions where
        two concurrent webhooks could both pass the is_webhook_processed check
        and both get processed.
        """
        from sqlalchemy import text

        try:
            # RACE CONDITION FIX: Use database-level locking
            # This prevents two concurrent requests from both processing the same webhook
            db.session.execute(
                text("SELECT id FROM migrations WHERE id = :id FOR UPDATE NOWAIT"),
                {"id": self.id}
            )
        except Exception as lock_error:
            # Another transaction has the lock - webhook is being processed
            logger.warning(f"Webhook {webhook_id} - migration {self.id} is locked by another transaction: {lock_error}")
            db.session.rollback()
            return False

        try:
            processed = json.loads(self.webhook_processed_ids) if self.webhook_processed_ids else []
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to parse webhook_processed_ids, resetting: {e}")
            processed = []

        # Double-check after acquiring lock (another process may have added it)
        if webhook_id in processed:
            logger.info(f"Webhook {webhook_id} already processed (detected after lock)")
            return False

        processed.append(webhook_id)
        # Keep only last N webhook IDs to prevent unbounded growth
        processed = processed[-WEBHOOK_ID_LIMIT:]
        self.webhook_processed_ids = json.dumps(processed)

        self.last_webhook_at = datetime.utcnow()
        db.session.commit()
        return True
    
    # ============================================================================
    # EXPIRATION & HEALTH CHECKS
    # ============================================================================
    
    def is_expired(self):
        """Check if migration has expired"""
        return datetime.utcnow() > self.expires_at
    
    def is_stuck(self, timeout_hours=STUCK_TIMEOUT_HOURS):
        """Check if migration is stuck (processing too long)"""
        if self.status != 'processing':
            return False
        
        if not self.started_at:
            return False
        
        elapsed = datetime.utcnow() - self.started_at
        return elapsed > timedelta(hours=timeout_hours)
    
    def needs_cleanup(self):
        """Check if migration needs cleanup"""
        if self.cleanup_completed:
            return False
        
        if self.status in ['completed', 'failed']:
            return True
        
        if self.is_expired():
            return True
        
        if self.is_stuck():
            return True
        
        return False
    
    def get_duration_minutes(self):
        """Get migration duration in minutes"""
        if not self.started_at:
            return 0
        
        end_time = self.completed_at or datetime.utcnow()
        delta = end_time - self.started_at
        return int(delta.total_seconds() / 60)
    
    # ============================================================================
    # SERIALIZATION
    # ============================================================================
    
    def to_dict(self, include_sensitive=False):
        """Convert migration to dictionary"""
        data = {
            'migration_id': self.migration_id,
            'status': self.status,
            'progress_percent': self.progress_percent,
            'current_step': self.current_step,
            'company_name': self.company_name,
            'qb_file_name': self.qb_file_name,
            'destination': self.destination,  # 'qbo' or 'caseware'
            'caseware_bundle_ready': self.caseware_bundle_ready if self.destination == 'caseware' else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration_minutes': self.get_duration_minutes(),
            'customers_migrated': self.customers_migrated,
            'vendors_migrated': self.vendors_migrated,
            'invoices_migrated': self.invoices_migrated,
            'total_records_migrated': self.total_records_migrated,
            'estimated_cost_usd': float(self.estimated_cost_usd) if self.estimated_cost_usd else None,
            'actual_cost_usd': float(self.actual_cost_usd) if self.actual_cost_usd else None,
            'error_message': self.get_error_message() if self.status == 'failed' else None,
            'error_code': self.error_code if self.status == 'failed' else None,
            'can_retry': self.can_retry() if self.status == 'failed' else False
        }
        
        if include_sensitive:
            data.update({
                's3_uri': self.s3_uri,
                'aws_instance_id': self.aws_instance_id,
                'aws_region': self.aws_region,
                'cleanup_completed': self.cleanup_completed,
                's3_file_deleted': self.s3_file_deleted,
                'ec2_terminated': self.ec2_terminated,
                'expires_at': self.expires_at.isoformat() if self.expires_at else None,
                'file_hash': self.file_hash,
                'data_size_mb': round(self.data_size_bytes / (1024 ** 2), 2) if self.data_size_bytes else None,
                'retry_count': self.retry_count,
                'ip_address': self.ip_address,
                'request_id': self.request_id
            })
            
            # Parse cost breakdown
            if self.cost_breakdown:
                try:
                    data['cost_breakdown'] = json.loads(self.cost_breakdown)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Failed to parse cost_breakdown: {e}")
            
            # Parse forensic data
            if hasattr(self, 'trial_balance_data') and self.trial_balance_data:
                try:
                    data['trial_balance_data'] = json.loads(self.trial_balance_data)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Failed to parse trial_balance_data: {e}")

            if hasattr(self, 'live_status_data') and self.live_status_data:
                try:
                    data['live_status_data'] = json.loads(self.live_status_data)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Failed to parse live_status_data: {e}")
        
        return data

    def strip_sensitive_data(self):
        """
        FIX #45: Strip sensitive PII/financial data for zero-persistence compliance.
        Keeps only metadata (hashes, counts, status) - removes raw balances, logs, transactions.
        Should be called 24 hours after migration completion.
        """
        import json
        from datetime import datetime

        # Strip trial_balance_data - keep only summary metadata
        if self.trial_balance_data:
            try:
                data = json.loads(self.trial_balance_data)
                # Keep only non-sensitive metadata
                metadata = {
                    'stripped_at': datetime.utcnow().isoformat(),
                    'original_account_count': len(data.get('accounts', [])) if 'accounts' in data else None,
                    'original_transaction_count': len(data.get('transactions', [])) if 'transactions' in data else None,
                    'data_hash': data.get('hash') if 'hash' in data else None,
                    'variance_percent': data.get('variance_percent') if 'variance_percent' in data else None,
                    'reconciliation_status': data.get('status') if 'status' in data else None
                }
                self.trial_balance_data = json.dumps(metadata)
            except (json.JSONDecodeError, TypeError) as e:
                # If parsing fails, just clear the data
                self.trial_balance_data = json.dumps({
                    'stripped_at': datetime.utcnow().isoformat(),
                    'error': 'Failed to parse original data'
                })

        # Strip live_status_data - keep only summary metadata
        if self.live_status_data:
            try:
                data = json.loads(self.live_status_data)
                # Keep only non-sensitive metadata
                metadata = {
                    'stripped_at': datetime.utcnow().isoformat(),
                    'final_phase': data.get('current_phase') if 'current_phase' in data else None,
                    'phase_count': len(data.get('phases', [])) if 'phases' in data else None,
                    'completion_status': data.get('status') if 'status' in data else None
                }
                self.live_status_data = json.dumps(metadata)
            except (json.JSONDecodeError, TypeError) as e:
                # If parsing fails, just clear the data
                self.live_status_data = json.dumps({
                    'stripped_at': datetime.utcnow().isoformat(),
                    'error': 'Failed to parse original data'
                })

        return True

    def __repr__(self):
        return f'<Migration {self.migration_id} - {self.status}>'