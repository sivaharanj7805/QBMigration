from models.database import db
from datetime import datetime
import secrets

class Migration(db.Model):
    __tablename__ = 'migrations'
    
    id = db.Column(db.Integer, primary_key=True)
    migration_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Company info
    company_name = db.Column(db.String(255))
    
    # Status
    status = db.Column(db.String(50), default='pending')
    # Status values: pending, processing, completed, failed
    
    # Progress
    progress_percent = db.Column(db.Integer, default=0)
    current_step = db.Column(db.String(255))
    
    # Data counts
    customers_count = db.Column(db.Integer, default=0)
    vendors_count = db.Column(db.Integer, default=0)
    accounts_count = db.Column(db.Integer, default=0)
    items_count = db.Column(db.Integer, default=0)
    invoices_count = db.Column(db.Integer, default=0)
    
    # Results
    customers_migrated = db.Column(db.Integer, default=0)
    vendors_migrated = db.Column(db.Integer, default=0)
    accounts_migrated = db.Column(db.Integer, default=0)
    items_migrated = db.Column(db.Integer, default=0)
    invoices_migrated = db.Column(db.Integer, default=0)
    
    # Files
    encrypted_file_path = db.Column(db.String(512))
    verification_report_path = db.Column(db.String(512))
    
    # Error tracking
    error_message = db.Column(db.Text)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    # Data deletion
    scheduled_deletion_at = db.Column(db.DateTime)
    deleted_at = db.Column(db.DateTime)
    
    def __init__(self, user_id, **kwargs):
        self.migration_id = secrets.token_urlsafe(16)
        self.user_id = user_id
        
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def update_progress(self, percent, step):
        """Update migration progress"""
        self.progress_percent = percent
        self.current_step = step
        db.session.commit()
    
    def mark_started(self):
        """Mark migration as started"""
        self.status = 'processing'
        self.started_at = datetime.utcnow()
        db.session.commit()
    
    def mark_completed(self):
        """Mark migration as completed"""
        self.status = 'completed'
        self.completed_at = datetime.utcnow()
        self.progress_percent = 100
        db.session.commit()
    
    def mark_failed(self, error_message):
        """Mark migration as failed"""
        self.status = 'failed'
        self.error_message = error_message
        self.completed_at = datetime.utcnow()
        db.session.commit()
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'migration_id': self.migration_id,
            'company_name': self.company_name,
            'status': self.status,
            'progress_percent': self.progress_percent,
            'current_step': self.current_step,
            'data_counts': {
                'customers': self.customers_count,
                'vendors': self.vendors_count,
                'accounts': self.accounts_count,
                'items': self.items_count,
                'invoices': self.invoices_count
            },
            'results': {
                'customers': self.customers_migrated,
                'vendors': self.vendors_migrated,
                'accounts': self.accounts_migrated,
                'items': self.items_migrated,
                'invoices': self.invoices_migrated
            },
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error_message': self.error_message
        }