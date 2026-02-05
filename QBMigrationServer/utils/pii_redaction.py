"""
PII Redaction Utilities
Provides functions to redact Personally Identifiable Information (PII) from logs
to comply with GDPR, PIPEDA, and other privacy regulations.
"""

import re
import hashlib
from typing import Optional


def hash_email(email: str) -> str:
    """
    Hash an email address to create a consistent, non-reversible identifier.

    Args:
        email: Email address to hash

    Returns:
        SHA-256 hash of the email (first 12 characters)

    Example:
        >>> hash_email("user@example.com")
        "usr_a1b2c3d4e5f6"
    """
    if not email:
        return "unknown"

    # Create consistent hash
    email_hash = hashlib.sha256(email.lower().encode()).hexdigest()[:12]
    return f"usr_{email_hash}"


def redact_email(text: str) -> str:
    """
    Redact email addresses from text while preserving domain for debugging.

    Args:
        text: Text potentially containing email addresses

    Returns:
        Text with emails redacted to user***@domain.com format

    Example:
        >>> redact_email("Error for user@example.com")
        "Error for use***@example.com"
    """
    # Email regex pattern
    email_pattern = r"\b([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b"

    def redact_match(match):
        username = match.group(1)
        domain = match.group(2)
        # Keep first 3 chars of username, redact rest
        redacted_user = username[:3] + "***" if len(username) > 3 else "***"
        return f"{redacted_user}@{domain}"

    return re.sub(email_pattern, redact_match, text)


def hash_ip(ip_address: str) -> str:
    """
    Hash an IP address for GDPR-compliant storage.

    Args:
        ip_address: IP address to hash

    Returns:
        SHA-256 hash of the IP (first 16 characters)

    Example:
        >>> hash_ip("192.168.1.1")
        "ip_a1b2c3d4e5f6g7h8"
    """
    if not ip_address:
        return "unknown"

    ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()[:16]
    return f"ip_{ip_hash}"


def redact_phone(text: str) -> str:
    """
    Redact phone numbers from text while avoiding false positives.

    Args:
        text: Text potentially containing phone numbers

    Returns:
        Text with phone numbers redacted

    Example:
        >>> redact_phone("Call 555-123-4567")
        "Call XXX-XXX-4567"

    False positive prevention:
        - Excludes date-like patterns (2024-01-15)
        - Excludes version numbers (1.2.3.4)
        - Excludes IDs and reference numbers with letters
        - Excludes IP addresses
    """
    # Patterns that look like phone numbers but aren't
    # Pre-process to mark these as "safe" before phone redaction
    safe_patterns = {
        # Date patterns (YYYY-MM-DD, MM-DD-YYYY, DD-MM-YYYY)
        r"\b\d{4}[-/]\d{2}[-/]\d{2}\b": lambda m: f"__DATE_{m.start()}__",
        r"\b\d{2}[-/]\d{2}[-/]\d{4}\b": lambda m: f"__DATE_{m.start()}__",
        # Time patterns (HH:MM:SS, including milliseconds)
        r"\b\d{2}:\d{2}:\d{2}(?:\.\d+)?\b": lambda m: f"__TIME_{m.start()}__",
        # Version numbers (1.2.3, 10.0.0.1)
        r"\b\d+\.\d+\.\d+(?:\.\d+)?\b": lambda m: f"__VERSION_{m.start()}__",
        # IP addresses
        r"\b(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b": lambda m: f"__IP_{m.start()}__",
        # Invoice/reference numbers with letters (INV-12345678, REF123456789)
        r"\b[A-Z]{2,4}[-]?\d{6,12}\b": lambda m: f"__REF_{m.start()}__",
        # Zip codes (should not be redacted)
        r"\b\d{5}(?:-\d{4})?\b": lambda m: f"__ZIP_{m.start()}__",
        # Account numbers (often just digits but context matters)
        r"(?:account|acct|acc)[:\s#]*\d{4,10}\b": lambda m: f"__ACCT_{m.start()}__",
    }

    result = text
    replacements = {}

    # Mark safe patterns
    for pattern, replacement_fn in safe_patterns.items():
        for match in re.finditer(pattern, result, re.IGNORECASE):
            placeholder = replacement_fn(match)
            replacements[placeholder] = match.group(0)

    # Replace safe patterns with placeholders
    for placeholder, original in replacements.items():
        result = result.replace(original, placeholder, 1)

    # Match phone number formats (more specific patterns)
    phone_patterns = [
        # US format with area code: (555) 123-4567 or 555-123-4567
        r"(?<![.\d])(?:\(\d{3}\)\s*|\b\d{3}[-.])\d{3}[-.]?\d{4}\b(?![.\d])",
        # International with + prefix: +1-555-123-4567
        r"\+\d{1,3}[-.\s]?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b",
        # Compact international: +12125551234 (10+ digits after +)
        r"\+\d{10,15}\b",
    ]

    for pattern in phone_patterns:
        result = re.sub(pattern, "XXX-XXX-XXXX", result)

    # Restore safe patterns
    for placeholder, original in replacements.items():
        result = result.replace(placeholder, original)

    return result


def redact_ssn(text: str) -> str:
    """
    Redact Social Security Numbers from text.

    Args:
        text: Text potentially containing SSNs

    Returns:
        Text with SSNs redacted

    Example:
        >>> redact_ssn("SSN: 123-45-6789")
        "SSN: XXX-XX-6789"
    """
    # Match SSN patterns
    ssn_pattern = r"\b\d{3}[-]?\d{2}[-]?\d{4}\b"

    def redact_match(match):
        ssn = match.group(0)
        # Keep last 4 digits only
        return f"XXX-XX-{ssn[-4:]}"

    return re.sub(ssn_pattern, redact_match, text)


def redact_credit_card(text: str) -> str:
    """
    Redact credit card numbers from text.

    Args:
        text: Text potentially containing credit card numbers

    Returns:
        Text with credit card numbers redacted

    Example:
        >>> redact_credit_card("Card: 4532-1234-5678-9010")
        "Card: XXXX-XXXX-XXXX-9010"
    """
    # Match credit card patterns (13-16 digits, with optional separators)
    cc_pattern = r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{3,4}\b"

    def redact_match(match):
        card = match.group(0)
        # Keep last 4 digits only
        last_four = card.replace("-", "").replace(" ", "")[-4:]
        return f"XXXX-XXXX-XXXX-{last_four}"

    return re.sub(cc_pattern, redact_match, text)


def redact_all_pii(text: str, preserve_email_hash: bool = False) -> str:
    """
    Redact all common PII types from text.

    Args:
        text: Text potentially containing PII
        preserve_email_hash: If True, replace emails with hashes instead of redaction

    Returns:
        Text with all PII redacted

    Example:
        >>> redact_all_pii("User user@example.com with SSN 123-45-6789 called 555-123-4567")
        "User use***@example.com with SSN XXX-XX-6789 called XXX-XXX-XXXX"
    """
    if not text:
        return text

    result = text

    # Redact in order of specificity
    result = redact_ssn(result)
    result = redact_credit_card(result)
    result = redact_phone(result)

    if preserve_email_hash:
        # Extract emails and replace with hashes
        email_pattern = r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b"
        emails = re.findall(email_pattern, result)
        for email in emails:
            result = result.replace(email, hash_email(email))
    else:
        result = redact_email(result)

    return result


def create_safe_log_message(message: str, user_email: Optional[str] = None) -> str:
    """
    Create a privacy-safe log message by redacting PII and optionally adding user hash.

    Args:
        message: Original log message
        user_email: Optional user email to include as hash

    Returns:
        Privacy-safe log message

    Example:
        >>> create_safe_log_message("Login failed for user@example.com", "user@example.com")
        "[usr_a1b2c3d4e5f6] Login failed"
    """
    # Redact any PII in the message
    safe_message = redact_all_pii(message)

    # Prepend user hash if provided
    if user_email:
        user_hash = hash_email(user_email)
        return f"[{user_hash}] {safe_message}"

    return safe_message
