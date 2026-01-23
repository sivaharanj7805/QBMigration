"""
ForensicBridge Authentication API
JWT-based authentication for dashboard users with full security features
Compatible with models/user.py User model
"""

from flask import Blueprint, request, jsonify, current_app, session
from functools import wraps
import jwt
import datetime
import re
from typing import Optional, Tuple

from models.database import db
from models.user import User
from extensions import limiter

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


def create_token(user_id: int, email: str, expires_hours: int = 24) -> str:
    """Create a JWT token for a user"""
    payload = {
        'user_id': user_id,
        'email': email,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=expires_hours),
        'iat': datetime.datetime.utcnow()
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token"""
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def require_auth(f):
    """Decorator to require authentication for an endpoint (supports both JWT and session)"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Check for JWT token in Authorization header
        auth_header = request.headers.get('Authorization')
        
        if auth_header:
            try:
                # Expect "Bearer <token>"
                parts = auth_header.split()
                if len(parts) != 2 or parts[0].lower() != 'bearer':
                    return jsonify({'success': False, 'error': 'Invalid authorization format'}), 401
                
                token = parts[1]
                payload = decode_token(token)
                
                if not payload:
                    return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
                
                # Add user info to request
                request.current_user = payload
                return f(*args, **kwargs)
                
            except Exception as e:
                return jsonify({'success': False, 'error': 'Authentication failed'}), 401
        
        # Check for session-based auth
        if 'user_id' in session:
            request.current_user = {
                'user_id': session['user_id'],
                'email': session.get('email', '')
            }
            return f(*args, **kwargs)
        
        return jsonify({'success': False, 'error': 'No authorization provided'}), 401
    return decorated


def validate_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_password(password: str) -> Tuple[bool, str]:
    """Validate password strength"""
    if len(password) < 8:
        return False, 'Password must be at least 8 characters'
    if not re.search(r'[A-Z]', password):
        return False, 'Password must contain at least one uppercase letter'
    if not re.search(r'[a-z]', password):
        return False, 'Password must contain at least one lowercase letter'
    if not re.search(r'\d', password):
        return False, 'Password must contain at least one digit'
    return True, ''


@auth_bp.route('/register', methods=['POST'])
@limiter.limit("5 per minute")
def register():
    """Register a new user with comprehensive error handling"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        # Extract and sanitize inputs
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        # Support both 'first_name' and 'name' from frontend
        first_name = data.get('first_name', data.get('name', '')).strip()
        last_name = data.get('last_name', '').strip()
        # Support both 'company_name' and 'company' from frontend
        company = data.get('company_name', data.get('company', '')).strip()
        
        # Sanitize inputs - remove potentially dangerous characters
        import re
        def sanitize(value, max_length=255):
            if not value:
                return value
            value = re.sub(r'[<>"\'/\\;]', '', str(value).strip())
            return value[:max_length]
        
        first_name = sanitize(first_name, 100)
        last_name = sanitize(last_name, 100)
        company = sanitize(company, 255)
        
        # Validation
        if not email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400
        
        if not password:
            return jsonify({'success': False, 'error': 'Password is required'}), 400
        
        if not validate_email(email):
            return jsonify({'success': False, 'error': 'Invalid email format'}), 400
        
        # Validate password strength BEFORE creating user
        valid, msg = validate_password(password)
        if not valid:
            return jsonify({'success': False, 'error': msg}), 400
        
        # Check if user exists
        existing = User.query.filter_by(email=email).first()
        if existing:
            return jsonify({'success': False, 'error': 'Email already registered'}), 409
        
        # Create user
        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            company_name=company
        )
        
        # Set password - this may raise ValueError for strength/reuse issues
        try:
            user.set_password(password)
        except ValueError as e:
            logger.warning(f"Password validation failed for {email}: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 400
        
        # Save to database
        db.session.add(user)
        db.session.commit()
        
        # Create session
        session['user_id'] = user.id
        session['email'] = user.email
        
        # Generate token
        token = create_token(user.id, user.email)
        
        logger.info(f"New user registered: {email}")
        
        return jsonify({
            'success': True,
            'token': token,
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'company_name': user.company_name
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.exception(f"Registration error: {str(e)}")
        return jsonify({'success': False, 'error': 'Registration failed. Please try again.'}), 500


@auth_bp.route('/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    """Login and get JWT token"""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({'success': False, 'error': 'Email and password required'}), 400
    
    # Find user
    user = User.query.filter_by(email=email).first()
    
    # Check if user exists (constant-time comparison to prevent enumeration)
    if not user:
        # Still check a fake password to prevent timing attacks
        from argon2 import PasswordHasher
        ph = PasswordHasher()
        try:
            ph.verify("$argon2id$v=19$m=65536,t=3,p=4$dummy$dummyhash", password)
        except:
            pass
        return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
    
    # Check if account is locked
    if user.is_locked():
        return jsonify({
            'success': False, 
            'error': 'Account is locked due to too many failed attempts. Please try again later.'
        }), 401
    
    # Verify password
    if not user.check_password(password):
        # Track failed attempt
        user.record_failed_login()
        db.session.commit()
        
        # Check if now locked
        if user.failed_login_attempts >= 5:
            return jsonify({
                'success': False,
                'error': 'Account is locked due to too many failed attempts. Please try again later.'
            }), 401
        
        return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
    
    # Successful login
    user.record_successful_login()
    db.session.commit()
    
    # Create session
    session['user_id'] = user.id
    session['email'] = user.email
    
    # Generate token
    token = create_token(user.id, user.email)
    
    return jsonify({
        'success': True,
        'token': token,
        'user': {
            'id': user.id,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'company_name': user.company_name
        }
    })


@auth_bp.route('/me', methods=['GET'])
@require_auth
def get_current_user():
    """Get current user info including tier and migration balance"""
    user_id = request.current_user['user_id']
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    # Get tier info - use try/except in case DB columns don't exist yet
    try:
        tier_info = user.get_tier_info()
    except Exception as e:
        # Fallback if tier columns don't exist in database
        import logging
        logging.getLogger(__name__).warning(f"Could not get tier info: {e}")
        tier_info = {
            'tier': 'none',
            'tier_name': 'Free Trial',
            'migrations_remaining': 0,
            'migrations_purchased': 0,
            'migrations_used': 0,
            'has_tier': False
        }
    
    # Get migration credits breakdown by type
    try:
        from models.migration_credit import MigrationCredit
        credits_summary = MigrationCredit.get_credits_summary(user.id)
        
        # Calculate totals from credits
        total_available = sum(t.get('available', 0) for t in credits_summary.values())
        total_used = sum(t.get('used', 0) for t in credits_summary.values())
        has_credits = total_available > 0
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Could not get credits summary: {e}")
        credits_summary = {}
        total_available = tier_info['migrations_remaining']
        total_used = tier_info['migrations_used']
        has_credits = total_available > 0
    
    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'name': user.first_name,  # Alias for frontend compatibility
            'company_name': user.company_name,
            'created_at': user.created_at.isoformat() if user.created_at else None,
            # Legacy tier info (for backward compatibility)
            'subscription_tier': tier_info['tier'],
            'tier_name': tier_info['tier_name'],
            'migrations_remaining': total_available,
            'migrations_purchased': total_available + total_used,
            'migrations_used': total_used,
            'has_tier': has_credits or tier_info['has_tier'],
            # New: Credits breakdown by type
            'migration_credits': credits_summary,
            'total_credits_available': total_available,
            'total_credits_used': total_used
        }
    })


@auth_bp.route('/refresh', methods=['POST'])
@require_auth
def refresh_token():
    """Refresh JWT token"""
    user_id = request.current_user['user_id']
    email = request.current_user['email']
    
    token = create_token(user_id, email)
    
    return jsonify({
        'success': True,
        'token': token
    })


@auth_bp.route('/logout', methods=['POST'])
@require_auth
def logout():
    """Logout - clears session"""
    # Clear session
    session.pop('user_id', None)
    session.pop('email', None)
    session.clear()
    
    return jsonify({'success': True})


# =============================================================================
# TIER SELECTION & MANAGEMENT
# =============================================================================

@auth_bp.route('/tiers', methods=['GET'])
def get_available_tiers():
    """Get all available pricing tiers"""
    tiers = [
        {
            'id': 'starter',
            'name': 'Starter',
            'price': 497,
            'max_transactions': 5000,
            'description': 'Small business, 1-2 years of data',
            'migrations': 1
        },
        {
            'id': 'business',
            'name': 'Business',
            'price': 997,
            'max_transactions': 25000,
            'description': 'Established business, 3-5 years of history',
            'migrations': 1
        },
        {
            'id': 'professional',
            'name': 'Professional',
            'price': 1997,
            'max_transactions': 100000,
            'description': 'Complex business, multi-year audit trail',
            'migrations': 1
        },
        {
            'id': 'enterprise',
            'name': 'Enterprise',
            'price': 3997,
            'max_transactions': 500000,
            'description': 'Large company, decade+ of records',
            'migrations': 1
        },
        {
            'id': 'forensic',
            'name': 'Forensic',
            'price': 7997,
            'max_transactions': -1,
            'description': 'Litigation-ready, expert documentation',
            'migrations': 1
        }
    ]
    return jsonify({'success': True, 'tiers': tiers})


@auth_bp.route('/select-tier', methods=['POST'])
@require_auth
def select_tier():
    """
    Select/purchase a tier after registration.
    In production, this would integrate with Stripe Checkout.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    tier_id = data.get('tier_id', '').lower()
    
    # Validate tier
    valid_tiers = ['starter', 'business', 'professional', 'enterprise', 'forensic']
    if tier_id not in valid_tiers:
        return jsonify({'success': False, 'error': f'Invalid tier: {tier_id}'}), 400
    
    user_id = request.current_user['user_id']
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    # Get tier config
    tier_config = User.TIER_CONFIG.get(tier_id, {})
    migrations_to_add = tier_config.get('migrations', 1)
    
    # In production: Create Stripe Checkout session here
    # For now, we'll simulate successful payment
    
    # Add migrations and set tier
    user.add_migrations(migrations_to_add, tier=tier_id)
    db.session.commit()
    
    logger.info(f"User {user.email} selected tier {tier_id} with {migrations_to_add} migration(s)")
    
    return jsonify({
        'success': True,
        'message': f'Successfully selected {tier_config.get("name", tier_id)} tier',
        'tier': tier_id,
        'migrations_remaining': user.get_migrations_remaining(),
        # In production: return Stripe checkout URL
        'payment_required': True,
        'checkout_url': None  # Would be Stripe checkout URL
    })


@auth_bp.route('/upgrade-tier', methods=['POST'])
@require_auth
def upgrade_tier():
    """Upgrade to a higher tier (adds more migrations)"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    tier_id = data.get('tier_id', '').lower()
    
    valid_tiers = ['starter', 'business', 'professional', 'enterprise', 'forensic']
    if tier_id not in valid_tiers:
        return jsonify({'success': False, 'error': f'Invalid tier: {tier_id}'}), 400
    
    user_id = request.current_user['user_id']
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    tier_config = User.TIER_CONFIG.get(tier_id, {})
    migrations_to_add = tier_config.get('migrations', 1)
    
    # Add migrations and update tier
    user.add_migrations(migrations_to_add, tier=tier_id)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Successfully upgraded to {tier_config.get("name", tier_id)}',
        'tier': tier_id,
        'migrations_remaining': user.get_migrations_remaining()
    })


# =============================================================================
# TEAM MANAGEMENT
# =============================================================================

@auth_bp.route('/team', methods=['GET'])
@require_auth
def list_team_members():
    """List team members and pending invites"""
    user_id = request.current_user['user_id']
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    try:
        from models.team_invite import TeamInvite
        
        # Get team members (accepted invites)
        team_members = TeamInvite.get_team_members(user_id)
        
        # Add the owner as first member
        owner_member = {
            'id': user.id,
            'email': user.email,
            'name': f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email.split('@')[0],
            'role': 'Owner',
            'joined_at': user.created_at.isoformat() if user.created_at else None
        }
        
        # Get pending invites
        pending = TeamInvite.get_pending_for_owner(user_id)
        pending_invites = [invite.to_dict() for invite in pending]
        
        return jsonify({
            'success': True,
            'team_members': [owner_member] + team_members,
            'pending_invites': pending_invites
        })
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Team fetch error (table may not exist): {e}")
        # Fallback if table doesn't exist
        return jsonify({
            'success': True,
            'team_members': [
                {
                    'id': user.id,
                    'email': user.email,
                    'name': f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email.split('@')[0],
                    'role': 'Owner',
                    'joined_at': user.created_at.isoformat() if user.created_at else None
                }
            ],
            'pending_invites': []
        })


@auth_bp.route('/team/invite', methods=['POST'])
@require_auth
def invite_team_member():
    """Invite a new team member"""
    import logging
    logger = logging.getLogger(__name__)
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    email = data.get('email', '').strip().lower()
    role = data.get('role', 'member')
    
    if not email:
        return jsonify({'success': False, 'error': 'Email is required'}), 400
    
    user_id = request.current_user['user_id']
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    # Check if user has Enterprise tier (required for team features)
    tier = getattr(user, 'subscription_tier', None)
    if tier not in ['enterprise', 'forensic']:
        return jsonify({
            'success': False,
            'error': 'Team management requires Enterprise or Forensic tier. Please upgrade your plan.'
        }), 403
    
    # Check if email is already a team member or has pending invite
    try:
        from models.team_invite import TeamInvite
        
        # Check for existing pending invite
        existing = TeamInvite.query.filter_by(
            owner_user_id=user_id,
            email=email,
            status='pending'
        ).first()
        
        if existing:
            return jsonify({
                'success': False,
                'error': f'An invitation is already pending for {email}'
            }), 400
        
        # Check if user is inviting themselves
        if email == user.email:
            return jsonify({
                'success': False,
                'error': 'You cannot invite yourself'
            }), 400
        
        # Create the invite
        invite = TeamInvite.create_invite(
            owner_user_id=user_id,
            email=email,
            role=role
        )
        
        logger.info(f"Team invite created: {email} invited by {user.email} as {role}")
        
        # TODO: Send email notification
        # In production, this would send an email with the invite link
        # Example: send_invite_email(email, invite.invite_token, user.email)
        
        return jsonify({
            'success': True,
            'message': f'Invitation sent to {email}',
            'invite': invite.to_dict()
        })
        
    except Exception as e:
        logger.exception(f"Failed to create team invite: {e}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Failed to send invitation. Please try again.'
        }), 500


@auth_bp.route('/team/invite/<int:invite_id>', methods=['DELETE'])
@require_auth
def cancel_team_invite(invite_id):
    """Cancel a pending team invite"""
    user_id = request.current_user['user_id']
    
    try:
        from models.team_invite import TeamInvite
        
        invite = TeamInvite.query.filter_by(
            id=invite_id,
            owner_user_id=user_id
        ).first()
        
        if not invite:
            return jsonify({'success': False, 'error': 'Invite not found'}), 404
        
        if invite.status != 'pending':
            return jsonify({'success': False, 'error': 'Can only cancel pending invites'}), 400
        
        invite.cancel()
        
        return jsonify({
            'success': True,
            'message': 'Invitation cancelled'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500