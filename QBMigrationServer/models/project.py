"""
Project Model
Manages migration projects for clients
"""

from models.database import db
from datetime import datetime
import secrets
import string


def generate_session_id() -> str:
    """Generate a unique session ID for a migration"""
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    return f"FB-{timestamp}-{random_part}"


class Project(db.Model):
    """Project model for grouping migrations by client"""
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
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
