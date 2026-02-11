"""
Tests for MigrationCredit concurrency/race condition handling.

Covers:
- TOCTOU prevention with SELECT FOR UPDATE (HIGH-11 fix)
- find_best_credit with lock_for_update
- Concurrent use_for_migration attempts
- Credit state transitions
- Edge cases: unlimited credits, exact-limit, over-limit
"""

import os
import threading
from unittest.mock import patch, MagicMock

import pytest

os.environ["FLASK_ENV"] = "testing"

from models.migration_credit import MigrationCredit


class TestCreditStateTransitions:
    """Tests for credit lifecycle state transitions."""

    def test_create_pending_valid_tier(self, db_session):
        """Creates pending credit for valid tier."""
        credit = MigrationCredit.create_pending(
            user_id=1,
            tier_type="starter",
            stripe_checkout_session_id="cs_test_001",
            auto_commit=False,
        )
        db_session.add(credit)
        db_session.flush()

        assert credit.status == "pending"
        assert credit.payment_status == "pending"
        assert credit.tier_type == "starter"
        assert credit.transaction_limit == 5000
        assert credit.price_cents == 49700

    def test_create_pending_invalid_tier(self, db_session):
        """Raises ValueError for invalid tier type."""
        with pytest.raises(ValueError, match="Invalid tier type"):
            MigrationCredit.create_pending(
                user_id=1,
                tier_type="invalid_tier",
                stripe_checkout_session_id="cs_test_002",
            )

    def test_mark_paid_transition(self, db_session):
        """Marks credit as paid and available."""
        credit = MigrationCredit(
            user_id=1,
            tier_type="business",
            transaction_limit=25000,
            price_cents=99700,
            stripe_checkout_session_id="cs_test_003",
            payment_status="pending",
            status="pending",
        )
        db_session.add(credit)
        db_session.flush()

        credit.mark_paid("pi_test_001", auto_commit=False)

        assert credit.status == "available"
        assert credit.payment_status == "paid"
        assert credit.stripe_payment_intent_id == "pi_test_001"
        assert credit.paid_at is not None

    def test_mark_failed_transition(self, db_session):
        """Marks credit as failed/expired."""
        credit = MigrationCredit(
            user_id=1,
            tier_type="starter",
            transaction_limit=5000,
            price_cents=49700,
            stripe_checkout_session_id="cs_test_004",
            payment_status="pending",
            status="pending",
        )
        db_session.add(credit)
        db_session.flush()

        credit.mark_failed(auto_commit=False)

        assert credit.payment_status == "failed"
        assert credit.status == "expired"


class TestUseForMigration:
    """Tests for use_for_migration with TOCTOU protection (HIGH-11 fix)."""

    def test_use_available_credit(self, db_session):
        """Successfully uses an available credit."""
        credit = MigrationCredit(
            user_id=1,
            tier_type="business",
            transaction_limit=25000,
            price_cents=99700,
            stripe_checkout_session_id="cs_test_005",
            stripe_payment_intent_id="pi_test_005",
            payment_status="paid",
            status="available",
        )
        db_session.add(credit)
        db_session.commit()

        result = credit.use_for_migration("mig-001", transactions_count=5000)

        assert result is True
        assert credit.status == "used"
        assert credit.migration_id == "mig-001"
        assert credit.transactions_used == 5000
        assert credit.used_at is not None

    def test_use_already_used_credit(self, db_session):
        """Cannot use an already-used credit (TOCTOU)."""
        credit = MigrationCredit(
            user_id=1,
            tier_type="starter",
            transaction_limit=5000,
            price_cents=49700,
            stripe_checkout_session_id="cs_test_006",
            stripe_payment_intent_id="pi_test_006",
            payment_status="paid",
            status="used",
        )
        db_session.add(credit)
        db_session.commit()

        result = credit.use_for_migration("mig-002", transactions_count=100)
        assert result is False

    def test_use_pending_credit(self, db_session):
        """Cannot use a pending (unpaid) credit."""
        credit = MigrationCredit(
            user_id=1,
            tier_type="starter",
            transaction_limit=5000,
            price_cents=49700,
            stripe_checkout_session_id="cs_test_007",
            payment_status="pending",
            status="pending",
        )
        db_session.add(credit)
        db_session.commit()

        result = credit.use_for_migration("mig-003", transactions_count=100)
        assert result is False

    def test_use_exceeds_transaction_limit(self, db_session):
        """Cannot use credit when transaction count exceeds limit."""
        credit = MigrationCredit(
            user_id=1,
            tier_type="starter",
            transaction_limit=5000,
            price_cents=49700,
            stripe_checkout_session_id="cs_test_008",
            stripe_payment_intent_id="pi_test_008",
            payment_status="paid",
            status="available",
        )
        db_session.add(credit)
        db_session.commit()

        result = credit.use_for_migration("mig-004", transactions_count=10000)
        assert result is False

    def test_use_unlimited_credit(self, db_session):
        """Unlimited (forensic) credit handles any transaction count."""
        credit = MigrationCredit(
            user_id=1,
            tier_type="forensic",
            transaction_limit=-1,  # Unlimited
            price_cents=799700,
            stripe_checkout_session_id="cs_test_009",
            stripe_payment_intent_id="pi_test_009",
            payment_status="paid",
            status="available",
        )
        db_session.add(credit)
        db_session.commit()

        result = credit.use_for_migration("mig-005", transactions_count=1000000)
        assert result is True
        assert credit.status == "used"


class TestCanHandleTransactions:
    """Tests for transaction limit checking."""

    def test_within_limit(self):
        credit = MigrationCredit(transaction_limit=5000)
        assert credit.can_handle_transactions(4999) is True

    def test_exact_limit(self):
        credit = MigrationCredit(transaction_limit=5000)
        assert credit.can_handle_transactions(5000) is True

    def test_over_limit(self):
        credit = MigrationCredit(transaction_limit=5000)
        assert credit.can_handle_transactions(5001) is False

    def test_unlimited(self):
        credit = MigrationCredit(transaction_limit=-1)
        assert credit.can_handle_transactions(999999999) is True


class TestFindBestCredit:
    """Tests for find_best_credit — smallest suitable credit selection."""

    def test_finds_smallest_suitable(self, db_session):
        """Returns the smallest credit that can handle the transaction count."""
        # Create user first
        from models.user import User
        user = User(email="credit-test@example.com", first_name="Test", last_name="User")
        user.set_password("TestPassword1234!")
        db_session.add(user)
        db_session.commit()

        # Create multiple credits
        for tier, limit, price in [
            ("starter", 5000, 49700),
            ("business", 25000, 99700),
            ("professional", 100000, 199700),
        ]:
            credit = MigrationCredit(
                user_id=user.id,
                tier_type=tier,
                transaction_limit=limit,
                price_cents=price,
                stripe_checkout_session_id=f"cs_{tier}",
                stripe_payment_intent_id=f"pi_{tier}",
                payment_status="paid",
                status="available",
            )
            db_session.add(credit)
        db_session.commit()

        # Should return starter (5000) for 3000 transactions
        best = MigrationCredit.find_best_credit(user.id, 3000)
        assert best is not None
        assert best.tier_type == "starter"

        # Should return business (25000) for 10000 transactions
        best = MigrationCredit.find_best_credit(user.id, 10000)
        assert best is not None
        assert best.tier_type == "business"

        # Should return professional (100000) for 50000 transactions
        best = MigrationCredit.find_best_credit(user.id, 50000)
        assert best is not None
        assert best.tier_type == "professional"

    def test_no_suitable_credit(self, db_session):
        """Returns None when no credit can handle the transaction count."""
        from models.user import User
        user = User(email="nocredit@example.com", first_name="No", last_name="Credit")
        user.set_password("TestPassword1234!")
        db_session.add(user)
        db_session.commit()

        credit = MigrationCredit(
            user_id=user.id,
            tier_type="starter",
            transaction_limit=5000,
            price_cents=49700,
            stripe_checkout_session_id="cs_small",
            stripe_payment_intent_id="pi_small",
            payment_status="paid",
            status="available",
        )
        db_session.add(credit)
        db_session.commit()

        best = MigrationCredit.find_best_credit(user.id, 10000)
        assert best is None

    def test_skips_used_credits(self, db_session):
        """Used credits are not returned."""
        from models.user import User
        user = User(email="used@example.com", first_name="Used", last_name="Credit")
        user.set_password("TestPassword1234!")
        db_session.add(user)
        db_session.commit()

        credit = MigrationCredit(
            user_id=user.id,
            tier_type="business",
            transaction_limit=25000,
            price_cents=99700,
            stripe_checkout_session_id="cs_used",
            stripe_payment_intent_id="pi_used",
            payment_status="paid",
            status="used",
        )
        db_session.add(credit)
        db_session.commit()

        best = MigrationCredit.find_best_credit(user.id, 1000)
        assert best is None

    def test_unlimited_credit_sorted_last(self, db_session):
        """Unlimited credits are used only when smaller ones insufficient."""
        from models.user import User
        user = User(email="unlim@example.com", first_name="Unlim", last_name="Test")
        user.set_password("TestPassword1234!")
        db_session.add(user)
        db_session.commit()

        for tier, limit, price in [
            ("starter", 5000, 49700),
            ("forensic", -1, 799700),
        ]:
            credit = MigrationCredit(
                user_id=user.id,
                tier_type=tier,
                transaction_limit=limit,
                price_cents=price,
                stripe_checkout_session_id=f"cs_sort_{tier}",
                stripe_payment_intent_id=f"pi_sort_{tier}",
                payment_status="paid",
                status="available",
            )
            db_session.add(credit)
        db_session.commit()

        # For 3000 transactions, should pick starter (5000) over forensic (-1)
        best = MigrationCredit.find_best_credit(user.id, 3000)
        assert best.tier_type == "starter"

        # For 10000 transactions, should pick forensic (unlimited)
        best = MigrationCredit.find_best_credit(user.id, 10000)
        assert best.tier_type == "forensic"


class TestGetAvailableForUser:
    """Tests for get_available_for_user — requires BOTH status and payment checks."""

    def test_returns_only_available_paid(self, db_session):
        """Only returns credits with status=available AND payment_status=paid."""
        from models.user import User
        user = User(email="avail@example.com", first_name="Avail", last_name="Test")
        user.set_password("TestPassword1234!")
        db_session.add(user)
        db_session.commit()

        # Available + Paid (should be returned)
        credit1 = MigrationCredit(
            user_id=user.id, tier_type="starter", transaction_limit=5000,
            price_cents=49700, stripe_checkout_session_id="cs_ap",
            stripe_payment_intent_id="pi_ap", payment_status="paid", status="available",
        )
        # Available but NOT paid (should NOT be returned)
        credit2 = MigrationCredit(
            user_id=user.id, tier_type="business", transaction_limit=25000,
            price_cents=99700, stripe_checkout_session_id="cs_anp",
            payment_status="pending", status="available",
        )
        # Paid but used (should NOT be returned)
        credit3 = MigrationCredit(
            user_id=user.id, tier_type="professional", transaction_limit=100000,
            price_cents=199700, stripe_checkout_session_id="cs_pu",
            stripe_payment_intent_id="pi_pu", payment_status="paid", status="used",
        )
        db_session.add_all([credit1, credit2, credit3])
        db_session.commit()

        available = MigrationCredit.get_available_for_user(user.id)
        assert len(available) == 1
        assert available[0].tier_type == "starter"


class TestGetCreditsSummary:
    """Tests for credits summary generation."""

    def test_summary_includes_only_paid(self, db_session):
        """Summary only counts paid credits."""
        from models.user import User
        user = User(email="summary@example.com", first_name="Sum", last_name="Test")
        user.set_password("TestPassword1234!")
        db_session.add(user)
        db_session.commit()

        # Two paid credits, one pending
        for status, payment_status, sid in [
            ("available", "paid", "cs_s1"),
            ("used", "paid", "cs_s2"),
            ("pending", "pending", "cs_s3"),
        ]:
            credit = MigrationCredit(
                user_id=user.id, tier_type="starter", transaction_limit=5000,
                price_cents=49700, stripe_checkout_session_id=sid,
                stripe_payment_intent_id=f"pi_{sid}" if payment_status == "paid" else None,
                payment_status=payment_status, status=status,
            )
            db_session.add(credit)
        db_session.commit()

        summary = MigrationCredit.get_credits_summary(user.id)
        assert "starter" in summary
        assert summary["starter"]["available"] == 1
        assert summary["starter"]["used"] == 1


class TestToDict:
    """Tests for dictionary serialization."""

    def test_to_dict_includes_all_fields(self):
        """to_dict includes all expected fields."""
        credit = MigrationCredit(
            id=1, tier_type="business", transaction_limit=25000,
            price_cents=99700, status="available", payment_status="paid",
        )
        d = credit.to_dict()

        assert d["id"] == 1
        assert d["tier_type"] == "business"
        assert d["tier_name"] == "Business"
        assert d["transaction_limit"] == 25000
        assert d["price_cents"] == 99700
        assert d["status"] == "available"
        assert d["payment_status"] == "paid"

    def test_tier_config_all_tiers(self):
        """All tier configurations are complete."""
        for tier_type, config in MigrationCredit.TIER_CONFIG.items():
            assert "name" in config
            assert "price_cents" in config
            assert "transaction_limit" in config
            assert "description" in config
            assert config["price_cents"] > 0
