"""
MigrationCredit model - tracks individual purchased migrations by type.
Each purchase creates one credit that can be used for one migration.
"""

from datetime import datetime, timezone
from models.database import db, is_postgresql


class MigrationCredit(db.Model):
    """
    Represents a single purchased migration credit.
    Users buy credits (by type) and use them to perform migrations.
    """

    __tablename__ = "migration_credits"

    # MED-10 FIX: Add composite index for common query patterns
    __table_args__ = (
        db.Index(
            "idx_credit_user_status_payment", "user_id", "status", "payment_status"
        ),
        db.Index("idx_credit_user_tier", "user_id", "tier_type"),
    )

    id = db.Column(db.Integer, primary_key=True)
    # SECURITY FIX: Add CASCADE delete to clean up credits when user is deleted
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Migration type and limits
    tier_type = db.Column(
        db.String(50), nullable=False
    )  # starter, business, professional, enterprise, forensic
    transaction_limit = db.Column(
        db.Integer, nullable=False
    )  # Max transactions allowed
    price_cents = db.Column(db.Integer, nullable=False)  # Amount paid in cents

    # Stripe payment verification
    # CRIT-05 FIX: Add unique constraint on payment_intent_id for idempotency
    stripe_checkout_session_id = db.Column(db.String(255), unique=True, index=True)
    stripe_payment_intent_id = db.Column(
        db.String(255), unique=True, nullable=True, index=True
    )
    payment_status = db.Column(
        db.String(50), default="pending"
    )  # pending, paid, failed, refunded

    # Usage tracking
    status = db.Column(
        db.String(50), default="pending"
    )  # pending (unpaid), available, used, expired
    migration_id = db.Column(db.String(36))  # Links to the Migration when used
    transactions_used = db.Column(
        db.Integer, default=0
    )  # Actual transactions processed

    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    paid_at = db.Column(db.DateTime)
    used_at = db.Column(db.DateTime)

    # Relationship
    user = db.relationship(
        "User", backref=db.backref("migration_credits", lazy="dynamic")
    )

    # Tier configuration - transaction limits and prices
    TIER_CONFIG = {
        "starter": {
            "name": "Starter",
            "price_cents": 49700,  # $497
            "transaction_limit": 5000,
            "description": "Up to 5,000 transactions",
        },
        "business": {
            "name": "Business",
            "price_cents": 99700,  # $997
            "transaction_limit": 25000,
            "description": "Up to 25,000 transactions",
        },
        "professional": {
            "name": "Professional",
            "price_cents": 199700,  # $1,997
            "transaction_limit": 100000,
            "description": "Up to 100,000 transactions",
        },
        "enterprise": {
            "name": "Enterprise",
            "price_cents": 399700,  # $3,997
            "transaction_limit": 500000,
            "description": "Up to 500,000 transactions",
        },
        "forensic": {
            "name": "Forensic",
            "price_cents": 799700,  # $7,997
            "transaction_limit": -1,  # Unlimited
            "description": "Unlimited transactions",
        },
    }

    @classmethod
    def get_tier_config(cls, tier_type):
        """Get configuration for a tier type"""
        return cls.TIER_CONFIG.get(tier_type)

    @classmethod
    def create_pending(
        cls, user_id, tier_type, stripe_checkout_session_id, auto_commit=True
    ):
        """
        Create a pending credit when checkout session is created.
        Credit becomes 'available' only after Stripe confirms payment.

        Args:
            user_id: User ID
            tier_type: Credit tier type
            stripe_checkout_session_id: Stripe checkout session ID
            auto_commit: If True, commits immediately. If False, caller manages transaction.

        FIX BE-03: Allow caller to manage transaction context.
        """
        config = cls.TIER_CONFIG.get(tier_type)
        if not config:
            raise ValueError(f"Invalid tier type: {tier_type}")

        credit = cls(
            user_id=user_id,
            tier_type=tier_type,
            transaction_limit=config["transaction_limit"],
            price_cents=config["price_cents"],
            stripe_checkout_session_id=stripe_checkout_session_id,
            payment_status="pending",
            status="pending",
        )
        db.session.add(credit)

        if auto_commit:
            db.session.commit()

        return credit

    def mark_paid(self, payment_intent_id, auto_commit=True):
        """
        Mark credit as paid and available for use.

        FIX HIGH-05: Added proper transaction handling with rollback on error.

        Args:
            payment_intent_id: Stripe payment intent ID
            auto_commit: If True, commits immediately. If False, caller manages transaction.
        """
        try:
            self.payment_status = "paid"
            self.status = "available"
            self.stripe_payment_intent_id = payment_intent_id
            self.paid_at = datetime.now(timezone.utc)

            if auto_commit:
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise

    def mark_failed(self, auto_commit=True):
        """
        Mark payment as failed.

        FIX HIGH-05: Added proper transaction handling.
        """
        try:
            self.payment_status = "failed"
            self.status = "expired"

            if auto_commit:
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise

    def use_for_migration(self, migration_id, transactions_count=0):
        """
        Use this credit for a migration.
        Returns True if successful, False if credit can't be used.
        """
        if self.status != "available":
            return False

        # Check transaction limit (skip if unlimited = -1)
        if self.transaction_limit != -1 and transactions_count > self.transaction_limit:
            return False

        self.status = "used"
        self.migration_id = migration_id
        self.transactions_used = transactions_count
        self.used_at = datetime.now(timezone.utc)
        db.session.commit()
        return True

    def can_handle_transactions(self, transaction_count):
        """Check if this credit can handle the given transaction count"""
        if self.transaction_limit == -1:  # Unlimited
            return True
        return transaction_count <= self.transaction_limit

    @classmethod
    def get_available_for_user(cls, user_id):
        """
        Get all available credits for a user.

        CRITICAL: Must check BOTH status='available' AND payment_status='paid'
        to ensure we only return credits that are:
        1. Paid via Stripe (payment_status='paid')
        2. Not yet used for a migration (status='available')
        """
        return cls.query.filter_by(
            user_id=user_id, status="available", payment_status="paid"
        ).all()

    @classmethod
    def get_credits_summary(cls, user_id):
        """
        Get summary of credits by type for a user.
        Returns dict like: {'starter': {'available': 2, 'used': 1, 'limit': 5000}, ...}
        """
        credits = (
            cls.query.filter_by(user_id=user_id)
            .filter(cls.payment_status == "paid")  # Only count paid credits
            .all()
        )

        summary = {}
        for tier_type, config in cls.TIER_CONFIG.items():
            tier_credits = [c for c in credits if c.tier_type == tier_type]
            available = len([c for c in tier_credits if c.status == "available"])
            used = len([c for c in tier_credits if c.status == "used"])

            if available > 0 or used > 0:  # Only include types with credits
                summary[tier_type] = {
                    "name": config["name"],
                    "available": available,
                    "used": used,
                    "transaction_limit": config["transaction_limit"],
                    "description": config["description"],
                }

        return summary

    @classmethod
    def find_best_credit(cls, user_id, transaction_count, lock_for_update=False):
        """
        Find the best available credit for a given transaction count.
        Returns the smallest credit that can handle the transaction count,
        or None if no suitable credit is available.

        RACE CONDITION FIX: When lock_for_update=True, locks rows BEFORE filtering
        to prevent TOCTOU race conditions where another transaction could change
        the status between check and use.

        Args:
            user_id: User ID
            transaction_count: Number of transactions to process
            lock_for_update: If True, lock the row for update (use within transaction)
        """
        if lock_for_update:
            # RACE CONDITION FIX: Lock ALL user's credits first, then filter
            # This prevents another transaction from grabbing the same credit
            # between our SELECT and UPDATE
            # Note: FOR UPDATE only works with PostgreSQL; SQLite has implicit locking
            query = cls.query.filter_by(user_id=user_id)
            if is_postgresql():
                query = query.with_for_update(skip_locked=True)
            all_credits = query.all()

            # Now filter to available/paid credits (already locked)
            available = [
                c
                for c in all_credits
                if c.status == "available" and c.payment_status == "paid"
            ]
        else:
            # No locking - simple query
            available = cls.query.filter_by(
                user_id=user_id, status="available", payment_status="paid"
            ).all()

        # Filter to credits that can handle the transaction count
        suitable = [
            c for c in available if c.can_handle_transactions(transaction_count)
        ]

        if not suitable:
            return None

        # Sort by transaction limit (smallest first, -1/unlimited last)
        def sort_key(c):
            if c.transaction_limit == -1:
                return float("inf")
            return c.transaction_limit

        suitable.sort(key=sort_key)
        return suitable[0]  # Return smallest suitable credit

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "tier_type": self.tier_type,
            "tier_name": self.TIER_CONFIG.get(self.tier_type, {}).get(
                "name", self.tier_type
            ),
            "transaction_limit": self.transaction_limit,
            "price_cents": self.price_cents,
            "status": self.status,
            "payment_status": self.payment_status,
            "migration_id": self.migration_id,
            "transactions_used": self.transactions_used,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "used_at": self.used_at.isoformat() if self.used_at else None,
        }
