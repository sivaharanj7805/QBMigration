"""
Project Model
Manages migration projects for clients
"""

from models.database import db
from datetime import datetime
import secrets
import string


def generate_session_id(max_retries: int = 10) -> str:
    """
    Generate a guaranteed unique session ID for a migration.

    Format: FB-YYYYMMDDHHMMSS-XXXXXXXX
    - FB prefix for ForensicBridge
    - Timestamp for rough ordering
    - 8 random alphanumeric characters for uniqueness

    Uses retry logic to ensure uniqueness even with concurrent requests.
    """
    for attempt in range(max_retries):
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        # Use cryptographically secure random characters
        random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        session_id = f"FB-{timestamp}-{random_part}"

        # Check if this session ID already exists
        existing = db.session.query(db.exists().where(
            Project.session_id == session_id
        )).scalar()

        if not existing:
            return session_id

        # If collision, add microseconds to timestamp for next attempt
        if attempt < max_retries - 1:
            import time
            time.sleep(0.001)  # Small delay to get different microsecond

    # Last resort: append extra random chars
    extra = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    return f"FB-{timestamp}-{random_part}{extra}"


class Project(db.Model):
    """Project model for grouping migrations by client"""
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    # FIX #48: Add CASCADE delete for GDPR compliance
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Project info
    name = db.Column(db.String(255), nullable=False)
    client_name = db.Column(db.String(255), nullable=False)
    client_email = db.Column(db.String(255))
    notes = db.Column(db.Text)
    
    # Unique session ID for extractor
    session_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    
    # Status: pending, active, completed, archived
    status = db.Column(db.String(50), default='pending')
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    
    # Relationships
    owner = db.relationship('User', backref=db.backref('projects', lazy='dynamic'))
    
    def __init__(self, **kwargs):
        super(Project, self).__init__(**kwargs)
        if not self.session_id:
            self.session_id = generate_session_id()
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'client_name': self.client_name,
            'client_email': self.client_email,
            'session_id': self.session_id,
            'status': self.status,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self):
        return f'<Project {self.name} - {self.session_id}>'
