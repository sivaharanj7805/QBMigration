"""
End-to-end test for the enhanced migration tracking system.
Tests: registration, tier endpoints, credits API, and /me endpoint.
"""

import time

import requests

API_URL = "http://localhost:5000"


def test_health():
    """Test server health"""
    print("\n1. Testing Server Health...")
    try:
        response = requests.get(f"{API_URL}/health", timeout=5)
        data = response.json()
        print(f"   Status: {data.get('status')}")
        assert data.get("status") == "healthy", "Server unhealthy"
        print("   [PASS] Server is healthy")
        return True
    except Exception as e:
        print(f"   [FAIL] {e}")
        return False


def test_tiers_endpoint():
    """Test public tiers endpoint"""
    print("\n2. Testing Tiers Endpoint (public)...")
    try:
        response = requests.get(f"{API_URL}/api/payments/tiers")
        data = response.json()

        assert data["success"], "Tiers endpoint failed"
        assert len(data["tiers"]) == 5, f"Expected 5 tiers, got {len(data['tiers'])}"

        tier_names = [t["id"] for t in data["tiers"]]
        print(f"   Tiers: {tier_names}")

        # Verify tier structure
        for tier in data["tiers"]:
            assert "id" in tier
            assert "name" in tier
            assert "price" in tier
            assert "max_transactions" in tier
            print(
                f"   - {tier['name']}: ${tier['price']} ({tier['max_transactions']} txn)"
            )

        print("   [PASS] Tiers endpoint working")
        return True
    except Exception as e:
        print(f"   [FAIL] {e}")
        return False


def test_registration():
    """Test user registration"""
    print("\n3. Testing User Registration...")
    try:
        email = f"test_{int(time.time())}@example.com"
        response = requests.post(
            f"{API_URL}/api/auth/register",
            json={
                "email": email,
                "password": "TestPassword123!",
                "first_name": "Test",
                "last_name": "User",
            },
        )

        data = response.json()
        assert data["success"], f"Registration failed: {data.get('error')}"
        assert "token" in data, "No token returned"

        print(f"   Registered: {email}")
        print(f"   Token: {data['token'][:50]}...")
        print("   [PASS] Registration successful")
        return data["token"]
    except Exception as e:
        print(f"   [FAIL] {e}")
        return None


def test_me_endpoint(token):
    """Test /me endpoint with credits breakdown"""
    print("\n4. Testing /me Endpoint...")
    try:
        response = requests.get(
            f"{API_URL}/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        )

        data = response.json()
        assert data["success"], f"/me failed: {data.get('error')}"

        user = data["user"]
        print(f"   User: {user.get('email')}")
        print(f"   Has Tier: {user.get('has_tier')}")
        print(f"   Migrations Remaining: {user.get('migrations_remaining')}")
        print(f"   Migration Credits: {user.get('migration_credits', {})}")

        # Verify new fields exist
        assert "migration_credits" in user, "migration_credits field missing"
        assert (
            "total_credits_available" in user
        ), "total_credits_available field missing"

        print("   [PASS] /me endpoint includes credit breakdown")
        return True
    except Exception as e:
        print(f"   [FAIL] {e}")
        return False


def test_checkout_without_stripe():
    """Test checkout endpoint (expects error without Stripe key)"""
    print("\n5. Testing Checkout Endpoint (without Stripe)...")
    try:
        # First register a new user
        email = f"checkout_test_{int(time.time())}@example.com"
        reg_response = requests.post(
            f"{API_URL}/api/auth/register",
            json={
                "email": email,
                "password": "TestPassword123!",
                "first_name": "Checkout",
                "last_name": "Test",
            },
        )
        token = reg_response.json().get("token")

        # Try to create checkout
        response = requests.post(
            f"{API_URL}/api/payments/create-checkout",
            headers={"Authorization": f"Bearer {token}"},
            json={"tier_type": "starter"},
        )

        data = response.json()

        if response.status_code == 503:
            print("   Expected: Stripe not configured (no API key)")
            print(f"   Error: {data.get('error')}")
            print("   [PASS] Checkout correctly rejects without Stripe key")
            return True
        elif response.status_code == 200:
            print("   Stripe is configured!")
            print(f"   Checkout URL: {data.get('checkout_url', 'N/A')[:80]}...")
            print("   [PASS] Checkout session created")
            return True
        else:
            print(f"   Unexpected status: {response.status_code}")
            print(f"   Response: {data}")
            return False
    except Exception as e:
        print(f"   [FAIL] {e}")
        return False


def test_credits_endpoint(token):
    """Test credits endpoint"""
    print("\n6. Testing Credits Endpoint...")
    try:
        response = requests.get(
            f"{API_URL}/api/payments/credits",
            headers={"Authorization": f"Bearer {token}"},
        )

        data = response.json()
        assert data["success"], f"Credits failed: {data.get('error')}"

        credits = data["credits"]
        print(f"   By Type: {credits.get('by_type', {})}")
        print(f"   Total Available: {credits.get('total_available')}")
        print(f"   Total Used: {credits.get('total_used')}")

        print("   [PASS] Credits endpoint working")
        return True
    except Exception as e:
        print(f"   [FAIL] {e}")
        return False


def run_tests():
    """Run all tests"""
    print("=" * 60)
    print("ENHANCED MIGRATION TRACKING - END TO END TEST")
    print("=" * 60)

    results = []

    # Test 1: Health
    results.append(("Server Health", test_health()))

    # Test 2: Tiers
    results.append(("Tiers Endpoint", test_tiers_endpoint()))

    # Test 3: Registration
    token = test_registration()
    results.append(("Registration", token is not None))

    if token:
        # Test 4: /me endpoint
        results.append(("/me Endpoint", test_me_endpoint(token)))

        # Test 5: Checkout
        results.append(("Checkout Endpoint", test_checkout_without_stripe()))

        # Test 6: Credits
        results.append(("Credits Endpoint", test_credits_endpoint(token)))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = 0
    failed = 0

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {name}: [{status}]")
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\n  Total: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
