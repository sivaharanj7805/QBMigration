from models.database import db
from datetime import datetime, timedelta
from flask import current_app
import uuid
import json
from cryptography.fernet import Fernet
import hashlib


class Migration(db.Model):
    """Migration model - tracks AWS-based ephemeral migrations with full audit trail"""
    __tablename__ = 'migrations'
    
    # Primary identifiers
    id = db.Column(db.Integer, primary_key=True)
    migration_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
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
    
    # Cost tracking
    estimated_cost_usd = db.Column(db.Numeric(10, 4))
    actual_cost_usd = db.Column(db.Numeric(10, 4))
    cost_breakdown = db.Column(db.Text)  # JSON: {ec2: X, s3: Y, data_transfer: Z}
    
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
    
    # Webhook tracking (prevent replay attacks)
    webhook_processed_ids = db.Column(db.Text)  # JSON array of processed webhook IDs
    last_webhook_at = db.Column(db.DateTime)
    
    def __init__(self, **kwargs):
        super(Migration, self).__init__(**kwargs)
        if not self.migration_id:
            self.migration_id = str(uuid.uuid4())
        if not self.expires_at:
            self.expires_at = datetime.utcnow() + timedelta(hours=48)
    
    # ============================================================================
    # ERROR MESSAGE ENCRYPTION (prevent leaking QB data in errors)
    # ============================================================================
    
    def set_error_message(self, message):
        """Set encrypted error message"""
        if not message:
            self.error_message_encrypted = None
            return
        
        try:
            key = current_app.config.get('BACKUP_ENCRYPTION_KEY')
            if not key:
                # Fallback: store unencrypted in development
                self.error_message_encrypted = message
                return
            
            f = Fernet(key.encode() if isinstance(key, str) else key)
            self.error_message_encrypted = f.encrypt(message.encode()).decode()
        except Exception as e:
            # Log error but don't fail
            current_app.logger.error(f"Failed to encrypt error message: {str(e)}")
            self.error_message_encrypted = "Error message encryption failed"
    
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
        except:
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
        """Mark migration as uploading to S3"""
        self.status = 'uploading'
        db.session.commit()
    
    def mark_as_uploaded(self, s3_uri, s3_bucket, s3_key):
        """Mark migration as uploaded to S3"""
        self.status = 'uploaded'
        self.s3_uri = s3_uri
        self.s3_bucket = s3_bucket
        self.s3_key = s3_key
        db.session.commit()
    
    def mark_as_provisioning(self):
        """Mark as provisioning EC2 instance"""
        self.status = 'provisioning'
        self.current_step = 'Creating AWS instance'
        db.session.commit()
    
    def mark_as_processing(self, instance_id):
        """Mark as processing on EC2 instance"""
        self.status = 'processing'
        self.aws_instance_id = instance_id
        self.started_at = datetime.utcnow()
        self.current_step = 'Running migration on AWS'
        db.session.commit()
    
    def mark_as_completed(self, results=None):
        """Mark migration as completed"""
        self.status = 'completed'
        self.completed_at = datetime.utcnow()
        self.progress_percent = 100
        self.current_step = 'Completed'
        
        if results:
            self.customers_migrated = results.get('customers', 0)
            self.vendors_migrated = results.get('vendors', 0)
            self.invoices_migrated = results.get('invoices', 0)
            self.bills_migrated = results.get('bills', 0)
            self.items_migrated = results.get('items', 0)
            self.total_records_migrated = results.get('total', 0)
        
        db.session.commit()
    
    def mark_as_failed(self, error_message, error_code=None):
        """Mark migration as failed"""
        self.status = 'failed'
        self.set_error_message(error_message)
        self.error_code = error_code
        self.completed_at = datetime.utcnow()
        db.session.commit()
    
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
        except:
            return False
    
    def mark_webhook_processed(self, webhook_id):
        """Mark webhook as processed"""
        try:
            processed = json.loads(self.webhook_processed_ids) if self.webhook_processed_ids else []
        except:
            processed = []
        
        if webhook_id not in processed:
            processed.append(webhook_id)
            # Keep only last 50 webhook IDs
            processed = processed[-50:]
            self.webhook_processed_ids = json.dumps(processed)
        
        self.last_webhook_at = datetime.utcnow()
        db.session.commit()
    
    # ============================================================================
    # EXPIRATION & HEALTH CHECKS
    # ============================================================================
    
    def is_expired(self):
        """Check if migration has expired"""
        return datetime.utcnow() > self.expires_at
    
    def is_stuck(self, timeout_hours=6):
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
                except:
                    pass
        
        return data
    
    def __repr__(self):
        return f'<Migration {self.migration_id} - {self.status}>'