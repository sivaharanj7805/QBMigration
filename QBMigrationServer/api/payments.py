"""
Payments API - Stripe integration for purchasing migration credits.
Handles checkout session creation and webhook verification.
"""

import os
import stripe
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from functools import wraps
import jwt

from models.database import db
from models.user import User
from models.migration_credit import MigrationCredit

logger = logging.getLogger(__name__)

payments_bp = Blueprint('payments', __name__, url_prefix='/api/payments')

# Initialize Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')


def token_required(f):
    """Decorator to require valid JWT token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({'success': False, 'error': 'Token is missing'}), 401
        
        try:
            secret_key = current_app.config.get('SECRET_KEY', 'dev-secret-key')
            data = jwt.decode(token, secret_key, algorithms=['HS256'])
            current_user = User.query.get(data['user_id'])
            
            if not current_user:
                return jsonify({'success': False, 'error': 'User not found'}), 401
            
            if not current_user.is_active:
                return jsonify({'success': False, 'error': 'Account is disabled'}), 403
                
        except jwt.ExpiredSignatureError:
            return jsonify({'success': False, 'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'success': False, 'error': 'Invalid token'}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated


@payments_bp.route('/create-checkout', methods=['POST'])
@token_required
def create_checkout(current_user):
    """
    Create a Stripe Checkout session for purchasing a migration credit.
    Returns a checkout URL that the frontend should redirect to.
    """
    try:
        data = request.get_json()
        tier_type = data.get('tier_type')
        
        if not tier_type:
            return jsonify({'success': False, 'error': 'tier_type is required'}), 400
        
        # Validate tier type
        tier_config = MigrationCredit.get_tier_config(tier_type)
        if not tier_config:
            return jsonify({'success': False, 'error': f'Invalid tier type: {tier_type}'}), 400
        
        # Check if Stripe is configured
        if not stripe.api_key:
            return jsonify({
                'success': False, 
                'error': 'Payment system not configured. Please contact support.'
            }), 503
        
        # Get or create Stripe customer
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                name=f"{current_user.first_name} {current_user.last_name}".strip() or current_user.email,
                metadata={
                    'user_id': current_user.id,
                    'company': current_user.company_name or ''
                }
            )
            current_user.stripe_customer_id = customer.id
            db.session.commit()
        
        # Build URLs
        base_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
        success_url = f"{base_url}/payment-success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{base_url}/select-tier?cancelled=true"
        
        # Create Checkout Session
        checkout_session = stripe.checkout.Session.create(
            customer=current_user.stripe_customer_id,
            payment_method_types=['card'],
            mode='payment',
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': f'{tier_config["name"]} Migration',
                        'description': f'{tier_config["description"]} - One-time purchase',
                        'metadata': {
                            'tier_type': tier_type
                        }
                    },
                    'unit_amount': tier_config['price_cents']
                },
                'quantity': 1
            }],
            metadata={
                'user_id': str(current_user.id),
                'tier_type': tier_type,
                'transaction_limit': str(tier_config['transaction_limit'])
            },
            success_url=success_url,
            cancel_url=cancel_url,
            expires_at=int(datetime.utcnow().timestamp()) + 1800  # 30 minutes
        )
        
        # Create pending credit (will be activated by webhook)
        credit = MigrationCredit.create_pending(
            user_id=current_user.id,
            tier_type=tier_type,
            stripe_checkout_session_id=checkout_session.id
        )
        
        logger.info(f"Created checkout session {checkout_session.id} for user {current_user.id}, tier {tier_type}")
        
        return jsonify({
            'success': True,
            'checkout_url': checkout_session.url,
            'session_id': checkout_session.id
        })
        
    except stripe.error.StripeError as e:
        # CRITICAL FIX: Sanitize Stripe errors before returning to client
        # Raw Stripe errors can leak internal configuration details (API keys, account info)
        logger.error(f"Stripe error for user {current_user.id}: {str(e)}")

        # Map Stripe error types to safe user-facing messages
        safe_error_messages = {
            stripe.error.CardError: "Your card was declined. Please try a different payment method.",
            stripe.error.RateLimitError: "Payment system is busy. Please try again in a moment.",
            stripe.error.InvalidRequestError: "Invalid payment request. Please try again.",
            stripe.error.AuthenticationError: "Payment system configuration error. Please contact support.",
            stripe.error.APIConnectionError: "Unable to connect to payment system. Please try again.",
            stripe.error.StripeError: "Payment processing failed. Please try again or contact support."
        }

        # Get the most specific safe error message
        safe_message = safe_error_messages.get(
            type(e),
            safe_error_messages[stripe.error.StripeError]
        )

        # For CardError, we can safely include the decline reason
        if isinstance(e, stripe.error.CardError):
            decline_code = getattr(e, 'decline_code', None)
            if decline_code == 'insufficient_funds':
                safe_message = "Insufficient funds. Please try a different payment method."
            elif decline_code == 'expired_card':
                safe_message = "Your card has expired. Please use a different card."

        return jsonify({'success': False, 'error': safe_message}), 400
    except Exception as e:
        logger.exception(f"Payment error for user {current_user.id}: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to create checkout session'}), 500


@payments_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    """
    Handle Stripe webhooks.
    Verifies payment and activates migration credits.
    """
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
    
    if not webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        return jsonify({'error': 'Webhook not configured'}), 500
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        # CRIT-03 FIX: Return 400 for invalid payloads (malformed JSON)
        logger.error(f"Invalid payload: {str(e)}")
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError as e:
        # CRIT-03 FIX: Return 400 for invalid signatures to reject forged webhooks
        # Stripe will NOT retry on 4xx errors, which is correct for security violations
        logger.error(f"SECURITY: Invalid Stripe signature from {request.remote_addr}")
        return jsonify({'error': 'Invalid signature'}), 400
    
    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_successful_payment(session)
    
    elif event['type'] == 'checkout.session.expired':
        session = event['data']['object']
        handle_expired_session(session)
    
    elif event['type'] == 'payment_intent.payment_failed':
        payment_intent = event['data']['object']
        handle_failed_payment(payment_intent)
    
    return jsonify({'received': True})


def handle_successful_payment(session):
    """Process a successful checkout session"""
    try:
        checkout_session_id = session['id']
        payment_intent_id = session.get('payment_intent')
        
        # Find the pending credit
        credit = MigrationCredit.query.filter_by(
            stripe_checkout_session_id=checkout_session_id
        ).first()
        
        if not credit:
            logger.error(f"No credit found for session {checkout_session_id}")
            return
        
        # Already processed?
        if credit.payment_status == 'paid':
            logger.info(f"Credit {credit.id} already marked as paid")
            return
        
        # CRITICAL FIX: Wrap in transaction to prevent partial updates
        try:
            db.session.begin_nested()  # Start savepoint

            # Mark as paid and available
            credit.mark_paid(payment_intent_id)

            # Update user's subscription tier and sync migration counts
            user = User.query.get(credit.user_id)
            if user:
                # Always update tier to reflect most recent purchase
                if not user.subscription_tier:
                    user.subscription_tier = credit.tier_type
                    user.tier_purchased_at = datetime.utcnow()

                # CRITICAL FIX: Sync User.migrations_purchased with MigrationCredit count
                # This ensures backwards compatibility with code that reads from User model
                # The MigrationCredit table is the source of truth, but we keep User in sync
                user.migrations_purchased = (user.migrations_purchased or 0) + 1

            db.session.commit()  # Commit both changes atomically

        except Exception as e:
            db.session.rollback()
            logger.error(f"Transaction failed for credit {credit.id}: {str(e)}")
            raise
        
        logger.info(f"Payment successful: Credit {credit.id} activated for user {credit.user_id}")
        
    except Exception as e:
        logger.exception(f"Error processing successful payment: {str(e)}")


def handle_expired_session(session):
    """Handle expired checkout session"""
    try:
        checkout_session_id = session['id']
        
        credit = MigrationCredit.query.filter_by(
            stripe_checkout_session_id=checkout_session_id
        ).first()
        
        if credit and credit.status == 'pending':
            credit.mark_failed()
            logger.info(f"Credit {credit.id} expired (session timeout)")
            
    except Exception as e:
        logger.exception(f"Error processing expired session: {str(e)}")


def handle_failed_payment(payment_intent):
    """Handle failed payment"""
    try:
        payment_intent_id = payment_intent['id']
        
        # Find credit by payment intent
        credit = MigrationCredit.query.filter_by(
            stripe_payment_intent_id=payment_intent_id
        ).first()
        
        if credit:
            credit.mark_failed()
            logger.info(f"Credit {credit.id} marked as failed")
            
    except Exception as e:
        logger.exception(f"Error processing failed payment: {str(e)}")


@payments_bp.route('/credits', methods=['GET'])
@token_required
def get_credits(current_user):
    """
    Get all migration credits for the current user.
    Returns breakdown by type and total available.
    """
    try:
        # Get summary by type
        summary = MigrationCredit.get_credits_summary(current_user.id)
        
        # Get all credits for details
        all_credits = MigrationCredit.query.filter_by(
            user_id=current_user.id
        ).filter(
            MigrationCredit.payment_status == 'paid'
        ).order_by(MigrationCredit.created_at.desc()).all()
        
        # Calculate totals
        total_available = sum(t['available'] for t in summary.values())
        total_used = sum(t['used'] for t in summary.values())
        
        return jsonify({
            'success': True,
            'credits': {
                'by_type': summary,
                'total_available': total_available,
                'total_used': total_used,
                'all_credits': [c.to_dict() for c in all_credits]
            }
        })
        
    except Exception as e:
        logger.exception(f"Error getting credits: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get credits'}), 500


@payments_bp.route('/verify-session/<session_id>', methods=['GET'])
@token_required
def verify_session(current_user, session_id):
    """
    Verify a checkout session after redirect.
    Frontend calls this to confirm payment was successful.
    """
    try:
        # Find the credit
        credit = MigrationCredit.query.filter_by(
            stripe_checkout_session_id=session_id,
            user_id=current_user.id
        ).first()
        
        if not credit:
            return jsonify({'success': False, 'error': 'Session not found'}), 404
        
        # If still pending, check with Stripe
        if credit.status == 'pending':
            session = stripe.checkout.Session.retrieve(session_id)
            
            if session.payment_status == 'paid':
                credit.mark_paid(session.payment_intent)
        
        return jsonify({
            'success': True,
            'credit': credit.to_dict(),
            'is_paid': credit.payment_status == 'paid'
        })
        
    except Exception as e:
        logger.exception(f"Error verifying session: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to verify session'}), 500


@payments_bp.route('/tiers', methods=['GET'])
def get_tiers():
    """Get all available pricing tiers (public endpoint)"""
    tiers = []
    for tier_id, config in MigrationCredit.TIER_CONFIG.items():
        tiers.append({
            'id': tier_id,
            'name': config['name'],
            'price': config['price_cents'] / 100,  # Convert to dollars
            'price_cents': config['price_cents'],
            'max_transactions': config['transaction_limit'],
            'description': config['description'],
            'migrations': 1  # Each purchase is 1 migration
        })
    
    # Sort by price
    tiers.sort(key=lambda x: x['price'])
    
    return jsonify({
        'success': True,
        'tiers': tiers
    })
