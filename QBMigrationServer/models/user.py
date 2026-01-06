"""
User Model with Enterprise Security
- Argon2id password hashing
- 2FA with TOTP
- Password history tracking
- Account lockout protection
"""

from models.database import db
from flask_login import UserMixin
from datetime import datetime, timedelta
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHash
import pyotp
import json
import re
import secrets

# Initialize Argon2 password hasher with secure parameters
ph = PasswordHasher(
    time_cost=3,        # Number of iterations
    memory_cost=65536,  # Memory usage in KiB (64 MB)
    parallelism=4,      # Number of parallel threads
    hash_len=32,        # Length of hash in bytes
    salt_len=16         # Length of salt in bytes
)


class User(UserMixin, db.Model):
    """
    User model with comprehensive security features
    
    Security Features:
    - Argon2id password hashing (industry best practice)
    - Multi-factor authentication (TOTP)
    - Password history (prevents reuse)
    - Account lockout (prevents brute force)
    - Failed login tracking
    - Device fingerprinting support
    """
    
    __tablename__ = 'users'
    
    # Primary Key
    id = db.Column(db.Integer, primary_key=True)
    
    # Authentication
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Profile
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    company_name = db.Column(db.String(255))
    phone = db.Column(db.String(20))
    
    # Account Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    email_verified = db.Column(db.Boolean, default=False)
    email_verification_token = db.Column(db.String(255))
    
    # Security - Account Lockout
    failed_login_attempts = db.Column(db.Integer, default=0)
    last_failed_login = db.Column(db.DateTime)
    account_locked_until = db.Column(db.DateTime)
    
    # Security - Password Management
    password_changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    password_history = db.Column(db.Text)  # JSON array of previous password hashes
    must_change_password = db.Column(db.Boolean, default=False)
    
    # Security - Multi-Factor Authentication
    mfa_enabled = db.Column(db.Boolean, default=False)
    mfa_secret = db.Column(db.String(32))  # TOTP secret
    backup_codes = db.Column(db.Text)  # JSON array of backup codes
    
    # Security - Device Fingerprinting
    trusted_devices = db.Column(db.Text)  # JSON array of device fingerprints
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    migrations = db.relationship('Migration', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<User {self.email}>'
    
    # ========================================================================
    # PASSWORD MANAGEMENT
    # ========================================================================
    
    def set_password(self, password):
        """
        Set user password with validation and history tracking
        
        Args:
            password: New password
            
        Raises:
            ValueError: If password is weak or recently used
        """
        # Validate password strength
        self._validate_password_strength(password)
        
        # CRITICAL: Check password history BEFORE hashing
        if self.check_password_reuse(password):
            raise ValueError("Password has been used recently. Please choose a different password.")
        
        # Hash password with Argon2id
        password_hash = ph.hash(password)
        
        # Add to password history
        self._add_to_password_history(password_hash)
        
        # Set new password
        self.password_hash = password_hash
        self.password_changed_at = datetime.utcnow()
    
    def check_password(self, password):
        """
        Check if provided password matches stored hash
        
        Args:
            password: Password to check
            
        Returns:
            bool: True if password matches, False otherwise
        """
        if not self.password_hash:
            return False
        
        try:
            # Verify password
            is_valid = ph.verify(self.password_hash, password)
            
            # CRITICAL FIX: Track failed attempts in the database
            # Note: This is tracked in auth.py, not here
            # This method only verifies the password
            
            return is_valid
        except (VerifyMismatchError, VerificationError, InvalidHash):
            return False
        except Exception:
            return False
    
    def _validate_password_strength(self, password):
        """
        Validate password meets strength requirements
        
        Requirements:
        - At least 8 characters
        - Contains uppercase letter
        - Contains lowercase letter
        - Contains digit
        
        Args:
            password: Password to validate
            
        Raises:
            ValueError: If password doesn't meet requirements
        """
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long")
        
        if not re.search(r'[A-Z]', password):
            raise ValueError("Password must contain at least one uppercase letter")
        
        if not re.search(r'[a-z]', password):
            raise ValueError("Password must contain at least one lowercase letter")
        
        if not re.search(r'\d', password):
            raise ValueError("Password must contain at least one digit")
    
    def check_password_reuse(self, password):
        """
        Check if password was recently used
        
        Args:
            password: Password to check
            
        Returns:
            bool: True if password was recently used, False otherwise
        """
        if not self.password_history:
            return False
        
        # Parse password history
        try:
            history = json.loads(self.password_history)
        except:
            return False
        
        # Check against each previous password
        for old_hash in history:
            try:
                if ph.verify(old_hash, password):
                    return True
            except:
                continue
        
        return False
    
    def _add_to_password_history(self, password_hash):
        """
        Add password hash to history
        
        Maintains last 5 passwords
        
        Args:
            password_hash: Hashed password to add
        """
        # Parse existing history
        try:
            history = json.loads(self.password_history) if self.password_history else []
        except:
            history = []
        
        # Add new hash
        history.append(password_hash)
        
        # Keep only last 5
        history = history[-5:]
        
        # Save
        self.password_history = json.dumps(history)
    
    # ========================================================================
    # ACCOUNT LOCKOUT
    # ========================================================================
    
    def is_locked(self):
        """
        Check if account is currently locked
        
        Returns:
            bool: True if account is locked, False otherwise
        """
        if not self.account_locked_until:
            return False
        
        # Check if lock has expired
        if datetime.utcnow() > self.account_locked_until:
            # Lock expired, reset
            self.account_locked_until = None
            self.failed_login_attempts = 0
            return False
        
        return True
    
    def record_failed_login(self):
        """
        Record failed login attempt
        
        Locks account after 5 failed attempts
        """
        self.failed_login_attempts += 1
        self.last_failed_login = datetime.utcnow()
        
        # Lock account after 5 failures
        if self.failed_login_attempts >= 5:
            self.account_locked_until = datetime.utcnow() + timedelta(minutes=15)
    
    def record_successful_login(self):
        """
        Record successful login
        
        Resets failed login counter
        """
        self.failed_login_attempts = 0
        self.last_failed_login = None
        self.account_locked_until = None
        self.last_login = datetime.utcnow()
    
    # ========================================================================
    # MULTI-FACTOR AUTHENTICATION
    # ========================================================================
    
    def enable_2fa(self):
        """
        Enable 2FA for user
        
        Returns:
            tuple: (secret, qr_code_url, backup_codes)
        """
        # Generate TOTP secret
        secret = pyotp.random_base32()
        self.mfa_secret = secret
        
        # Generate QR code URL
        totp = pyotp.TOTP(secret)
        qr_url = totp.provisioning_uri(
            name=self.email,
            issuer_name='QB Migration'
        )
        
        # Generate backup codes
        backup_codes = [secrets.token_hex(4).upper() for _ in range(10)]
        self.backup_codes = json.dumps(backup_codes)
        
        # Enable 2FA
        self.mfa_enabled = True
        
        return secret, qr_url, backup_codes
    
    def disable_2fa(self):
        """Disable 2FA for user"""
        self.mfa_enabled = False
        self.mfa_secret = None
        self.backup_codes = None
    
    def verify_2fa_token(self, token):
        """
        Verify 2FA token
        
        Args:
            token: TOTP token or backup code
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not self.mfa_enabled or not self.mfa_secret:
            return False
        
        # Try TOTP verification
        totp = pyotp.TOTP(self.mfa_secret)
        if totp.verify(token, valid_window=1):
            return True
        
        # Try backup codes
        if self.backup_codes:
            try:
                codes = json.loads(self.backup_codes)
                if token.upper() in codes:
                    # Remove used backup code
                    codes.remove(token.upper())
                    self.backup_codes = json.dumps(codes)
                    return True
            except:
                pass
        
        return False
    
    # ========================================================================
    # DEVICE FINGERPRINTING
    # ========================================================================
    
    def is_trusted_device(self, fingerprint):
        """
        Check if device is trusted
        
        Args:
            fingerprint: Device fingerprint hash
            
        Returns:
            bool: True if trusted, False otherwise
        """
        if not self.trusted_devices:
            return False
        
        try:
            devices = json.loads(self.trusted_devices)
            return fingerprint in devices
        except:
            return False
    
    def add_trusted_device(self, fingerprint):
        """
        Add device to trusted list
        
        Args:
            fingerprint: Device fingerprint hash
        """
        try:
            devices = json.loads(self.trusted_devices) if self.trusted_devices else []
        except:
            devices = []
        
        if fingerprint not in devices:
            devices.append(fingerprint)
        
        # Keep only last 5 devices
        devices = devices[-5:]
        
        self.trusted_devices = json.dumps(devices)
    
    # ========================================================================
    # FLASK-LOGIN METHODS
    # ========================================================================
    
    def get_id(self):
        """Required by Flask-Login"""
        return str(self.id)
    
    @property
    def is_authenticated(self):
        """Required by Flask-Login"""
        return True
    
    @property
    def is_anonymous(self):
        """Required by Flask-Login"""
        return False