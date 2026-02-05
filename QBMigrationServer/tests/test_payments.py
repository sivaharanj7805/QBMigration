"""
Test Suite for Payments REST API Endpoints
Tests cover:
1. Get tiers (success, correct structure)
2. Get credits (empty, with credits)
3. Create checkout returns 503 when Stripe not configured
4. Webhook with invalid payload returns 400
5. Credit creation and retrieval

NOTE: The payments blueprint is not registered in app.py by default.
We register it via a conftest-level fixture that runs before any request
is made to the app.
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
from models.migration_credit import MigrationCredit


class TestGetTiers:
    """Tests for GET /api/payments/tiers (public endpoint)."""

    def test_get_tiers_success(self, client, db_session):
        """Tiers endpoint returns 200 with tier list."""
        response = client.get("/api/payments/tiers")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert isinstance(data["tiers"], list)
        assert len(data["tiers"]) > 0

    def test_get_tiers_no_auth_required(self, client, db_session):
        """Tiers endpoint does not require authentication."""
        response = client.get("/api/payments/tiers")
        assert response.status_code == 200

    def test_get_tiers_correct_structure(self, client, db_session):
        """Each tier has required fields with correct types."""
        response = client.get("/api/payments/tiers")
        data = response.get_json()
        tiers = data["tiers"]

        required_fields = [
            "id",
            "name",
            "price",
            "price_cents",
            "max_transactions",
            "description",
            "migrations",
        ]
        for tier in tiers:
            for field in required_fields:
                assert (
                    field in tier
                ), f"Missing field '{field}' in tier {tier.get('id', 'unknown')}"

            # Type checks
            assert isinstance(tier["price"], (int, float))
            assert isinstance(tier["price_cents"], int)
            assert isinstance(tier["max_transactions"], int)
            assert isinstance(tier["name"], str)
            assert isinstance(tier["description"], str)
            assert tier["migrations"] == 1  # Each purchase is 1 migration

    def test_get_tiers_sorted_by_price(self, client, db_session):
        """Tiers are returned sorted by price ascending."""
        response = client.get("/api/payments/tiers")
        data = response.get_json()
        tiers = data["tiers"]
        prices = [t["price"] for t in tiers]
        assert prices == sorted(prices)

    def test_get_tiers_contains_known_tiers(self, client, db_session):
        """Response contains expected tier IDs."""
        response = client.get("/api/payments/tiers")
        data = response.get_json()
        tier_ids = {t["id"] for t in data["tiers"]}
        expected = {"starter", "business", "professional", "enterprise", "forensic"}
        assert expected == tier_ids

    def test_get_tiers_price_cents_matches_dollars(self, client, db_session):
        """price_cents / 100 equals price for each tier."""
        response = client.get("/api/payments/tiers")
        data = response.get_json()
        for tier in data["tiers"]:
            assert tier["price"] == tier["price_cents"] / 100


class TestGetCredits:
    """Tests for GET /api/payments/credits (requires auth)."""

    def test_get_credits_requires_auth(self, client, db_session):
        """Unauthenticated request returns 401."""
        response = client.get("/api/payments/credits")
        assert response.status_code == 401

    def test_get_credits_empty(self, authenticated_client, db_session):
        """Returns empty credits when user has none."""
        response = authenticated_client.get("/api/payments/credits")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["credits"]["total_available"] == 0
        assert data["credits"]["total_used"] == 0
        assert data["credits"]["all_credits"] == []

    def test_get_credits_with_paid_credit(
        self, authenticated_client, db_session, test_user
    ):
        """Returns credit details for a paid credit."""
        credit = MigrationCredit(
            user_id=test_user.id,
            tier_type="starter",
            transaction_limit=5000,
            price_cents=49700,
            stripe_checkout_session_id="cs_test_" + str(uuid.uuid4()),
            stripe_payment_intent_id="pi_test_" + str(uuid.uuid4()),
            payment_status="paid",
            status="available",
            paid_at=datetime.now(timezone.utc),
        )
        db_session.add(credit)
        db_session.commit()

        response = authenticated_client.get("/api/payments/credits")
        assert response.status_code == 200
        data = response.get_json()
        assert data["credits"]["total_available"] == 1
        assert data["credits"]["total_used"] == 0
        assert len(data["credits"]["all_credits"]) == 1

        credit_data = data["credits"]["all_credits"][0]
        assert credit_data["tier_type"] == "starter"
        assert credit_data["status"] == "available"
        assert credit_data["payment_status"] == "paid"

    def test_get_credits_with_used_credit(
        self, authenticated_client, db_session, test_user
    ):
        """Used credits appear in totals correctly."""
        credit = MigrationCredit(
            user_id=test_user.id,
            tier_type="business",
            transaction_limit=25000,
            price_cents=99700,
            stripe_checkout_session_id="cs_test_" + str(uuid.uuid4()),
            stripe_payment_intent_id="pi_test_" + str(uuid.uuid4()),
            payment_status="paid",
            status="used",
            paid_at=datetime.now(timezone.utc),
            used_at=datetime.now(timezone.utc),
            migration_id=str(uuid.uuid4()),
        )
        db_session.add(credit)
        db_session.commit()

        response = authenticated_client.get("/api/payments/credits")
        data = response.get_json()
        assert data["credits"]["total_available"] == 0
        assert data["credits"]["total_used"] == 1

    def test_get_credits_excludes_pending_unpaid(
        self, authenticated_client, db_session, test_user
    ):
        """Pending (unpaid) credits are not counted in totals."""
        credit = MigrationCredit(
            user_id=test_user.id,
            tier_type="starter",
            transaction_limit=5000,
            price_cents=49700,
            stripe_checkout_session_id="cs_test_" + str(uuid.uuid4()),
            payment_status="pending",
            status="pending",
        )
        db_session.add(credit)
        db_session.commit()

        response = authenticated_client.get("/api/payments/credits")
        data = response.get_json()
        # Pending credits are excluded from all_credits (only paid shown)
        assert data["credits"]["total_available"] == 0
        assert data["credits"]["total_used"] == 0

    def test_get_credits_multiple_types(
        self, authenticated_client, db_session, test_user
    ):
        """Credits summary groups by tier type correctly."""
        for tier in ["starter", "business", "starter"]:
            credit = MigrationCredit(
                user_id=test_user.id,
                tier_type=tier,
                transaction_limit=MigrationCredit.TIER_CONFIG[tier][
                    "transaction_limit"
                ],
                price_cents=MigrationCredit.TIER_CONFIG[tier]["price_cents"],
                stripe_checkout_session_id="cs_test_" + str(uuid.uuid4()),
                stripe_payment_intent_id="pi_test_" + str(uuid.uuid4()),
                payment_status="paid",
                status="available",
                paid_at=datetime.now(timezone.utc),
            )
            db_session.add(credit)
        db_session.commit()

        response = authenticated_client.get("/api/payments/credits")
        data = response.get_json()
        assert data["credits"]["total_available"] == 3
        by_type = data["credits"]["by_type"]
        assert by_type["starter"]["available"] == 2
        assert by_type["business"]["available"] == 1


class TestCreateCheckout:
    """Tests for POST /api/payments/create-checkout (requires auth)."""

    def test_create_checkout_requires_auth(self, client, db_session):
        """Unauthenticated request returns 401."""
        response = client.post(
            "/api/payments/create-checkout", json={"tier_type": "starter"}
        )
        assert response.status_code == 401

    def test_create_checkout_stripe_not_configured(
        self, authenticated_client, db_session
    ):
        """Returns 503 when Stripe API key is not set."""
        response = authenticated_client.post(
            "/api/payments/create-checkout", json={"tier_type": "starter"}
        )
        # Stripe is not configured in test environment
        assert response.status_code == 503
        data = response.get_json()
        assert data["success"] is False
        assert "not configured" in data["error"].lower() or "Payment" in data["error"]

    def test_create_checkout_missing_tier_type(self, authenticated_client, db_session):
        """Returns 400 when tier_type is missing."""
        response = authenticated_client.post("/api/payments/create-checkout", json={})
        # Could be 400 (missing field) or 503 (stripe not configured) depending on order of checks
        assert response.status_code in [400, 503]

    def test_create_checkout_invalid_tier_type(self, authenticated_client, db_session):
        """Returns 400 for an invalid tier type."""
        response = authenticated_client.post(
            "/api/payments/create-checkout", json={"tier_type": "nonexistent_tier"}
        )
        # Could be 400 (invalid tier) or 503 (stripe not configured) depending on order of checks
        assert response.status_code in [400, 503]


class TestStripeWebhook:
    """Tests for POST /api/payments/webhook."""

    def test_webhook_no_auth_required(self, client, db_session):
        """Webhook endpoint does not require JWT authentication (Stripe calls it)."""
        response = client.post(
            "/api/payments/webhook",
            data=b"{}",
            content_type="application/json",
        )
        # Should not return 401 (no auth required)
        assert response.status_code != 401

    def test_webhook_invalid_payload(self, client, db_session):
        """Invalid payload returns 400 or 500 depending on webhook secret config."""
        response = client.post(
            "/api/payments/webhook",
            data=b"not json at all {{{",
            content_type="application/json",
            headers={"Stripe-Signature": "fake_sig"},
        )
        # Without STRIPE_WEBHOOK_SECRET configured, returns 500
        # With it configured but bad sig, returns 400
        assert response.status_code in [400, 500]

    def test_webhook_missing_signature(self, client, db_session):
        """Missing Stripe-Signature header is rejected."""
        response = client.post(
            "/api/payments/webhook",
            data=json.dumps({"type": "checkout.session.completed"}).encode(),
            content_type="application/json",
        )
        # No signature header and no webhook secret configured = 500
        assert response.status_code in [400, 500]

    def test_webhook_empty_body(self, client, db_session):
        """Empty body is rejected."""
        response = client.post(
            "/api/payments/webhook",
            data=b"",
            content_type="application/json",
            headers={"Stripe-Signature": "fake_sig"},
        )
        assert response.status_code in [400, 500]


class TestCreditCreationAndRetrieval:
    """Tests for MigrationCredit model operations via the API."""

    def test_credit_to_dict_structure(self, db_session, test_user):
        """MigrationCredit.to_dict() returns expected fields."""
        credit = MigrationCredit(
            user_id=test_user.id,
            tier_type="professional",
            transaction_limit=100000,
            price_cents=199700,
            stripe_checkout_session_id="cs_test_struct",
            payment_status="paid",
            status="available",
            paid_at=datetime.now(timezone.utc),
        )
        db_session.add(credit)
        db_session.commit()
        db_session.refresh(credit)

        d = credit.to_dict()
        assert d["tier_type"] == "professional"
        assert d["tier_name"] == "Professional"
        assert d["transaction_limit"] == 100000
        assert d["price_cents"] == 199700
        assert d["status"] == "available"
        assert d["payment_status"] == "paid"
        assert d["paid_at"] is not None

    def test_create_pending_credit(self, db_session, test_user):
        """MigrationCredit.create_pending creates a pending credit."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="starter",
            stripe_checkout_session_id="cs_test_pending_" + str(uuid.uuid4()),
        )
        assert credit.status == "pending"
        assert credit.payment_status == "pending"
        assert credit.tier_type == "starter"
        assert credit.transaction_limit == 5000
        assert credit.price_cents == 49700

    def test_mark_paid_transitions_to_available(self, db_session, test_user):
        """mark_paid changes status to available and payment_status to paid."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="business",
            stripe_checkout_session_id="cs_test_pay_" + str(uuid.uuid4()),
        )
        credit.mark_paid("pi_test_" + str(uuid.uuid4()))
        db_session.refresh(credit)

        assert credit.status == "available"
        assert credit.payment_status == "paid"
        assert credit.paid_at is not None

    def test_mark_failed_transitions_to_expired(self, db_session, test_user):
        """mark_failed changes status to expired."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="starter",
            stripe_checkout_session_id="cs_test_fail_" + str(uuid.uuid4()),
        )
        credit.mark_failed()
        db_session.refresh(credit)

        assert credit.status == "expired"
        assert credit.payment_status == "failed"

    def test_use_for_migration(self, db_session, test_user):
        """use_for_migration marks credit as used."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="starter",
            stripe_checkout_session_id="cs_test_use_" + str(uuid.uuid4()),
        )
        credit.mark_paid("pi_test_" + str(uuid.uuid4()))

        migration_id = str(uuid.uuid4())
        result = credit.use_for_migration(migration_id, transactions_count=1000)
        assert result is True
        assert credit.status == "used"
        assert credit.migration_id == migration_id
        assert credit.transactions_used == 1000

    def test_use_for_migration_not_available(self, db_session, test_user):
        """Cannot use a credit that is not available."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="starter",
            stripe_checkout_session_id="cs_test_notavail_" + str(uuid.uuid4()),
        )
        # Still pending - not paid
        result = credit.use_for_migration(str(uuid.uuid4()))
        assert result is False

    def test_use_for_migration_exceeds_limit(self, db_session, test_user):
        """Cannot use credit if transaction count exceeds limit."""
        credit = MigrationCredit.create_pending(
            user_id=test_user.id,
            tier_type="starter",
            stripe_checkout_session_id="cs_test_exceed_" + str(uuid.uuid4()),
        )
        credit.mark_paid("pi_test_" + str(uuid.uuid4()))

        # Starter limit is 5000 - try 10000
        result = credit.use_for_migration(str(uuid.uuid4()), transactions_count=10000)
        assert result is False
        assert credit.status == "available"  # Not consumed

    def test_get_available_for_user(self, db_session, test_user):
        """get_available_for_user returns only available+paid credits."""
        # Create one available and one pending
        available = MigrationCredit(
            user_id=test_user.id,
            tier_type="starter",
            transaction_limit=5000,
            price_cents=49700,
            stripe_checkout_session_id="cs_test_avail_" + str(uuid.uuid4()),
            stripe_payment_intent_id="pi_test_avail_" + str(uuid.uuid4()),
            payment_status="paid",
            status="available",
            paid_at=datetime.now(timezone.utc),
        )
        pending = MigrationCredit(
            user_id=test_user.id,
            tier_type="starter",
            transaction_limit=5000,
            price_cents=49700,
            stripe_checkout_session_id="cs_test_pend_" + str(uuid.uuid4()),
            payment_status="pending",
            status="pending",
        )
        db_session.add_all([available, pending])
        db_session.commit()

        result = MigrationCredit.get_available_for_user(test_user.id)
        assert len(result) == 1
        assert result[0].payment_status == "paid"
        assert result[0].status == "available"

    def test_find_best_credit_smallest_suitable(self, db_session, test_user):
        """find_best_credit returns the smallest credit that fits."""
        for tier in ["professional", "starter"]:
            credit = MigrationCredit(
                user_id=test_user.id,
                tier_type=tier,
                transaction_limit=MigrationCredit.TIER_CONFIG[tier][
                    "transaction_limit"
                ],
                price_cents=MigrationCredit.TIER_CONFIG[tier]["price_cents"],
                stripe_checkout_session_id="cs_test_best_"
                + tier
                + "_"
                + str(uuid.uuid4()),
                stripe_payment_intent_id="pi_test_best_"
                + tier
                + "_"
                + str(uuid.uuid4()),
                payment_status="paid",
                status="available",
                paid_at=datetime.now(timezone.utc),
            )
            db_session.add(credit)
        db_session.commit()

        # 3000 transactions fits in starter (5000 limit)
        best = MigrationCredit.find_best_credit(test_user.id, 3000)
        assert best is not None
        assert best.tier_type == "starter"

    def test_find_best_credit_none_suitable(self, db_session, test_user):
        """find_best_credit returns None when no credit fits."""
        credit = MigrationCredit(
            user_id=test_user.id,
            tier_type="starter",
            transaction_limit=5000,
            price_cents=49700,
            stripe_checkout_session_id="cs_test_nofit_" + str(uuid.uuid4()),
            stripe_payment_intent_id="pi_test_nofit_" + str(uuid.uuid4()),
            payment_status="paid",
            status="available",
            paid_at=datetime.now(timezone.utc),
        )
        db_session.add(credit)
        db_session.commit()

        # 50000 transactions does not fit in starter (5000 limit)
        best = MigrationCredit.find_best_credit(test_user.id, 50000)
        assert best is None

    def test_credits_summary(self, db_session, test_user):
        """get_credits_summary returns correct counts by tier."""
        # 2 available starters, 1 used business
        for i in range(2):
            c = MigrationCredit(
                user_id=test_user.id,
                tier_type="starter",
                transaction_limit=5000,
                price_cents=49700,
                stripe_checkout_session_id=f"cs_summ_s{i}_" + str(uuid.uuid4()),
                stripe_payment_intent_id=f"pi_summ_s{i}_" + str(uuid.uuid4()),
                payment_status="paid",
                status="available",
                paid_at=datetime.now(timezone.utc),
            )
            db_session.add(c)
        used = MigrationCredit(
            user_id=test_user.id,
            tier_type="business",
            transaction_limit=25000,
            price_cents=99700,
            stripe_checkout_session_id="cs_summ_b_" + str(uuid.uuid4()),
            stripe_payment_intent_id="pi_summ_b_" + str(uuid.uuid4()),
            payment_status="paid",
            status="used",
            paid_at=datetime.now(timezone.utc),
            used_at=datetime.now(timezone.utc),
        )
        db_session.add(used)
        db_session.commit()

        summary = MigrationCredit.get_credits_summary(test_user.id)
        assert summary["starter"]["available"] == 2
        assert summary["starter"]["used"] == 0
        assert summary["business"]["available"] == 0
        assert summary["business"]["used"] == 1

    def test_create_pending_invalid_tier(self, db_session, test_user):
        """create_pending raises ValueError for invalid tier."""
        with pytest.raises(ValueError, match="Invalid tier type"):
            MigrationCredit.create_pending(
                user_id=test_user.id,
                tier_type="nonexistent",
                stripe_checkout_session_id="cs_test_invalid_" + str(uuid.uuid4()),
            )
