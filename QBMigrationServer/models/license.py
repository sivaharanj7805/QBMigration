"""
License Model - Production-grade licensing for ForensicBridge
Features:
- Tiered licensing (Starter/Professional/Enterprise)
- Hardware fingerprint binding
- Migration usage tracking
- Activation audit trail
"""

from models.database import db
from datetime import datetime, timedelta
import secrets
import hashlib
import json


# License tier configuration
LICENSE_TIERS = {
    'starter': {'migrations': 10, 'name': 'Starter'},
    'professional': {'migrations': 50, 'name': 'Professional'},
    'enterprise': {'migrations': -1, 'name': 'Enterprise'}  # -1 = unlimited
}


class License(db.Model):
    """
    License model for tracking software licenses
    
    Security Features:
    - Cryptographically secure license keys
    - Hardware fingerprint binding (prevents license sharing)
    - Migration usage tracking with automatic decrement
    - Revocation support with audit trail
    """
    
    __tablename__ = 'licenses'
    
    # Primary Key
    id = db.Column(db.Integer, primary_key=True)
    
    # License Key (format: FB-XXXX-XXXX-XXXX-XXXX)
    license_key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    license_key_hash = db.Column(db.String(64), nullable=False, index=True)  # SHA-256 for lookup
    
    # User Association (optional - can be activated later)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    user_email = db.Column(db.String(255))  # Associated email at time of purchase
    
    # License Type
    tier = db.Column(db.String(20), default='starter', nullable=False)
    
    # Usage Tracking
    migrations_allowed = db.Column(db.Integer, default=10, nullable=False)
    migrations_used = db.Column(db.Integer, default=0, nullable=False)
    
    # Hardware Binding
    hardware_fingerprint = db.Column(db.String(128))
    fingerprint_set_at = db.Column(db.DateTime)
    
    # Activation
    is_activated = db.Column(db.Boolean, default=False)
    activation_date = db.Column(db.DateTime)
    last_validated = db.Column(db.DateTime)
    
    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_revoked = db.Column(db.Boolean, default=False)
    revocation_reason = db.Column(db.String(255))
    revoked_at = db.Column(db.DateTime)
    revoked_by = db.Column(db.String(100))
    
    # Expiry
    expires_at = db.Column(db.DateTime)
    
    # Purchase Info
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    order_id = db.Column(db.String(100))  # External order reference
    
    # Audit
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('licenses', lazy='dynamic'))
    activations = db.relationship('LicenseActivation', backref='license', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<License {self.license_key[:10]}... ({self.tier})>'
    
    # ========================================================================
    # LICENSE KEY GENERATION
    # ========================================================================
    
    @classmethod
    def generate_license_key(cls):
        """
        Generate a cryptographically secure license key
        Format: FB-XXXX-XXXX-XXXX-XXXX (20 chars + dashes)
        """
        # Generate 16 random bytes
        random_bytes = secrets.token_bytes(16)
        # Convert to hex and uppercase
        hex_string = random_bytes.hex().upper()
        # Format: FB-XXXX-XXXX-XXXX-XXXX
        formatted = f"FB-{hex_string[:4]}-{hex_string[4:8]}-{hex_string[8:12]}-{hex_string[12:16]}"
        return formatted
    
    @classmethod
    def hash_license_key(cls, license_key):
        """Create SHA-256 hash of license key for secure lookup"""
        normalized = license_key.strip().upper()
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    @classmethod
    def create_license(cls, tier='starter', user_email=None, order_id=None, expires_in_days=None):
        """
        Create a new license
        
        Args:
            tier: License tier (starter, professional, enterprise)
            user_email: Email address of purchaser
            order_id: External order reference
            expires_in_days: Optional expiry in days
            
        Returns:
            License: New license instance (not yet committed)
        """
        if tier not in LICENSE_TIERS:
            raise ValueError(f"Invalid tier: {tier}. Must be one of: {list(LICENSE_TIERS.keys())}")
        
        license_key = cls.generate_license_key()
        
        license = cls(
            license_key=license_key,
            license_key_hash=cls.hash_license_key(license_key),
            tier=tier,
            migrations_allowed=LICENSE_TIERS[tier]['migrations'],
            user_email=user_email,
            order_id=order_id
        )
        
        if expires_in_days:
            license.expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        
        return license
    
    @classmethod
    def find_by_key(cls, license_key):
        """Find license by key (using hash for security)"""
        key_hash = cls.hash_license_key(license_key)
        return cls.query.filter_by(license_key_hash=key_hash, is_revoked=False).first()
    
    # ========================================================================
    # ACTIVATION & VALIDATION
    # ========================================================================
    
    def activate(self, hardware_fingerprint, user_id=None):
        """
        Activate license on a specific hardware
        
        Args:
            hardware_fingerprint: Hardware fingerprint hash
            user_id: Optional user to associate
            
        Returns:
            bool: True if activated, False if already activated elsewhere
        """
        # Check if already activated on different hardware
        if self.is_activated and self.hardware_fingerprint:
            if self.hardware_fingerprint != hardware_fingerprint:
                return False  # Already activated on different machine
        
        self.hardware_fingerprint = hardware_fingerprint
        self.fingerprint_set_at = datetime.utcnow()
        self.is_activated = True
        self.activation_date = datetime.utcnow()
        
        if user_id:
            self.user_id = user_id
        
        # Log activation - use relationship to avoid null license_id on uncommitted licenses
        activation = LicenseActivation(
            hardware_fingerprint=hardware_fingerprint,
            action='activate',
            success=True
        )
        self.activations.append(activation)
        
        return True
    
    def validate(self, hardware_fingerprint):
        """
        Validate license is valid for given hardware
        
        Args:
            hardware_fingerprint: Hardware fingerprint to validate
            
        Returns:
            tuple: (is_valid, error_message)
        """
        # Check if license is active
        if not self.is_active:
            return False, "License is inactive"
        
        # Check if revoked
        if self.is_revoked:
            return False, f"License has been revoked: {self.revocation_reason}"
        
        # Check expiry
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False, "License has expired"
        
        # Check hardware fingerprint (if activated)
        if self.is_activated and self.hardware_fingerprint:
            if self.hardware_fingerprint != hardware_fingerprint:
                return False, "License is activated on a different machine"
        
        # Check migrations remaining
        if not self.has_migrations_remaining():
            return False, "No migrations remaining on license"
        
        # Update last validated timestamp
        self.last_validated = datetime.utcnow()
        
        return True, None
    
    def deactivate(self, reason=None, admin_email=None):
        """
        Deactivate license (allow transfer to new machine)
        
        Args:
            reason: Reason for deactivation
            admin_email: Admin who performed deactivation
        """
        old_fingerprint = self.hardware_fingerprint
        
        self.hardware_fingerprint = None
        self.fingerprint_set_at = None
        self.is_activated = False
        
        # Log deactivation - use relationship to handle uncommitted licenses
        activation = LicenseActivation(
            hardware_fingerprint=old_fingerprint,
            action='deactivate',
            success=True,
            notes=f"Deactivated by {admin_email}: {reason}"
        )
        self.activations.append(activation)
    
    def revoke(self, reason, revoked_by):
        """
        Permanently revoke license
        
        Args:
            reason: Reason for revocation
            revoked_by: Admin who revoked
        """
        self.is_revoked = True
        self.revocation_reason = reason
        self.revoked_at = datetime.utcnow()
        self.revoked_by = revoked_by
        self.is_active = False
        
        # Log revocation - use relationship to handle uncommitted licenses
        activation = LicenseActivation(
            hardware_fingerprint=self.hardware_fingerprint,
            action='revoke',
            success=True,
            notes=f"Revoked by {revoked_by}: {reason}"
        )
        self.activations.append(activation)
    
    # ========================================================================
    # MIGRATION TRACKING
    # ========================================================================
    
    def has_migrations_remaining(self):
        """Check if license has migrations remaining"""
        # -1 = unlimited
        if self.migrations_allowed == -1:
            return True
        return (self.migrations_used or 0) < (self.migrations_allowed or 0)
    
    def get_migrations_remaining(self):
        """Get number of migrations remaining"""
        if self.migrations_allowed == -1:
            return -1  # Unlimited
        return max(0, (self.migrations_allowed or 0) - (self.migrations_used or 0))
    
    def use_migration(self):
        """
        Use one migration from the license
        
        Returns:
            bool: True if migration was used, False if none remaining
        """
        if not self.has_migrations_remaining():
            return False
        
        # Don't increment for unlimited licenses
        if self.migrations_allowed != -1:
            self.migrations_used += 1
        
        return True
    
    def add_migrations(self, count):
        """
        Add migrations to license (for upgrades/add-ons)
        
        Args:
            count: Number of migrations to add
        """
        if self.migrations_allowed == -1:
            return  # Already unlimited
        
        self.migrations_allowed += count
    
    # ========================================================================
    # SERIALIZATION
    # ========================================================================
    
    def to_dict(self, include_sensitive=False):
        """Convert license to dictionary"""
        data = {
            'id': self.id,
            'tier': self.tier,
            'tier_name': LICENSE_TIERS.get(self.tier, {}).get('name', self.tier),
            'is_activated': self.is_activated,
            'is_active': self.is_active,
            'migrations_allowed': self.migrations_allowed,
            'migrations_used': self.migrations_used,
            'migrations_remaining': self.get_migrations_remaining(),
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'activation_date': self.activation_date.isoformat() if self.activation_date else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        
        if include_sensitive:
            data.update({
                'license_key': self.license_key,
                'hardware_fingerprint': self.hardware_fingerprint,
                'user_email': self.user_email,
                'order_id': self.order_id,
                'is_revoked': self.is_revoked,
                'revocation_reason': self.revocation_reason
            })
        
        return data


class LicenseActivation(db.Model):
    """
    Audit log for license activations/deactivations
    
    Tracks all license state changes for security auditing
    """
    
    __tablename__ = 'license_activations'
    
    id = db.Column(db.Integer, primary_key=True)
    license_id = db.Column(db.Integer, db.ForeignKey('licenses.id'), nullable=False)
    
    # Action Details
    action = db.Column(db.String(20), nullable=False)  # activate, deactivate, validate, revoke
    hardware_fingerprint = db.Column(db.String(128))
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    
    # Result
    success = db.Column(db.Boolean, default=True)
    error_message = db.Column(db.String(255))
    notes = db.Column(db.Text)
    
    # Timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f'<LicenseActivation {self.action} for License {self.license_id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'license_id': self.license_id,
            'action': self.action,
            'success': self.success,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
