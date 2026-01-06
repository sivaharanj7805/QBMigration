import re
from typing import Tuple

def validate_email(email: str) -> Tuple[bool, str]:
    """Validate email format"""
    if not email:
        return False, "Email is required"
    
    if len(email) > 255:
        return False, "Email too long (max 255 characters)"
    
    # RFC 5322 simplified regex
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, "Invalid email format"
    
    return True, ""

def validate_password(password: str) -> Tuple[bool, str]:
    """Validate password strength"""
    if not password:
        return False, "Password is required"
    
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    
    if len(password) > 128:
        return False, "Password too long (max 128 characters)"
    
    # Check complexity
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    
    if not (has_upper and has_lower and has_digit):
        return False, "Password must contain uppercase, lowercase, and number"
    
    return True, ""

def sanitize_string(value: str, max_length: int = 255) -> str:
    """Sanitize string input"""
    if not value:
        return ""
    
    # Remove null bytes (can cause SQL issues)
    value = value.replace('\x00', '')
    
    # Trim whitespace
    value = value.strip()
    
    # Truncate to max length
    if len(value) > max_length:
        value = value[:max_length]
    
    return value