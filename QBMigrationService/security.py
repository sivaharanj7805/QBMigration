import hashlib
import hmac
import secrets
import pyotp
from datetime import datetime, timedelta

class SecurityManager:
    """Additional security utilities"""
    
    @staticmethod
    def generate_session_id():
        """Generate cryptographically secure session ID"""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def hash_password(password):
        """Hash password using SHA-256 (use bcrypt in production)"""
        import bcrypt
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    @staticmethod
    def verify_password(password, hashed):
        """Verify password against hash"""
        import bcrypt
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    
    @staticmethod
    def generate_2fa_secret():
        """Generate TOTP secret for 2FA"""
        return pyotp.random_base32()
    
    @staticmethod
    def verify_2fa_code(secret, code):
        """Verify 2FA TOTP code"""
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)
    
    @staticmethod
    def generate_api_signature(payload, secret):
        """Generate HMAC signature for API requests"""
        message = payload.encode('utf-8')
        signature = hmac.new(
            secret.encode('utf-8'),
            message,
            hashlib.sha256
        ).hexdigest()
        return signature
    
    @staticmethod
    def verify_api_signature(payload, signature, secret):
        """Verify HMAC signature"""
        expected = SecurityManager.generate_api_signature(payload, secret)
        return hmac.compare_digest(signature, expected)
    
    @staticmethod
    def rate_limit_check(user_id, max_requests=10, window_minutes=1):
        """Simple in-memory rate limiting"""
        # In production, use Redis
        if not hasattr(SecurityManager, '_rate_limit_store'):
            SecurityManager._rate_limit_store = {}
        
        now = datetime.now()
        window_start = now - timedelta(minutes=window_minutes)
        
        if user_id not in SecurityManager._rate_limit_store:
            SecurityManager._rate_limit_store[user_id] = []
        
        # Clean old requests
        SecurityManager._rate_limit_store[user_id] = [
            req_time for req_time in SecurityManager._rate_limit_store[user_id]
            if req_time > window_start
        ]
        
        # Check limit
        if len(SecurityManager._rate_limit_store[user_id]) >= max_requests:
            return False
        
        # Add this request
        SecurityManager._rate_limit_store[user_id].append(now)
        return True