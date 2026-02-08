"""
Payments API - Stripe integration for purchasing migration credits.
Handles checkout session creation and webhook verification.
"""

import logging
import os
from datetime import datetime, timezone

import stripe
from flask import Blueprint, current_app, jsonify, request
from models.database import db
from models.migration_credit import MigrationCredit
from models.user import User

# HIGH-06 FIX: Import shared auth decorator instead of maintaining a duplicate.
# This ensures auth policy changes (e.g., JTI revocation, algorithm updates)
# automatically apply to payment endpoints.
from api.auth import require_auth

logger = logging.getLogger(__name__)

payments_bp = Blueprint("payments", __name__, url_prefix="/api/payments")


def _get_stripe():
    """HIGH-09 FIX: Lazy-load Stripe API key to support key rotation without restart."""
    key = os.getenv("STRIPE_SECRET_KEY") or current_app.config.get("STRIPE_SECRET_KEY")
    if not key:
        raise ValueError("STRIPE_SECRET_KEY not configured")
    stripe.api_key = key
    return stripe


def _get_current_user():
    """HIGH-06 helper: Resolve User model from request.current_user (set by require_auth)."""
    user_id = request.current_user.get("user_id")
    user = db.session.get(User, user_id)
    if not user:
        return None
    return user


@payments_bp.route("/create-checkout", methods=["POST"])
@require_auth
def create_checkout():
    """
    Create a Stripe Checkout session for purchasing a migration credit.
    Returns a checkout URL that the frontend should redirect to.
    """
    try:
        current_user = _get_current_user()
        if not current_user:
            return jsonify({"success": False, "error": "User not found"}), 401

        data = request.get_json()
        tier_type = data.get("tier_type")

        if not tier_type:
            return jsonify({"success": False, "error": "tier_type is required"}), 400

        # Validate tier type
        tier_config = MigrationCredit.get_tier_config(tier_type)
        if not tier_config:
            return (
                jsonify({"success": False, "error": f"Invalid tier type: {tier_type}"}),
                400,
            )

        # HIGH-09 FIX: Lazy-load Stripe key (supports rotation without restart)
        try:
            _get_stripe()
        except ValueError:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Payment system not configured. Please contact support.",
                    }
                ),
                503,
            )

        # Get or create Stripe customer
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                name=f"{current_user.first_name} {current_user.last_name}".strip()
                or current_user.email,
                metadata={
                    "user_id": current_user.id,
                    "company": current_user.company_name or "",
                },
            )
            current_user.stripe_customer_id = customer.id
            db.session.commit()

        # Build URLs
        base_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        success_url = f"{base_url}/payment-success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{base_url}/select-tier?cancelled=true"

        # Create Checkout Session
        checkout_session = stripe.checkout.Session.create(
            customer=current_user.stripe_customer_id,
            payment_method_types=["card"],
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": f'{tier_config["name"]} Migration',
                            "description": f'{tier_config["description"]} - One-time purchase',
                            "metadata": {"tier_type": tier_type},
                        },
                        "unit_amount": tier_config["price_cents"],
                    },
                    "quantity": 1,
                }
            ],
            metadata={
                "user_id": str(current_user.id),
                "tier_type": tier_type,
                "transaction_limit": str(tier_config["transaction_limit"]),
            },
            success_url=success_url,
            cancel_url=cancel_url,
            expires_at=int(datetime.now(timezone.utc).timestamp()) + 1800,  # 30 minutes
        )

        # Create pending credit (will be activated by webhook)
        _ = MigrationCredit.create_pending(
            user_id=current_user.id,
            tier_type=tier_type,
            stripe_checkout_session_id=checkout_session.id,
        )

        logger.info(
            f"Created checkout session {checkout_session.id} for user {current_user.id}, tier {tier_type}"
        )

        return jsonify(
            {
                "success": True,
                "checkout_url": checkout_session.url,
                "session_id": checkout_session.id,
            }
        )

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
            stripe.error.StripeError: "Payment processing failed. Please try again or contact support.",
        }

        # Get the most specific safe error message
        safe_message = safe_error_messages.get(
            type(e), safe_error_messages[stripe.error.StripeError]
        )

        # For CardError, we can safely include the decline reason
        if isinstance(e, stripe.error.CardError):
            decline_code = getattr(e, "decline_code", None)
            if decline_code == "insufficient_funds":
                safe_message = (
                    "Insufficient funds. Please try a different payment method."
                )
            elif decline_code == "expired_card":
                safe_message = "Your card has expired. Please use a different card."

        return jsonify({"success": False, "error": safe_message}), 400
    except Exception as e:
        # FIX: Sanitize exception message before logging to avoid card details
        # Remove potential card numbers, CVVs, and other sensitive payment info
        import re

        error_str = str(e)
        # Redact card numbers (13-19 digits, optionally with spaces/dashes)
        error_str = re.sub(
            r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{1,7}\b",
            "[CARD_REDACTED]",
            error_str,
        )
        # Redact CVV/CVC (3-4 digit codes)
        error_str = re.sub(
            r"\b(cvv|cvc|cvn|security[\s_]?code)[\s:=]*\d{3,4}\b",
            r"\1=[REDACTED]",
            error_str,
            flags=re.IGNORECASE,
        )
        # Redact expiry dates in various formats (MM/YY, MM/YYYY, MMYY, etc.)
        error_str = re.sub(
            r"\b(exp|expir[ey]|expiration)[\s:=]*\d{2}[/\-]?\d{2,4}\b",
            r"\1=[REDACTED]",
            error_str,
            flags=re.IGNORECASE,
        )
        logger.exception(
            f"Payment error for user {current_user.id}: {type(e).__name__}: {error_str}"
        )
        return (
            jsonify({"success": False, "error": "Failed to create checkout session"}),
            500,
        )


@payments_bp.route("/webhook", methods=["POST"])
def stripe_webhook():
    """
    Handle Stripe webhooks.
    Verifies payment and activates migration credits.
    """
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        return jsonify({"error": "Webhook not configured"}), 500

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError as e:
        # CRIT-03 FIX: Return 400 for invalid payloads (malformed JSON)
        logger.error(f"Invalid payload: {str(e)}")
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError:
        # CRIT-03 FIX: Return 400 for invalid signatures to reject forged webhooks
        # Stripe will NOT retry on 4xx errors, which is correct for security violations
        logger.error(f"SECURITY: Invalid Stripe signature from {request.remote_addr}")
        return jsonify({"error": "Invalid signature"}), 400

    # FIX B-05: Handle events with proper error propagation
    # Return 500 on critical failures so Stripe retries the webhook
    try:
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            handle_successful_payment(session)

        elif event["type"] == "checkout.session.expired":
            session = event["data"]["object"]
            handle_expired_session(session)

        elif event["type"] == "payment_intent.payment_failed":
            payment_intent = event["data"]["object"]
            handle_failed_payment(payment_intent)

    except Exception as handler_err:
        logger.exception(
            f"Failed to handle Stripe event {event['type']}: {str(handler_err)}"
        )
        return jsonify({"received": False, "error": "Handler failed"}), 500

    return jsonify({"received": True})


def handle_successful_payment(session):
    """Process a successful checkout session"""
    try:
        checkout_session_id = session["id"]
        payment_intent_id = session.get("payment_intent")

        # Find the pending credit
        credit = MigrationCredit.query.filter_by(
            stripe_checkout_session_id=checkout_session_id
        ).first()

        if not credit:
            logger.error(f"No credit found for session {checkout_session_id}")
            return

        # Already processed?
        if credit.payment_status == "paid":
            logger.info(f"Credit {credit.id} already marked as paid")
            return

        # CRITICAL FIX: Wrap in transaction to prevent partial updates
        try:
            db.session.begin_nested()  # Start savepoint

            # Mark as paid and available
            credit.mark_paid(payment_intent_id)

            # Update user's subscription tier and sync migration counts
            user = db.session.get(User, credit.user_id)
            if user:
                # Always update tier to reflect most recent purchase
                if not user.subscription_tier:
                    user.subscription_tier = credit.tier_type
                    user.tier_purchased_at = datetime.now(timezone.utc)

                # CRITICAL FIX: Sync User.migrations_purchased with MigrationCredit count
                # This ensures backwards compatibility with code that reads from User model
                # The MigrationCredit table is the source of truth, but we keep User in sync
                user.migrations_purchased = (user.migrations_purchased or 0) + 1

            db.session.commit()  # Commit both changes atomically

        except Exception as e:
            db.session.rollback()
            logger.error(f"Transaction failed for credit {credit.id}: {str(e)}")
            raise

        logger.info(
            f"Payment successful: Credit {credit.id} activated for user {credit.user_id}"
        )

    except Exception as e:
        logger.exception(f"Error processing successful payment: {str(e)}")


def handle_expired_session(session):
    """Handle expired checkout session"""
    try:
        checkout_session_id = session["id"]

        credit = MigrationCredit.query.filter_by(
            stripe_checkout_session_id=checkout_session_id
        ).first()

        if credit and credit.status == "pending":
            credit.mark_failed()
            logger.info(f"Credit {credit.id} expired (session timeout)")

    except Exception as e:
        logger.exception(f"Error processing expired session: {str(e)}")


def handle_failed_payment(payment_intent):
    """Handle failed payment"""
    try:
        payment_intent_id = payment_intent["id"]

        # Find credit by payment intent
        credit = MigrationCredit.query.filter_by(
            stripe_payment_intent_id=payment_intent_id
        ).first()

        if credit:
            credit.mark_failed()
            logger.info(f"Credit {credit.id} marked as failed")

    except Exception as e:
        logger.exception(f"Error processing failed payment: {str(e)}")


@payments_bp.route("/credits", methods=["GET"])
@require_auth
def get_credits():
    """
    Get all migration credits for the current user.
    Returns breakdown by type and total available.
    """
    try:
        current_user = _get_current_user()
        if not current_user:
            return jsonify({"success": False, "error": "User not found"}), 401

        # Get summary by type
        summary = MigrationCredit.get_credits_summary(current_user.id)

        # Get all credits for details
        all_credits = (
            MigrationCredit.query.filter_by(user_id=current_user.id)
            .filter(MigrationCredit.payment_status == "paid")
            .order_by(MigrationCredit.created_at.desc())
            .all()
        )

        # Calculate totals
        total_available = sum(t["available"] for t in summary.values())
        total_used = sum(t["used"] for t in summary.values())

        return jsonify(
            {
                "success": True,
                "credits": {
                    "by_type": summary,
                    "total_available": total_available,
                    "total_used": total_used,
                    "all_credits": [c.to_dict() for c in all_credits],
                },
            }
        )

    except Exception as e:
        logger.exception(f"Error getting credits: {str(e)}")
        return jsonify({"success": False, "error": "Failed to get credits"}), 500


@payments_bp.route("/verify-session/<session_id>", methods=["GET"])
@require_auth
def verify_session(session_id):
    """
    Verify a checkout session after redirect.
    Frontend calls this to confirm payment was successful.
    """
    try:
        current_user = _get_current_user()
        if not current_user:
            return jsonify({"success": False, "error": "User not found"}), 401

        # Find the credit
        credit = MigrationCredit.query.filter_by(
            stripe_checkout_session_id=session_id, user_id=current_user.id
        ).first()

        if not credit:
            return jsonify({"success": False, "error": "Session not found"}), 404

        # HIGH-01 FIX: Check both status AND payment_status to prevent double processing.
        # The webhook may have already processed this payment between the user's redirect
        # and this verification call, causing duplicate credit allocation.
        if credit.status == "pending" and credit.payment_status != "paid":
            session = stripe.checkout.Session.retrieve(session_id)

            if session.payment_status == "paid":
                # Use SELECT FOR UPDATE to prevent race with concurrent webhook
                locked_credit = MigrationCredit.query.filter_by(
                    id=credit.id
                ).with_for_update().first()
                if locked_credit and locked_credit.payment_status != "paid":
                    locked_credit.mark_paid(session.payment_intent, auto_commit=False)
                    db.session.commit()
                else:
                    logger.info(f"Credit {credit.id} already processed by webhook")
                credit = locked_credit or credit

        return jsonify(
            {
                "success": True,
                "credit": credit.to_dict(),
                "is_paid": credit.payment_status == "paid",
            }
        )

    except Exception as e:
        logger.exception(f"Error verifying session: {str(e)}")
        return jsonify({"success": False, "error": "Failed to verify session"}), 500


@payments_bp.route("/tiers", methods=["GET"])
def get_tiers():
    """Get all available pricing tiers (public endpoint)"""
    tiers = []
    for tier_id, config in MigrationCredit.TIER_CONFIG.items():
        tiers.append(
            {
                "id": tier_id,
                "name": config["name"],
                "price": config["price_cents"] / 100,  # Convert to dollars
                "price_cents": config["price_cents"],
                "max_transactions": config["transaction_limit"],
                "description": config["description"],
                "migrations": 1,  # Each purchase is 1 migration
            }
        )

    # Sort by price
    tiers.sort(key=lambda x: x["price"])

    return jsonify({"success": True, "tiers": tiers})
