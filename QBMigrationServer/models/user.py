from models.database import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import secrets

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Profile
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    company_name = db.Column(db.String(255))
    phone = db.Column(db.String(50))
    
    # Account status
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(255), unique=True)
    
    # 2FA
    totp_secret = db.Column(db.String(32))
    is_2fa_enabled = db.Column(db.Boolean, default=False)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    migrations = db.relationship('Migration', backref='user', lazy='dynamic')
    
    def __init__(self, email, password, **kwargs):
        self.email = email.lower()
        self.set_password(password)
        self.verification_token = secrets.token_urlsafe(32)
        
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    
    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)
    
    def generate_verification_token(self):
        """Generate new verification token"""
        self.verification_token = secrets.token_urlsafe(32)
        return self.verification_token
    
    def verify_email(self):
        """Mark email as verified"""
        self.is_verified = True
        self.verification_token = None
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'company_name': self.company_name,
            'is_verified': self.is_verified,
            'is_2fa_enabled': self.is_2fa_enabled,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }