from models.database import db
from flask_login import UserMixin
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHash
from datetime import datetime, timedelta
import secrets
import re
import json
import pyotp

# Initialize Argon2 password hasher (OWASP recommended)
ph = PasswordHasher(
    time_cost=2,
    memory_cost=65536,
    parallelism=1,
    hash_len=32,
    salt_len=16
)


class User(db.Model, UserMixin):
    """User model with comprehensive security features"""
    __tablename__ = 'users'
    
    # Primary identifiers
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Profile
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    company_name = db.Column(db.String(255))
    
    # Security - Account Status
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    
    # Security - Login Protection
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)
    last_login_ip = db.Column(db.String(50))
    last_device_fingerprint = db.Column(db.String(64))
    
    # Security - Email Verification
    verification_token = db.Column(db.String(100), unique=True, nullable=True)
    verification_token_expires = db.Column(db.DateTime, nullable=True)
    
    # Security - Password Management
    password_changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    password_history = db.Column(db.Text)  # JSON array of old password hashes
    require_password_change = db.Column(db.Boolean, default=False)
    
    # Security - 2FA/MFA
    mfa_secret = db.Column(db.String(32))
    mfa_enabled = db.Column(db.Boolean, default=False)
    mfa_backup_codes = db.Column(db.Text)  # JSON array of backup codes
    
    # Security - CAPTCHA
    failed_captcha_attempts = db.Column(db.Integer, default=0)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    migrations = db.relationship('Migration', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """
        Hash password using Argon2id with history tracking
        
        Args:
            password: Plain text password
            
        Raises:
            ValueError: If password doesn't meet requirements or was used before
        """
        # Validate password strength
        if not self._validate_password_strength(password):
            raise ValueError("Password does not meet security requirements")
        
        # Check password history
        if self.check_password_reuse(password):
            raise ValueError("Password was used recently. Please choose a different password.")
        
        # Hash new password
        new_hash = ph.hash(password)
        
        # Save old password to history
        self._add_to_password_history(self.password_hash)
        
        # Update password
        self.password_hash = new_hash
        self.password_changed_at = datetime.utcnow()
        self.require_password_change = False
    
    def check_password(self, password):
        """
        Verify password against hash
        
        Args:
            password: Plain text password to verify
            
        Returns:
            bool: True if password matches, False otherwise
        """
        try:
            ph.verify(self.password_hash, password)
            
            # Check if rehashing is needed (algorithm updated)
            if ph.check_needs_rehash(self.password_hash):
                self.password_hash = ph.hash(password)
                db.session.commit()
            
            return True
        except (VerifyMismatchError, VerificationError, InvalidHash):
            return False
    
    def check_password_reuse(self, new_password):
        """
        Check if password was used before
        
        Args:
            new_password: Password to check
            
        Returns:
            bool: True if password was used before
        """
        if not self.password_history:
            return False
        
        try:
            history = json.loads(self.password_history)
            
            # Check last N passwords
            for old_hash in history[-5:]:
                try:
                    ph.verify(old_hash, new_password)
                    return True  # Password was used before
                except:
                    continue
            
            return False
        except:
            return False
    
    def _add_to_password_history(self, password_hash):
        """Add password hash to history"""
        if not password_hash:
            return
        
        try:
            history = json.loads(self.password_history) if self.password_history else []
        except:
            history = []
        
        history.append(password_hash)
        
        # Keep only last 5 passwords
        history = history[-5:]
        
        self.password_history = json.dumps(history)
    
    @staticmethod
    def _validate_password_strength(password):
        """
        Validate password meets security requirements
        
        Args:
            password: Password to validate
            
        Returns:
            bool: True if valid
        """
        if len(password) < 8:
            return False
        
        if not re.search(r'[A-Z]', password):
            return False
        
        if not re.search(r'[a-z]', password):
            return False
        
        if not re.search(r'\d', password):
            return False
        
        # Check common passwords
        common_passwords = ['password', '12345678', 'qwerty', 'abc123', 'password123', 'admin123']
        if password.lower() in common_passwords:
            return False
        
        return True
    
    # ============================================================================
    # ACCOUNT LOCKOUT
    # ============================================================================
    
    def is_locked(self):
        """Check if account is locked"""
        if self.locked_until and datetime.utcnow() < self.locked_until:
            return True
        
        if self.locked_until and datetime.utcnow() >= self.locked_until:
            self.unlock_account()
        
        return False
    
    def increment_failed_login(self):
        """Increment failed login counter and lock if threshold reached"""
        self.failed_login_attempts += 1
        
        if self.failed_login_attempts >= 5:
            self.locked_until = datetime.utcnow() + timedelta(minutes=15)
        
        db.session.commit()
    
    def reset_failed_login(self):
        """Reset failed login counter"""
        self.failed_login_attempts = 0
        self.locked_until = None
        db.session.commit()
    
    def unlock_account(self):
        """Manually unlock account"""
        self.failed_login_attempts = 0
        self.locked_until = None
        db.session.commit()
    
    # ============================================================================
    # EMAIL VERIFICATION
    # ============================================================================
    
    def generate_verification_token(self):
        """Generate secure email verification token"""
        self.verification_token = secrets.token_urlsafe(32)
        self.verification_token_expires = datetime.utcnow() + timedelta(hours=24)
        db.session.commit()
        return self.verification_token
    
    def verify_email(self, token):
        """
        Verify email with token
        
        Args:
            token: Verification token
            
        Returns:
            bool: True if verified successfully
        """
        if not self.verification_token or self.verification_token != token:
            return False
        
        if self.verification_token_expires and datetime.utcnow() > self.verification_token_expires:
            return False
        
        self.is_verified = True
        self.verification_token = None
        self.verification_token_expires = None
        db.session.commit()
        return True
    
    # ============================================================================
    # TWO-FACTOR AUTHENTICATION (2FA)
    # ============================================================================
    
    def enable_2fa(self):
        """
        Enable 2FA and generate secret
        
        Returns:
            tuple: (secret, qr_code_url)
        """
        if not self.mfa_secret:
            self.mfa_secret = pyotp.random_base32()
        
        self.mfa_enabled = True
        
        # Generate backup codes
        backup_codes = [secrets.token_hex(4) for _ in range(10)]
        self.mfa_backup_codes = json.dumps(backup_codes)
        
        db.session.commit()
        
        # Generate QR code URL
        totp = pyotp.TOTP(self.mfa_secret)
        qr_url = totp.provisioning_uri(
            name=self.email,
            issuer_name='QB Migration'
        )
        
        return self.mfa_secret, qr_url, backup_codes
    
    def disable_2fa(self):
        """Disable 2FA"""
        self.mfa_enabled = False
        db.session.commit()
    
    def verify_2fa_token(self, token):
        """
        Verify 2FA token
        
        Args:
            token: 6-digit TOTP token or backup code
            
        Returns:
            bool: True if valid
        """
        if not self.mfa_enabled or not self.mfa_secret:
            return True  # 2FA not enabled
        
        # Check TOTP token
        totp = pyotp.TOTP(self.mfa_secret)
        if totp.verify(token, valid_window=1):
            return True
        
        # Check backup codes
        if self.mfa_backup_codes:
            try:
                backup_codes = json.loads(self.mfa_backup_codes)
                if token in backup_codes:
                    # Remove used backup code
                    backup_codes.remove(token)
                    self.mfa_backup_codes = json.dumps(backup_codes)
                    db.session.commit()
                    return True
            except:
                pass
        
        return False
    
    # ============================================================================
    # UTILITY METHODS
    # ============================================================================
    
    def update_login_info(self, ip_address, device_fingerprint):
        """Update login information"""
        self.last_login = datetime.utcnow()
        self.last_login_ip = ip_address
        self.last_device_fingerprint = device_fingerprint
        db.session.commit()
    
    def to_dict(self, include_sensitive=False):
        """Convert user to dictionary"""
        data = {
            'id': self.id,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'company_name': self.company_name,
            'is_active': self.is_active,
            'is_verified': self.is_verified,
            'mfa_enabled': self.mfa_enabled,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }
        
        if include_sensitive:
            data.update({
                'failed_login_attempts': self.failed_login_attempts,
                'is_locked': self.is_locked(),
                'locked_until': self.locked_until.isoformat() if self.locked_until else None,
                'require_password_change': self.require_password_change
            })
        
        return data
    
    def __repr__(self):
        return f'<User {self.email}>'