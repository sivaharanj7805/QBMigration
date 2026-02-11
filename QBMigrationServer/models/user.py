"""
User Model with Enterprise Security
- Argon2id password hashing
- 2FA with TOTP
- Password history tracking
- Account lockout protection
"""

import hmac
import json
import re
import secrets
from datetime import datetime, timedelta, timezone

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError
from flask_login import UserMixin
from models.database import db
from utils.env_helper import is_production

# Initialize Argon2 password hasher with secure parameters
ph = PasswordHasher(
    time_cost=3,  # Number of iterations
    memory_cost=65536,  # Memory usage in KiB (64 MB)
    parallelism=4,  # Number of parallel threads
    hash_len=32,  # Length of hash in bytes
    salt_len=16,  # Length of salt in bytes
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

    __tablename__ = "users"

    # Primary Key
    id = db.Column(db.Integer, primary_key=True)

    # Authentication
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # Indexes for performance
    __table_args__ = (
        db.Index("idx_user_email_active", "email", "is_active"),
        db.Index("idx_user_subscription_tier", "subscription_tier"),
    )

    # Profile
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    company_name = db.Column(db.String(255))
    phone = db.Column(db.String(20))

    # Account Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    email_verified = db.Column(db.Boolean, default=False)
    email_verification_token = db.Column(db.String(255))

    # RBAC - Role-Based Access Control (100/100 FIX)
    # Roles: 'user' (default), 'admin', 'super_admin'
    role = db.Column(db.String(50), default="user", nullable=False, index=True)

    # Security - Account Lockout
    failed_login_attempts = db.Column(db.Integer, default=0)
    last_failed_login = db.Column(db.DateTime)
    account_locked_until = db.Column(db.DateTime)

    # Security - Password Management
    password_changed_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc)
    )
    password_history = db.Column(db.Text)  # JSON array of previous password hashes
    must_change_password = db.Column(db.Boolean, default=False)
    # HIGH-02 FIX: Track last used password reset token JTI to prevent reuse
    password_reset_jti = db.Column(db.String(64), nullable=True)

    # Security - Multi-Factor Authentication
    mfa_enabled = db.Column(db.Boolean, default=False)
    # SECURITY FIX: MFA secrets encrypted at rest to prevent exposure on DB breach
    _mfa_secret_encrypted = db.Column("mfa_secret_encrypted", db.Text, nullable=True)
    _backup_codes_encrypted = db.Column(
        "backup_codes_encrypted", db.Text, nullable=True
    )
    # DEPRECATED LEGACY COLUMNS - Retained only for data migration compatibility.
    # These columns store UNENCRYPTED MFA data and MUST be dropped after all rows
    # have been migrated to encrypted columns. See migrate_legacy_mfa_data() below.
    # SECURITY: Never write new data to these columns - always use encrypted variants.
    mfa_secret = db.Column(
        db.String(32), nullable=True
    )  # DEPRECATED: DROP after migration
    backup_codes = db.Column(db.Text, nullable=True)  # DEPRECATED: DROP after migration

    # Security - Device Fingerprinting
    trusted_devices = db.Column(db.Text)  # JSON array of device fingerprints

    # Timestamps
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_login = db.Column(db.DateTime)
    last_login_at = db.Column(db.DateTime)  # For anomaly detection
    last_login_ip = db.Column(db.String(45))  # For anomaly detection (supports IPv6)

    # QuickBooks Online OAuth (tokens stored encrypted)
    qbo_access_token = db.Column(db.Text, nullable=True)  # Encrypted access token
    qbo_refresh_token = db.Column(db.Text, nullable=True)  # Encrypted refresh token
    qbo_realm_id = db.Column(db.String(50), nullable=True)  # Company ID in QBO
    qbo_token_expires_at = db.Column(db.DateTime, nullable=True)
    qbo_connected_at = db.Column(db.DateTime, nullable=True)

    def _get_encryption_key(self):
        """Get encryption key for QBO tokens.

        FIX M-06: Require dedicated QBO_ENCRYPTION_KEY for domain separation.
        BACKUP_ENCRYPTION_KEY fallback only in development to aid migration.
        """
        from flask import current_app
        import os

        key = current_app.config.get("QBO_ENCRYPTION_KEY")
        if not key:
            if is_production():
                raise ValueError(
                    "QBO_ENCRYPTION_KEY not configured. "
                    "Production requires dedicated encryption key per domain."
                )
            # Development fallback with warning
            key = current_app.config.get("BACKUP_ENCRYPTION_KEY")
            if key:
                import logging

                logging.getLogger(__name__).warning(
                    "Using BACKUP_ENCRYPTION_KEY as fallback for QBO tokens. "
                    "Set QBO_ENCRYPTION_KEY for production."
                )
        if not key:
            raise ValueError(
                "QBO_ENCRYPTION_KEY not configured - cannot encrypt QBO tokens"
            )
        return key.encode() if isinstance(key, str) else key

    def set_qbo_tokens(self, access_token, refresh_token, realm_id, expires_at):
        """Set encrypted QBO tokens"""
        from cryptography.fernet import Fernet

        try:
            f = Fernet(self._get_encryption_key())

            # Encrypt tokens
            self.qbo_access_token = (
                f.encrypt(access_token.encode()).decode() if access_token else None
            )
            self.qbo_refresh_token = (
                f.encrypt(refresh_token.encode()).decode() if refresh_token else None
            )
            self.qbo_realm_id = realm_id
            self.qbo_token_expires_at = expires_at
            self.qbo_connected_at = datetime.now(timezone.utc)
        except Exception as e:
            from flask import current_app

            current_app.logger.error(f"Failed to encrypt QBO tokens: {str(e)}")
            raise

    def get_qbo_access_token(self):
        """Get decrypted QBO access token"""
        if not self.qbo_access_token:
            return None
        import logging

        from cryptography.fernet import Fernet

        try:
            f = Fernet(self._get_encryption_key())
            return f.decrypt(self.qbo_access_token.encode()).decode()
        except Exception as e:
            logging.getLogger(__name__).error(
                f"Failed to decrypt QBO access token for user {self.id}: {type(e).__name__}"
            )
            return None

    def get_qbo_refresh_token(self):
        """Get decrypted QBO refresh token"""
        if not self.qbo_refresh_token:
            return None
        import logging

        from cryptography.fernet import Fernet

        try:
            f = Fernet(self._get_encryption_key())
            return f.decrypt(self.qbo_refresh_token.encode()).decode()
        except Exception as e:
            logging.getLogger(__name__).error(
                f"Failed to decrypt QBO refresh token for user {self.id}: {type(e).__name__}"
            )
            return None

    def clear_qbo_tokens(self):
        """Clear QBO tokens (logout)"""
        self.qbo_access_token = None
        self.qbo_refresh_token = None
        self.qbo_realm_id = None
        self.qbo_token_expires_at = None

    # Subscription Tier & Migration Tracking
    subscription_tier = db.Column(
        db.String(20), default=None, nullable=True
    )  # None = not selected yet
    tier_purchased_at = db.Column(db.DateTime, nullable=True)
    migrations_purchased = db.Column(
        db.Integer, default=0, nullable=False
    )  # Total purchased
    migrations_used = db.Column(db.Integer, default=0, nullable=False)  # Total consumed

    # Relationships
    migrations = db.relationship(
        "Migration", backref="user", lazy="dynamic", cascade="all, delete-orphan"
    )

    # ========================================================================
    # RBAC - ROLE-BASED ACCESS CONTROL (100/100 FIX)
    # ========================================================================

    # Define role hierarchy (higher = more permissions)
    ROLE_HIERARCHY = {"user": 0, "support": 1, "admin": 2, "super_admin": 3}

    def has_role(self, role: str) -> bool:
        """
        Check if user has a specific role.

        Args:
            role: Role to check (e.g., 'admin', 'user')

        Returns:
            bool: True if user has the role
        """
        return self.role == role

    def has_role_or_higher(self, required_role: str) -> bool:
        """
        Check if user has a role at or above the required level.

        Uses role hierarchy to determine if user has sufficient privileges.

        Args:
            required_role: Minimum required role

        Returns:
            bool: True if user has sufficient role level
        """
        user_level = self.ROLE_HIERARCHY.get(self.role, 0)
        required_level = self.ROLE_HIERARCHY.get(required_role, 0)
        return user_level >= required_level

    def is_admin(self) -> bool:
        """Check if user is an admin or super_admin."""
        return self.has_role_or_higher("admin")

    def is_super_admin(self) -> bool:
        """Check if user is a super_admin."""
        return self.role == "super_admin"

    def can_manage_users(self) -> bool:
        """Check if user can manage other users."""
        return self.is_admin()

    def can_view_all_migrations(self) -> bool:
        """Check if user can view all migrations (not just their own)."""
        return self.is_admin()

    def can_access_admin_dashboard(self) -> bool:
        """Check if user can access admin dashboard."""
        return self.has_role_or_higher("support")

    def __repr__(self):
        return f"<User {self.email}>"

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
            raise ValueError(
                "Password has been used recently. Please choose a different password."
            )

        # Hash password with Argon2id
        password_hash = ph.hash(password)

        # Add to password history
        self._add_to_password_history(password_hash)

        # Set new password
        self.password_hash = password_hash
        self.password_changed_at = datetime.now(timezone.utc)

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

        Requirements (PCI DSS v4.0.1 compliant):
        - At least 12 characters
        - Contains uppercase letter
        - Contains lowercase letter
        - Contains digit
        - Contains special character (LOW-01 FIX)

        Args:
            password: Password to validate

        Raises:
            ValueError: If password doesn't meet requirements
        """
        if len(password) < 12:
            raise ValueError("Password must be at least 12 characters long")

        if not re.search(r"[A-Z]", password):
            raise ValueError("Password must contain at least one uppercase letter")

        if not re.search(r"[a-z]", password):
            raise ValueError("Password must contain at least one lowercase letter")

        if not re.search(r"\d", password):
            raise ValueError("Password must contain at least one digit")

        if not re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:\'",.<>?/\\`~]', password):
            raise ValueError(
                "Password must contain at least one special character (!@#$%^&*...)"
            )

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

        # HIGH FIX: Validate JSON structure when loading password history
        # Prevents code injection or corruption attacks via malformed JSON
        # FIX: Use database-level locking for thread-safe password history access
        from models.database import is_postgresql

        try:
            # Acquire row-level lock to prevent concurrent modifications (PostgreSQL only)
            # SQLite doesn't support FOR SHARE but has implicit locking
            if is_postgresql():
                db.session.execute(
                    db.text(
                        "SELECT password_history FROM users WHERE id = :user_id FOR SHARE"
                    ),
                    {"user_id": self.id},
                )

            history = json.loads(self.password_history)

            # Validate structure: must be a list
            if not isinstance(history, list):
                import logging

                logging.getLogger(__name__).warning(
                    f"Invalid password_history structure for user"
                    f" {self.id}: expected list,"
                    f" got {type(history).__name__}"
                )
                return False

            # Validate each item: must be a non-empty string (hash)
            validated_history = []
            for item in history:
                if isinstance(item, str) and item:
                    validated_history.append(item)
                else:
                    import logging

                    logging.getLogger(__name__).warning(
                        f"Invalid item in password_history for user {self.id}: {type(item).__name__}"
                    )
            history = validated_history

        except (json.JSONDecodeError, TypeError) as e:
            import logging

            logging.getLogger(__name__).warning(
                f"Failed to parse password_history for user {self.id}: {e}"
            )
            return False

        # Check against each previous password
        for old_hash in history:
            try:
                if ph.verify(old_hash, password):
                    return True
            except (VerifyMismatchError, VerificationError, InvalidHash):
                continue

        return False

    def _add_to_password_history(self, password_hash):
        """
        Add password hash to history

        Maintains last 5 passwords

        Args:
            password_hash: Hashed password to add
        """
        # HIGH FIX: Validate JSON structure when loading password history
        # FIX: Use database-level locking for thread-safe password history manipulation
        try:
            # Acquire row-level lock to prevent concurrent modifications (PostgreSQL only)
            # SQLite doesn't support FOR UPDATE but has implicit locking
            # M-01 FIX: Use shared is_postgresql() instead of duplicating logic
            from models.database import is_postgresql

            if is_postgresql():
                db.session.execute(
                    db.text(
                        "SELECT password_history FROM users WHERE id = :user_id FOR UPDATE"
                    ),
                    {"user_id": self.id},
                )

            history = json.loads(self.password_history) if self.password_history else []

            # Validate structure: must be a list
            if not isinstance(history, list):
                import logging

                logging.getLogger(__name__).warning(
                    f"Invalid password_history structure for user {self.id}, resetting"
                )
                history = []

            # Validate each item: must be a non-empty string (hash)
            validated_history = []
            for item in history:
                if isinstance(item, str) and item:
                    validated_history.append(item)
            history = validated_history

        except (json.JSONDecodeError, TypeError):
            history = []

        # Validate the new hash before adding
        if not isinstance(password_hash, str) or not password_hash:
            raise ValueError("Invalid password hash format")

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
        FIX M-01: Pure query method - no side effects, no state mutation.
        Only checks if account is currently locked without modifying any fields.
        Call clear_expired_lock() explicitly to persist the unlock.

        Returns:
            bool: True if account is locked, False otherwise
        """
        if not self.account_locked_until:
            return False

        # Check if lock has expired
        # Handle both timezone-aware and naive datetimes
        now = datetime.now(timezone.utc)
        lock_until = self.account_locked_until
        if lock_until.tzinfo is None:
            lock_until = lock_until.replace(tzinfo=timezone.utc)

        return now <= lock_until

    def clear_expired_lock(self):
        """FIX M-01: Explicitly clear an expired lock. Must be called within a transaction.
        Returns True if lock was cleared, False if still active or not locked."""
        if not self.account_locked_until:
            return False

        now = datetime.now(timezone.utc)
        lock_until = self.account_locked_until
        if lock_until.tzinfo is None:
            lock_until = lock_until.replace(tzinfo=timezone.utc)

        if now > lock_until:
            self.account_locked_until = None
            self.failed_login_attempts = 0
            return True
        return False

    def record_failed_login(self):
        """
        Record failed login attempt.
        AUDIT FIX MEDIUM-14: Uses SQL-level atomic increment to prevent race
        conditions where two concurrent failed logins each read the same count
        and only increment by 1 instead of 2.
        Locks account after 5 failed attempts.
        """
        now = datetime.now(timezone.utc)
        # Atomic SQL-level increment avoids TOCTOU race on concurrent requests
        db.session.execute(
            db.update(User)
            .where(User.id == self.id)
            .values(
                failed_login_attempts=db.func.coalesce(User.failed_login_attempts, 0) + 1,
                last_failed_login=now,
            )
        )
        db.session.flush()
        db.session.refresh(self)

        # Lock account after 5 failures
        if self.failed_login_attempts >= 5:
            self.account_locked_until = now + timedelta(minutes=15)

    def record_successful_login(self, ip_address=None):
        """
        Record successful login

        Resets failed login counter and updates login tracking for anomaly detection.

        Args:
            ip_address: Optional IP address for anomaly detection
        """
        now = datetime.now(timezone.utc)
        self.failed_login_attempts = 0
        self.last_failed_login = None
        self.account_locked_until = None
        # Use only last_login_at (last_login is redundant and kept for legacy compatibility)
        self.last_login_at = now  # For anomaly detection
        if ip_address:
            self.last_login_ip = ip_address

    # ========================================================================
    # MULTI-FACTOR AUTHENTICATION
    # ========================================================================

    def _get_mfa_secret(self) -> str:
        """Get decrypted MFA secret (prefers encrypted, falls back to legacy).

        FIX M-02: Uses dedicated MFA_ENCRYPTION_KEY with proper domain separation.
        Legacy unencrypted fallback blocked in production.
        """
        import logging
        import os

        # Try encrypted first
        if self._mfa_secret_encrypted:
            try:
                from cryptography.fernet import Fernet
                from flask import current_app

                # AUDIT FIX HIGH-3: Require MFA_ENCRYPTION_KEY strictly.
                # Fallback chain removed to prevent key rotation data loss.
                key = current_app.config.get("MFA_ENCRYPTION_KEY")
                if not key:
                    logging.getLogger(__name__).error(
                        "MFA_ENCRYPTION_KEY not configured. "
                        "Set this environment variable to decrypt MFA secrets."
                    )
                    return None
                if key:
                    f = Fernet(key.encode() if isinstance(key, str) else key)
                    return f.decrypt(self._mfa_secret_encrypted.encode()).decode()
            except Exception as e:
                logging.getLogger(__name__).error(
                    f"Failed to decrypt MFA secret for user {self.id}: {e}"
                )
                return None
        # Fall back to legacy unencrypted column (DEPRECATED)
        if self.mfa_secret:
            if is_production():
                logging.getLogger(__name__).error(
                    f"User {self.id} has unencrypted MFA secret in production. "
                    "Run migrate_legacy_mfa_data() immediately."
                )
                return None  # Block unencrypted access in production
            logging.getLogger(__name__).warning(
                f"User {self.id} still using legacy unencrypted mfa_secret column. "
                "Run migrate_legacy_mfa_data() to encrypt."
            )
        return self.mfa_secret

    def _set_mfa_secret(self, value: str):
        """Set encrypted MFA secret.

        MED-01 FIX: Never falls back to plaintext storage. Raises on encryption
        failure to prevent unencrypted secrets from being persisted.
        """
        if value is None:
            self._mfa_secret_encrypted = None
            self.mfa_secret = None  # Clear legacy column
            return
        from cryptography.fernet import Fernet
        from flask import current_app

        # AUDIT FIX HIGH-3: Use ONLY MFA_ENCRYPTION_KEY — no fallback chain.
        # This ensures encrypt/decrypt always use the same key and prevents
        # data loss during key rotation.
        key = current_app.config.get("MFA_ENCRYPTION_KEY")
        if not key:
            raise ValueError(
                "MFA_ENCRYPTION_KEY not configured - cannot store MFA secret. "
                "Set this environment variable before enabling MFA."
            )
        f = Fernet(key.encode() if isinstance(key, str) else key)
        self._mfa_secret_encrypted = f.encrypt(value.encode()).decode()
        self.mfa_secret = None  # Clear legacy column

    def _get_backup_codes(self):
        """Get decrypted backup codes (prefers encrypted, falls back to legacy).

        MED-01 FIX: Logs deprecation warning when falling back to legacy column.
        """
        # Try encrypted first
        if self._backup_codes_encrypted:
            try:
                from cryptography.fernet import Fernet
                from flask import current_app

                key = current_app.config.get(
                    "QBO_ENCRYPTION_KEY"
                ) or current_app.config.get("BACKUP_ENCRYPTION_KEY")
                if key:
                    f = Fernet(key.encode() if isinstance(key, str) else key)
                    return json.loads(
                        f.decrypt(self._backup_codes_encrypted.encode()).decode()
                    )
            except Exception as exc:
                import logging
                logging.getLogger(__name__).debug("Failed to decrypt backup codes: %s", exc)
        # AUDIT FIX HIGH-5: Block legacy unencrypted backup codes in production.
        # Plaintext fallback is only allowed in development to aid migration.
        if self.backup_codes:
            import logging

            _log = logging.getLogger(__name__)
            from flask import current_app

            env = current_app.config.get("FLASK_ENV") or os.environ.get(
                "FLASK_ENV", "development"
            )
            if env == "production":
                _log.error(
                    "User %s has legacy unencrypted backup_codes. "
                    "Run migrate_legacy_mfa_data() to encrypt. "
                    "Plaintext access is blocked in production.",
                    self.id,
                )
                return None
            _log.warning(
                "User %s still using legacy unencrypted backup_codes column. "
                "Run migrate_legacy_mfa_data() to encrypt.",
                self.id,
            )
            try:
                return json.loads(self.backup_codes)
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    def _set_backup_codes(self, value: list):
        """Set encrypted backup codes.

        MED-01 FIX: Never falls back to plaintext storage. Raises on encryption
        failure to prevent unencrypted codes from being persisted.
        """
        if value is None:
            self._backup_codes_encrypted = None
            self.backup_codes = None  # Clear legacy column
            return
        from cryptography.fernet import Fernet
        from flask import current_app

        key = current_app.config.get("QBO_ENCRYPTION_KEY") or current_app.config.get(
            "BACKUP_ENCRYPTION_KEY"
        )
        if not key:
            raise ValueError(
                "Encryption key not configured - cannot store backup codes in plaintext"
            )
        f = Fernet(key.encode() if isinstance(key, str) else key)
        self._backup_codes_encrypted = f.encrypt(json.dumps(value).encode()).decode()
        self.backup_codes = None  # Clear legacy column

    def enable_2fa(self):
        """
        Enable 2FA for user

        Returns:
            tuple: (secret, qr_code_url, backup_codes)
        """
        # Generate TOTP secret
        secret = pyotp.random_base32()
        self._set_mfa_secret(secret)

        # Generate QR code URL
        totp = pyotp.TOTP(secret)
        qr_url = totp.provisioning_uri(name=self.email, issuer_name="QB Migration")

        # Generate backup codes
        backup_codes = [secrets.token_hex(4).upper() for _ in range(10)]
        self._set_backup_codes(backup_codes)

        # Enable 2FA
        self.mfa_enabled = True

        return secret, qr_url, backup_codes

    def disable_2fa(self):
        """Disable 2FA for user"""
        self.mfa_enabled = False
        self._set_mfa_secret(None)
        self._set_backup_codes(None)

    def verify_2fa_token(self, token):
        """
        Verify 2FA token

        Args:
            token: TOTP token or backup code

        Returns:
            bool: True if valid, False otherwise
        """
        mfa_secret = self._get_mfa_secret()
        if not self.mfa_enabled or not mfa_secret:
            return False

        # Try TOTP verification
        totp = pyotp.TOTP(mfa_secret)
        if totp.verify(token, valid_window=1):
            return True

        # Try backup codes (constant-time comparison to prevent timing attacks)
        backup_codes = self._get_backup_codes()
        if backup_codes:
            try:
                token_upper = token.upper()
                matched_code = None
                for code in backup_codes:
                    if hmac.compare_digest(token_upper, code):
                        matched_code = code
                if matched_code is not None:
                    backup_codes.remove(matched_code)
                    self._set_backup_codes(backup_codes)
                    return True
            except (TypeError, ValueError):
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
        except (json.JSONDecodeError, TypeError):
            return False

    def add_trusted_device(self, fingerprint):
        """
        Add device to trusted list

        Args:
            fingerprint: Device fingerprint hash
        """
        try:
            devices = json.loads(self.trusted_devices) if self.trusted_devices else []
        except (json.JSONDecodeError, TypeError):
            devices = []

        if fingerprint not in devices:
            devices.append(fingerprint)

        # Keep only last 5 devices
        devices = devices[-5:]

        self.trusted_devices = json.dumps(devices)

    # ========================================================================
    # SUBSCRIPTION TIER MANAGEMENT
    # ========================================================================

    # Tier configuration
    TIER_CONFIG = {
        "starter": {"migrations": 1, "name": "Starter", "max_transactions": 5000},
        "business": {"migrations": 1, "name": "Business", "max_transactions": 25000},
        "professional": {
            "migrations": 1,
            "name": "Professional",
            "max_transactions": 100000,
        },
        "enterprise": {
            "migrations": 1,
            "name": "Enterprise",
            "max_transactions": 500000,
        },
        "forensic": {
            "migrations": 1,
            "name": "Forensic",
            "max_transactions": -1,
        },  # -1 = unlimited
    }

    def get_migrations_remaining(self):
        """Get number of migrations remaining for this user"""
        purchased = getattr(self, "migrations_purchased", None) or 0
        used = getattr(self, "migrations_used", None) or 0
        return max(0, purchased - used)

    def has_migrations_remaining(self):
        """Check if user has migrations remaining"""
        return self.get_migrations_remaining() > 0

    def use_migration(self):
        """
        Use one migration from the user's balance.

        Returns:
            bool: True if migration was used, False if none remaining
        """
        if not self.has_migrations_remaining():
            return False
        self.migrations_used = (self.migrations_used or 0) + 1
        return True

    def add_migrations(self, count, tier=None):
        """
        Add migrations to user's balance (for purchases/upgrades).

        Args:
            count: Number of migrations to add
            tier: Optional tier to set
        """
        self.migrations_purchased = (self.migrations_purchased or 0) + count
        if tier:
            self.subscription_tier = tier
            self.tier_purchased_at = datetime.now(timezone.utc)

    def get_tier_info(self):
        """
        Get current tier information for the user.

        CRITICAL FIX: Query MigrationCredit table for accurate credit counts.
        The MigrationCredit table is the source of truth for purchased credits
        (created via Stripe payments), while User.migrations_purchased/used
        fields may be stale or out of sync.

        Returns:
            dict with tier details and migrations info
        """
        tier = getattr(self, "subscription_tier", None) or "none"
        config = self.TIER_CONFIG.get(tier, {})

        # CRITICAL FIX: Get actual credit counts from MigrationCredit table
        # This is the source of truth for paid credits
        try:
            from models.migration_credit import MigrationCredit

            # Count credits by status (only paid credits)
            credits_available = MigrationCredit.query.filter_by(
                user_id=self.id, status="available", payment_status="paid"
            ).count()

            credits_used = MigrationCredit.query.filter_by(
                user_id=self.id, status="used", payment_status="paid"
            ).count()

            # Total paid credits (available + used)
            credits_purchased = credits_available + credits_used

            # Determine tier from most recent paid credit if user tier is not set
            if tier == "none" or tier is None:
                latest_credit = (
                    MigrationCredit.query.filter_by(
                        user_id=self.id, payment_status="paid"
                    )
                    .order_by(MigrationCredit.paid_at.desc())
                    .first()
                )

                if latest_credit:
                    tier = latest_credit.tier_type
                    config = self.TIER_CONFIG.get(tier, {})

        except Exception as e:
            # Fallback to legacy User fields if MigrationCredit query fails
            # This maintains backwards compatibility during migrations
            import logging

            logging.getLogger(__name__).warning(
                f"Failed to query MigrationCredit table for user {self.id}: {e}. "
                "Falling back to User model fields."
            )
            credits_purchased = getattr(self, "migrations_purchased", None) or 0
            credits_used = getattr(self, "migrations_used", None) or 0
            credits_available = max(0, credits_purchased - credits_used)

        return {
            "tier": tier,
            "tier_name": config.get("name", "Free Trial"),
            "max_transactions": config.get("max_transactions", 0),
            "migrations_purchased": credits_purchased,
            "migrations_used": credits_used,
            "migrations_remaining": credits_available,
            "has_tier": (tier != "none" and tier is not None) or credits_available > 0,
        }

    # ========================================================================
    # FLASK-LOGIN METHODS
    # ========================================================================

    def get_id(self):
        """Required by Flask-Login.

        Uses SQLAlchemy identity key to avoid DetachedInstanceError
        when the instance is not bound to a session.
        """
        from sqlalchemy import inspect as sa_inspect

        try:
            state = sa_inspect(self)
            if state.identity:
                return str(state.identity[0])
        except Exception as exc:
            import logging
            logging.getLogger(__name__).debug("SQLAlchemy inspect failed for user identity: %s", exc)
        return str(self.id)

    @property
    def is_authenticated(self):
        """Required by Flask-Login"""
        return True

    @property
    def is_anonymous(self):
        """Required by Flask-Login"""
        return False

    # ========================================================================
    # MED-01 FIX: Legacy MFA Data Migration
    # ========================================================================

    def migrate_legacy_mfa_data(self) -> bool:
        """Migrate unencrypted legacy MFA columns to encrypted columns.

        Reads plaintext mfa_secret and backup_codes, encrypts them into
        _mfa_secret_encrypted and _backup_codes_encrypted, then NULLs out
        the legacy columns. Safe to call multiple times (idempotent).

        Returns:
            True if data was migrated, False if no legacy data found.
        """
        migrated = False
        if self.mfa_secret and not self._mfa_secret_encrypted:
            self._set_mfa_secret(self.mfa_secret)
            migrated = True
        if self.backup_codes and not self._backup_codes_encrypted:
            try:
                codes = json.loads(self.backup_codes)
                self._set_backup_codes(codes)
            except (json.JSONDecodeError, TypeError):
                pass
            migrated = True
        return migrated

    @classmethod
    def migrate_all_legacy_mfa(cls) -> int:
        """Batch-migrate all users with legacy unencrypted MFA data.

        Usage (in Flask shell or migration script):
            with app.app_context():
                count = User.migrate_all_legacy_mfa()
                db.session.commit()
                print(f"Migrated {count} users")

        Returns:
            Number of users migrated.
        """
        import logging

        logger = logging.getLogger(__name__)
        users = cls.query.filter(
            db.or_(
                db.and_(
                    cls.mfa_secret.isnot(None), cls._mfa_secret_encrypted.is_(None)
                ),
                db.and_(
                    cls.backup_codes.isnot(None), cls._backup_codes_encrypted.is_(None)
                ),
            )
        ).all()
        count = 0
        for user in users:
            try:
                if user.migrate_legacy_mfa_data():
                    count += 1
            except Exception as e:
                logger.error(f"Failed to migrate MFA data for user {user.id}: {e}")
        logger.info(
            f"Legacy MFA migration complete: {count}/{len(users)} users migrated"
        )
        return count
