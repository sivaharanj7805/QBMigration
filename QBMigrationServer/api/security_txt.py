"""
Security.txt Endpoint

FIX 100/100: Implements RFC 9116 security.txt for vulnerability disclosure.

This provides security researchers with contact information for reporting
vulnerabilities according to the security.txt standard.

Reference: https://securitytxt.org/
"""

from flask import Blueprint, Response
from datetime import datetime, timezone
import os

security_txt_bp = Blueprint('security_txt', __name__)


def _get_security_txt_content() -> str:
    """
    Generate security.txt content per RFC 9116.

    Environment Variables:
        SECURITY_CONTACT_EMAIL: Email for security reports (default: security@forensicbridge.io)
        SECURITY_POLICY_URL: URL to security policy page
        SECURITY_ACKNOWLEDGMENTS_URL: URL to acknowledgments page
    """
    contact_email = os.getenv('SECURITY_CONTACT_EMAIL', 'security@forensicbridge.io')
    policy_url = os.getenv('SECURITY_POLICY_URL', 'https://forensicbridge.io/security')
    acknowledgments_url = os.getenv('SECURITY_ACKNOWLEDGMENTS_URL', 'https://forensicbridge.io/security/acknowledgments')

    # Calculate expiration date (1 year from now)
    expires = datetime.now(timezone.utc).replace(year=datetime.now().year + 1)
    expires_str = expires.strftime('%Y-%m-%dT%H:%M:%S.000Z')

    content = f"""# ForensicBridge Security Contact Information
# This file follows RFC 9116 (security.txt standard)
# https://securitytxt.org/

Contact: mailto:{contact_email}
Expires: {expires_str}
Preferred-Languages: en
Canonical: https://forensicbridge.io/.well-known/security.txt

# Security Policy
Policy: {policy_url}

# Acknowledgments
Acknowledgments: {acknowledgments_url}

# Hiring Security Professionals
# Hiring: https://forensicbridge.io/careers

# Our Commitment
# We take security seriously and appreciate responsible disclosure.
# We commit to:
# - Acknowledge receipt within 48 hours
# - Provide updates on remediation progress
# - Recognize valid reports in our acknowledgments page
# - Not pursue legal action for good-faith security research
"""
    return content


@security_txt_bp.route('/.well-known/security.txt', methods=['GET'])
def security_txt():
    """
    Serve security.txt file per RFC 9116.

    This endpoint provides standardized security contact information
    for vulnerability researchers.
    """
    content = _get_security_txt_content()
    return Response(
        content,
        mimetype='text/plain',
        headers={
            'Content-Type': 'text/plain; charset=utf-8',
            'Cache-Control': 'public, max-age=86400',  # Cache for 1 day
        }
    )


@security_txt_bp.route('/security.txt', methods=['GET'])
def security_txt_root():
    """
    Alternative location for security.txt (root path).

    Some scanners look for /security.txt in addition to /.well-known/security.txt
    """
    content = _get_security_txt_content()
    return Response(
        content,
        mimetype='text/plain',
        headers={
            'Content-Type': 'text/plain; charset=utf-8',
            'Cache-Control': 'public, max-age=86400',
        }
    )
