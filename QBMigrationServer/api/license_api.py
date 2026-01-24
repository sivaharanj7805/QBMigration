"""
License API - Production-grade license validation endpoints

Endpoints:
- POST /api/license/validate - Validate license key + hardware fingerprint
- POST /api/license/activate - Activate license on hardware
- GET  /api/license/usage    - Get remaining migrations
- POST /api/license/deactivate - Transfer license (admin only)
"""

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, timedelta
import jwt
import os
import logging

from models.database import db
from models.license import License, LicenseActivation, LICENSE_TIERS
from extensions import limiter
from config import Config
# FIX #53: Import PII redaction for secure logging
from utils.pii_redaction import hash_email

license_bp = Blueprint('license', __name__, url_prefix='/api/license')
logger = logging.getLogger(__name__)


# ============================================================================
# HELPERS
# ============================================================================

def get_license_secret():
    """Get license signing secret"""
    return os.getenv('LICENSE_SECRET_KEY', current_app.config.get('SECRET_KEY', 'dev-secret'))


def generate_license_token(license_obj, hardware_fingerprint):
    """
    Generate a signed JWT token for offline license validation
    
    Args:
        license_obj: License instance
        hardware_fingerprint: Hardware fingerprint
        
    Returns:
        str: Signed JWT token
    """
    payload = {
        'license_id': license_obj.id,
        'tier': license_obj.tier,
        'hardware_fingerprint': hardware_fingerprint,
        'migrations_remaining': license_obj.get_migrations_remaining(),
        'expires_at': license_obj.expires_at.isoformat() if license_obj.expires_at else None,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=24)  # Token valid for 24 hours
    }
    
    return jwt.encode(payload, get_license_secret(), algorithm='HS256')


def log_activation(license_obj, action, fingerprint, success, error=None, notes=None):
    """Log license activation attempt"""
    activation = LicenseActivation(
        license_id=license_obj.id,
        action=action,
        hardware_fingerprint=fingerprint,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent', '')[:255],
        success=success,
        error_message=error,
        notes=notes
    )
    db.session.add(activation)


def admin_required(f):
    """Decorator for admin-only endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is authenticated and is admin
        if not current_user.is_authenticated:
            return jsonify({'error': 'Authentication required'}), 401
        
        # Use Config method to properly parse admin emails
        admin_emails = Config.get_admin_emails()
        if current_user.email not in admin_emails:
            return jsonify({'error': 'Admin access required'}), 403
        
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# PUBLIC ENDPOINTS (Desktop client uses these)
# ============================================================================

@license_bp.route('/validate', methods=['POST'])
@limiter.limit("10 per minute")  # Rate limit to prevent brute force
def validate_license():
    """
    Validate a license key and hardware fingerprint
    
    Request:
        {
            "license_key": "FB-XXXX-XXXX-XXXX-XXXX",
            "hardware_fingerprint": "base64-encoded-hash"
        }
    
    Response:
        {
            "valid": true,
            "tier": "professional",
            "migrations_remaining": 45,
            "token": "eyJ..."  // JWT for offline caching
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'valid': False, 'error': 'No data provided'}), 400
        
        license_key = data.get('license_key', '').strip()
        hardware_fingerprint = data.get('hardware_fingerprint', '').strip()
        
        if not license_key:
            return jsonify({'valid': False, 'error': 'License key required'}), 400
        
        if not hardware_fingerprint:
            return jsonify({'valid': False, 'error': 'Hardware fingerprint required'}), 400
        
        # Find license
        license_obj = License.find_by_key(license_key)
        
        if not license_obj:
            logger.warning(f"License validation failed: key not found - {license_key[:15]}...")
            return jsonify({'valid': False, 'error': 'Invalid license key'}), 404
        
        # Validate license
        is_valid, error = license_obj.validate(hardware_fingerprint)
        
        if not is_valid:
            log_activation(license_obj, 'validate', hardware_fingerprint, False, error)
            db.session.commit()
            logger.warning(f"License validation failed: {error} - License ID {license_obj.id}")
            return jsonify({'valid': False, 'error': error}), 403
        
        # Generate token for offline caching
        token = generate_license_token(license_obj, hardware_fingerprint)
        
        # Log successful validation
        log_activation(license_obj, 'validate', hardware_fingerprint, True)
        db.session.commit()
        
        logger.info(f"License validated: ID {license_obj.id}, tier {license_obj.tier}")
        
        return jsonify({
            'valid': True,
            'tier': license_obj.tier,
            'tier_name': LICENSE_TIERS.get(license_obj.tier, {}).get('name', license_obj.tier),
            'migrations_remaining': license_obj.get_migrations_remaining(),
            'is_unlimited': license_obj.migrations_allowed == -1,
            'expires_at': license_obj.expires_at.isoformat() if license_obj.expires_at else None,
            'token': token
        })
        
    except Exception as e:
        logger.error(f"License validation error: {str(e)}")
        db.session.rollback()
        return jsonify({'valid': False, 'error': 'Validation failed'}), 500


@license_bp.route('/activate', methods=['POST'])
@limiter.limit("5 per minute")  # Stricter rate limit for activation
def activate_license():
    """
    Activate a license on specific hardware
    
    Request:
        {
            "license_key": "FB-XXXX-XXXX-XXXX-XXXX",
            "hardware_fingerprint": "base64-encoded-hash"
        }
    
    Response:
        {
            "success": true,
            "message": "License activated successfully"
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        license_key = data.get('license_key', '').strip()
        hardware_fingerprint = data.get('hardware_fingerprint', '').strip()
        
        if not license_key:
            return jsonify({'success': False, 'error': 'License key required'}), 400
        
        if not hardware_fingerprint:
            return jsonify({'success': False, 'error': 'Hardware fingerprint required'}), 400
        
        # Find license
        license_obj = License.find_by_key(license_key)
        
        if not license_obj:
            logger.warning(f"License activation failed: key not found - {license_key[:15]}...")
            return jsonify({'success': False, 'error': 'Invalid license key'}), 404
        
        # Check if license is valid (not revoked/expired)
        if license_obj.is_revoked:
            return jsonify({'success': False, 'error': 'License has been revoked'}), 403
        
        if license_obj.expires_at and datetime.utcnow() > license_obj.expires_at:
            return jsonify({'success': False, 'error': 'License has expired'}), 403
        
        # Try to activate
        success = license_obj.activate(hardware_fingerprint)
        
        if not success:
            log_activation(license_obj, 'activate', hardware_fingerprint, False, 
                          'License already activated on different hardware')
            db.session.commit()
            logger.warning(f"License activation failed: already activated elsewhere - ID {license_obj.id}")
            return jsonify({
                'success': False, 
                'error': 'License is already activated on another machine. Contact support to transfer.'
            }), 409
        
        db.session.commit()
        
        # Generate token
        token = generate_license_token(license_obj, hardware_fingerprint)
        
        logger.info(f"License activated: ID {license_obj.id} on hardware {hardware_fingerprint[:20]}...")
        
        return jsonify({
            'success': True,
            'message': 'License activated successfully',
            'tier': license_obj.tier,
            'migrations_remaining': license_obj.get_migrations_remaining(),
            'token': token
        })
        
    except Exception as e:
        logger.error(f"License activation error: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Activation failed'}), 500


@license_bp.route('/usage', methods=['POST'])
def get_usage():
    """
    Get license usage/remaining migrations
    
    Request:
        {
            "license_key": "FB-XXXX-XXXX-XXXX-XXXX",
            "hardware_fingerprint": "base64-encoded-hash"
        }
    
    Response:
        {
            "migrations_allowed": 50,
            "migrations_used": 5,
            "migrations_remaining": 45
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        license_key = data.get('license_key', '').strip()
        hardware_fingerprint = data.get('hardware_fingerprint', '').strip()
        
        if not license_key or not hardware_fingerprint:
            return jsonify({'error': 'License key and hardware fingerprint required'}), 400
        
        # Find and validate license
        license_obj = License.find_by_key(license_key)
        
        if not license_obj:
            return jsonify({'error': 'Invalid license key'}), 404
        
        is_valid, error = license_obj.validate(hardware_fingerprint)
        
        if not is_valid:
            return jsonify({'error': error}), 403
        
        return jsonify({
            'tier': license_obj.tier,
            'tier_name': LICENSE_TIERS.get(license_obj.tier, {}).get('name', license_obj.tier),
            'migrations_allowed': license_obj.migrations_allowed,
            'migrations_used': license_obj.migrations_used,
            'migrations_remaining': license_obj.get_migrations_remaining(),
            'is_unlimited': license_obj.migrations_allowed == -1,
            'expires_at': license_obj.expires_at.isoformat() if license_obj.expires_at else None
        })
        
    except Exception as e:
        logger.error(f"License usage check error: {str(e)}")
        return jsonify({'error': 'Failed to get usage'}), 500


@license_bp.route('/use-migration', methods=['POST'])
def use_migration():
    """
    Consume one migration from the license
    Called after successful migration completion
    
    Request:
        {
            "license_key": "FB-XXXX-XXXX-XXXX-XXXX",
            "hardware_fingerprint": "base64-encoded-hash",
            "migration_id": "uuid"
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        license_key = data.get('license_key', '').strip()
        hardware_fingerprint = data.get('hardware_fingerprint', '').strip()
        migration_id = data.get('migration_id', '')
        
        if not license_key or not hardware_fingerprint:
            return jsonify({'success': False, 'error': 'License key and hardware fingerprint required'}), 400
        
        # Find and validate license
        license_obj = License.find_by_key(license_key)
        
        if not license_obj:
            return jsonify({'success': False, 'error': 'Invalid license key'}), 404
        
        is_valid, error = license_obj.validate(hardware_fingerprint)
        
        if not is_valid:
            return jsonify({'success': False, 'error': error}), 403
        
        # Use migration
        if not license_obj.use_migration():
            return jsonify({'success': False, 'error': 'No migrations remaining'}), 403
        
        # Log usage
        log_activation(license_obj, 'use_migration', hardware_fingerprint, True, 
                      notes=f"Migration: {migration_id}")
        db.session.commit()
        
        logger.info(f"Migration used: License ID {license_obj.id}, remaining: {license_obj.get_migrations_remaining()}")
        
        return jsonify({
            'success': True,
            'migrations_remaining': license_obj.get_migrations_remaining()
        })
        
    except Exception as e:
        logger.error(f"Use migration error: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Failed to use migration'}), 500


# ============================================================================
# ADMIN ENDPOINTS (Require authentication)
# ============================================================================

@license_bp.route('/create', methods=['POST'])
@login_required
@admin_required
def create_license():
    """
    Create a new license (admin only)
    
    Request:
        {
            "tier": "professional",
            "user_email": "customer@example.com",
            "order_id": "ORDER-123",
            "expires_in_days": 365  // optional
        }
    """
    try:
        data = request.get_json()
        
        tier = data.get('tier', 'starter')
        user_email = data.get('user_email')
        order_id = data.get('order_id')
        expires_in_days = data.get('expires_in_days')
        
        # Create license
        license_obj = License.create_license(
            tier=tier,
            user_email=user_email,
            order_id=order_id,
            expires_in_days=expires_in_days
        )
        
        db.session.add(license_obj)
        db.session.commit()
        
        # FIX #53: Redact PII from logs
        logger.info(f"License created: {license_obj.license_key} ({tier}) by {hash_email(current_user.email)}")
        
        return jsonify({
            'success': True,
            'license': license_obj.to_dict(include_sensitive=True)
        }), 201
        
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Create license error: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Failed to create license'}), 500


@license_bp.route('/deactivate', methods=['POST'])
@login_required
@admin_required
def deactivate_license():
    """
    Deactivate a license to allow transfer (admin only)
    
    Request:
        {
            "license_key": "FB-XXXX-XXXX-XXXX-XXXX",
            "reason": "Customer requested transfer"
        }
    """
    try:
        data = request.get_json()
        
        license_key = data.get('license_key', '').strip()
        reason = data.get('reason', 'Admin deactivation')
        
        if not license_key:
            return jsonify({'success': False, 'error': 'License key required'}), 400
        
        license_obj = License.find_by_key(license_key)
        
        if not license_obj:
            return jsonify({'success': False, 'error': 'License not found'}), 404
        
        license_obj.deactivate(reason=reason, admin_email=current_user.email)
        db.session.commit()
        
        # FIX #53: Redact PII from logs
        logger.info(f"License deactivated: {license_key[:15]}... by {hash_email(current_user.email)}")
        
        return jsonify({
            'success': True,
            'message': 'License deactivated. Customer can now activate on new hardware.'
        })
        
    except Exception as e:
        logger.error(f"Deactivate license error: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Failed to deactivate license'}), 500


@license_bp.route('/revoke', methods=['POST'])
@login_required
@admin_required
def revoke_license():
    """
    Permanently revoke a license (admin only)
    
    Request:
        {
            "license_key": "FB-XXXX-XXXX-XXXX-XXXX",
            "reason": "Chargeback"
        }
    """
    try:
        data = request.get_json()
        
        license_key = data.get('license_key', '').strip()
        reason = data.get('reason', 'Revoked by admin')
        
        if not license_key:
            return jsonify({'success': False, 'error': 'License key required'}), 400
        
        license_obj = License.find_by_key(license_key)
        
        if not license_obj:
            return jsonify({'success': False, 'error': 'License not found'}), 404
        
        license_obj.revoke(reason=reason, revoked_by=current_user.email)
        db.session.commit()
        
        # FIX #53: Redact PII from logs
        logger.warning(f"License revoked: {license_key[:15]}... by {hash_email(current_user.email)}: {reason}")
        
        return jsonify({
            'success': True,
            'message': 'License has been permanently revoked'
        })
        
    except Exception as e:
        logger.error(f"Revoke license error: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Failed to revoke license'}), 500


@license_bp.route('/list', methods=['GET'])
@login_required
@admin_required
def list_licenses():
    """List all licenses (admin only)"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        tier = request.args.get('tier')
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        
        query = License.query
        
        if tier:
            query = query.filter_by(tier=tier)
        
        if active_only:
            query = query.filter_by(is_active=True, is_revoked=False)
        
        query = query.order_by(License.created_at.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return jsonify({
            'licenses': [l.to_dict(include_sensitive=True) for l in pagination.items],
            'total': pagination.total,
            'page': page,
            'pages': pagination.pages
        })
        
    except Exception as e:
        logger.error(f"List licenses error: {str(e)}")
        return jsonify({'error': 'Failed to list licenses'}), 500


@license_bp.route('/<int:license_id>/history', methods=['GET'])
@login_required
@admin_required
def get_license_history(license_id):
    """Get activation history for a license (admin only)"""
    try:
        license_obj = License.query.get_or_404(license_id)
        
        activations = LicenseActivation.query.filter_by(license_id=license_id)\
            .order_by(LicenseActivation.created_at.desc())\
            .limit(100)\
            .all()
        
        return jsonify({
            'license': license_obj.to_dict(include_sensitive=True),
            'history': [a.to_dict() for a in activations]
        })
        
    except Exception as e:
        logger.error(f"Get license history error: {str(e)}")
        return jsonify({'error': 'Failed to get history'}), 500
