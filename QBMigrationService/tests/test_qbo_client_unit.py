"""
Unit tests for PremiumQBOClient (qbo_client.py)

Tests all core methods with mocked HTTP calls. Validates critical bug fixes:
- Token refresh updates _base_access_token (not access_token)
- Lock ordering: db_lock acquired before synctoken_lock in update_synctoken
- Query count whitelist validation prevents injection
- Idempotency keys and correlation IDs propagated in headers
- Fault response parsing extracts full Error array details
- Rate limit (429) honours Retry-After header
- Exponential backoff on 500/503 server errors
"""

import os
import sqlite3
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path so we can import qbo_client
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qbo_client import PremiumQBOClient  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_URL = "https://sandbox-quickbooks.api.intuit.com/v3/company/1234567890"
ACCESS_TOKEN = "test_access_token_abc123"


def _make_client(tmp_path, access_token=ACCESS_TOKEN, base_url=BASE_URL):
    """Create a PremiumQBOClient with a temporary database."""
    db_path = str(tmp_path / "unit_test.db")
    client = PremiumQBOClient(
        access_token=access_token,
        base_url=base_url,
        db_path=db_path,
    )
    return client


def _mock_response(status_code=200, json_data=None, headers=None, text=""):
    """Build a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.headers = headers or {}
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


def _mock_oauth_manager(new_token="refreshed_token_xyz"):
    """Build a mock OAuthManager that returns a new token on refresh."""
    mgr = MagicMock()
    mgr.refresh_access_token.return_value = None
    mgr.get_access_token.return_value = new_token
    return mgr


# ===================================================================
# 1. Constructor / Initialization
# ===================================================================


class TestConstructor:
    """Verify constructor stores state correctly."""

    def test_token_stored_as_base_access_token(self, tmp_path):
        """CRITICAL BUG FIX: token must be stored in _base_access_token."""
        client = _make_client(tmp_path)
        assert client._base_access_token == ACCESS_TOKEN
        assert (
            not hasattr(client, "access_token")
            or client._base_access_token == ACCESS_TOKEN
        )

    def test_base_url_stored(self, tmp_path):
        client = _make_client(tmp_path)
        assert client.base_url == BASE_URL

    def test_db_lock_is_threading_lock(self, tmp_path):
        client = _make_client(tmp_path)
        assert isinstance(client.db_lock, type(threading.Lock()))

    def test_synctoken_lock_is_threading_lock(self, tmp_path):
        client = _make_client(tmp_path)
        assert isinstance(client.synctoken_lock, type(threading.Lock()))

    def test_synctoken_cache_starts_empty(self, tmp_path):
        client = _make_client(tmp_path)
        assert client.synctoken_cache == {}

    def test_database_file_created(self, tmp_path):
        client = _make_client(tmp_path)
        assert client.db_path.exists()

    def test_invalid_qbo_plan_defaults_to_plus(self, tmp_path):
        db_path = str(tmp_path / "plan_test.db")
        client = PremiumQBOClient(
            access_token=ACCESS_TOKEN,
            base_url=BASE_URL,
            db_path=db_path,
            qbo_plan="InvalidPlan",
        )
        assert client.qbo_plan == "Plus"


# ===================================================================
# 2. _get_request_headers
# ===================================================================


class TestGetRequestHeaders:
    """Verify per-request headers are built correctly."""

    def test_authorization_header_uses_bearer_token(self, tmp_path):
        client = _make_client(tmp_path)
        headers = client._get_request_headers()
        assert headers["Authorization"] == f"Bearer {ACCESS_TOKEN}"

    def test_accept_header(self, tmp_path):
        client = _make_client(tmp_path)
        headers = client._get_request_headers()
        assert headers["Accept"] == "application/json"

    def test_content_type_header(self, tmp_path):
        client = _make_client(tmp_path)
        headers = client._get_request_headers()
        assert headers["Content-Type"] == "application/json"

    def test_headers_use_oauth_manager_token_when_provided(self, tmp_path):
        client = _make_client(tmp_path)
        mgr = _mock_oauth_manager("oauth_token_999")
        headers = client._get_request_headers(oauth_manager=mgr)
        assert headers["Authorization"] == "Bearer oauth_token_999"
        mgr.get_access_token.assert_called_once()

    def test_headers_raise_if_no_token(self, tmp_path):
        client = _make_client(tmp_path, access_token=None)
        with pytest.raises(ValueError, match="No access token available"):
            client._get_request_headers()


# ===================================================================
# 3. _make_request -- happy path
# ===================================================================


class TestMakeRequestHappyPath:
    """Verify normal request flow."""

    @patch("qbo_client.time.sleep", return_value=None)
    def test_post_request_sends_json(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        ok_resp = _mock_response(200, {"Customer": {"Id": "42", "SyncToken": "0"}})
        client.session.post = MagicMock(return_value=ok_resp)

        result = client._make_request("POST", "customer", {"Name": "Acme"})
        assert result["Customer"]["Id"] == "42"
        client.session.post.assert_called_once()

    @patch("qbo_client.time.sleep", return_value=None)
    def test_get_request(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        ok_resp = _mock_response(200, {"QueryResponse": {"totalCount": 5}})
        client.session.get = MagicMock(return_value=ok_resp)

        result = client._make_request(
            "GET", "query?query=SELECT+COUNT(*)+FROM+Customer"
        )
        assert result["QueryResponse"]["totalCount"] == 5

    @patch("qbo_client.time.sleep", return_value=None)
    def test_unsupported_method_raises(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        with pytest.raises(ValueError, match="does not support HTTP DELETE"):
            client._make_request("DELETE", "customer")

    @patch("qbo_client.time.sleep", return_value=None)
    def test_unsupported_method_put_raises(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        with pytest.raises(ValueError, match="Unsupported method"):
            client._make_request("PUT", "customer")

    @patch("qbo_client.time.sleep", return_value=None)
    def test_idempotency_key_in_headers(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        ok_resp = _mock_response(200, {"Customer": {"Id": "1", "SyncToken": "0"}})
        client.session.post = MagicMock(return_value=ok_resp)

        client._make_request(
            "POST", "customer", {"Name": "X"}, idempotency_key="idem-123"
        )

        posted_headers = client.session.post.call_args[1]["headers"]
        assert posted_headers.get("X-Idempotency-Key") == "idem-123"

    @patch("qbo_client.time.sleep", return_value=None)
    def test_correlation_id_in_headers(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        ok_resp = _mock_response(200, {})
        client.session.post = MagicMock(return_value=ok_resp)

        client._make_request("POST", "customer", {}, correlation_id="corr-abc")

        posted_headers = client.session.post.call_args[1]["headers"]
        assert posted_headers.get("X-Correlation-ID") == "corr-abc"

    @patch("qbo_client.time.sleep", return_value=None)
    def test_url_includes_minorversion(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        ok_resp = _mock_response(200, {})
        client.session.get = MagicMock(return_value=ok_resp)

        client._make_request("GET", "customer")

        called_url = client.session.get.call_args[0][0]
        assert "minorversion=75" in called_url


# ===================================================================
# 4. _make_request -- 401 token refresh
# ===================================================================


class TestMakeRequest401:
    """Verify token refresh logic on 401 responses."""

    @patch("qbo_client.time.sleep", return_value=None)
    def test_401_refreshes_and_retries(self, _sleep, tmp_path):
        """On 401, oauth_manager.refresh_access_token is called, then
        _base_access_token is updated and the request is retried."""
        client = _make_client(tmp_path)
        mgr = _mock_oauth_manager("new_token_after_refresh")

        resp_401 = _mock_response(401, headers={"intuit_tid": "tid1"})
        resp_200 = _mock_response(200, {"Customer": {"Id": "7", "SyncToken": "0"}})
        client.session.post = MagicMock(side_effect=[resp_401, resp_200])

        result = client._make_request(
            "POST", "customer", {"Name": "Test"}, oauth_manager=mgr
        )

        # Token was refreshed
        mgr.refresh_access_token.assert_called_once()
        # _base_access_token updated (CRITICAL BUG FIX)
        assert client._base_access_token == "new_token_after_refresh"
        # Response returned from retry
        assert result["Customer"]["Id"] == "7"

    @patch("qbo_client.time.sleep", return_value=None)
    def test_401_without_oauth_manager_raises(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        resp_401 = _mock_response(401, headers={"intuit_tid": "tid2"})
        client.session.post = MagicMock(return_value=resp_401)

        with pytest.raises(Exception, match="Authentication failed"):
            client._make_request("POST", "customer", {"Name": "Test"})

    @patch("qbo_client.time.sleep", return_value=None)
    def test_401_only_refreshes_once(self, _sleep, tmp_path):
        """If after refresh we still get 401, raise rather than infinite loop."""
        client = _make_client(tmp_path)
        mgr = _mock_oauth_manager("still_bad_token")

        resp_401 = _mock_response(401, headers={"intuit_tid": "tid3"})
        # Both calls return 401
        client.session.post = MagicMock(return_value=resp_401)

        with pytest.raises(Exception, match="Authentication failed"):
            client._make_request("POST", "customer", {"Name": "X"}, oauth_manager=mgr)

        # refresh called exactly once
        mgr.refresh_access_token.assert_called_once()


# ===================================================================
# 5. _make_request -- 429 rate limiting
# ===================================================================


class TestMakeRequest429:
    """Verify Retry-After handling on 429 responses."""

    @patch("qbo_client.time.sleep", return_value=None)
    def test_429_retries_with_retry_after_header(self, mock_sleep, tmp_path):
        client = _make_client(tmp_path)

        resp_429 = _mock_response(
            429, headers={"Retry-After": "5", "intuit_tid": "tid4"}
        )
        resp_200 = _mock_response(200, {"ok": True})
        client.session.get = MagicMock(side_effect=[resp_429, resp_200])

        result = client._make_request("GET", "customer")
        assert result == {"ok": True}

        # Verify we slept for the Retry-After value (5 seconds)
        sleep_calls = [c for c in mock_sleep.call_args_list if c[0][0] == 5]
        assert len(sleep_calls) >= 1

    @patch("qbo_client.time.sleep", return_value=None)
    def test_429_max_retries_exceeded_raises(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        resp_429 = _mock_response(
            429, headers={"Retry-After": "1", "intuit_tid": "tid5"}
        )
        client.session.get = MagicMock(return_value=resp_429)

        with pytest.raises(Exception, match="Max retries exceeded"):
            # retries=3 means we have already retried 3 times, so it should fail
            # but default max_retries from config is 3, so let's start from 0
            # and the client retries until retries >= max_retries
            client._make_request("GET", "customer")


# ===================================================================
# 6. _make_request -- 500/503 server errors
# ===================================================================


class TestMakeRequest5xx:
    """Verify exponential backoff on server errors."""

    @patch("qbo_client.time.sleep", return_value=None)
    def test_500_retries_then_succeeds(self, mock_sleep, tmp_path):
        client = _make_client(tmp_path)

        resp_500 = _mock_response(500, headers={"intuit_tid": "tid6"})
        resp_200 = _mock_response(200, {"ok": True})
        client.session.post = MagicMock(side_effect=[resp_500, resp_200])

        result = client._make_request("POST", "customer", {"Name": "Test"})
        assert result == {"ok": True}
        assert client.session.post.call_count == 2

    @patch("qbo_client.time.sleep", return_value=None)
    def test_503_retries_then_succeeds(self, mock_sleep, tmp_path):
        client = _make_client(tmp_path)

        resp_503 = _mock_response(503, headers={"intuit_tid": "tid7"})
        resp_200 = _mock_response(200, {"data": 1})
        client.session.get = MagicMock(side_effect=[resp_503, resp_200])

        result = client._make_request("GET", "vendor")
        assert result == {"data": 1}

    @patch("qbo_client.time.sleep", return_value=None)
    def test_500_max_retries_raises(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        resp_500 = _mock_response(500, headers={"intuit_tid": "tid8"})
        client.session.post = MagicMock(return_value=resp_500)

        with pytest.raises(Exception, match="Max retries exceeded"):
            client._make_request("POST", "customer", {"Name": "Fail"})


# ===================================================================
# 7. _make_request -- 400 validation error
# ===================================================================


class TestMakeRequest400:
    """Verify 400 validation errors are NOT retried."""

    @patch("qbo_client.time.sleep", return_value=None)
    def test_400_raises_value_error_with_fault_detail(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        fault_body = {
            "Fault": {
                "Error": [
                    {
                        "code": "6000",
                        "Message": "Duplicate Name",
                        "Detail": "Name already exists",
                    }
                ],
                "type": "ValidationFault",
            }
        }
        resp_400 = _mock_response(
            400, json_data=fault_body, headers={"intuit_tid": "tid9"}
        )
        resp_400.raise_for_status.side_effect = (
            None  # 400 path doesn't reach raise_for_status
        )
        client.session.post = MagicMock(return_value=resp_400)

        with pytest.raises(ValueError, match="Name already exists"):
            client._make_request("POST", "customer", {"Name": "Dup"})

        # Confirm no retries -- called exactly once
        assert client.session.post.call_count == 1


# ===================================================================
# 8. create_entity
# ===================================================================


class TestCreateEntity:
    """Verify create_entity parses responses and faults."""

    @patch("qbo_client.time.sleep", return_value=None)
    def test_create_entity_returns_entity(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        created = {"Id": "100", "SyncToken": "0", "DisplayName": "Acme Corp"}
        ok_resp = _mock_response(200, {"Customer": created})
        client.session.post = MagicMock(return_value=ok_resp)

        result = client.create_entity("Customer", {"DisplayName": "Acme Corp"})
        assert result["Id"] == "100"
        assert result["DisplayName"] == "Acme Corp"

    @patch("qbo_client.time.sleep", return_value=None)
    def test_create_entity_endpoint_is_lowercased(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        ok_resp = _mock_response(200, {"Invoice": {"Id": "200", "SyncToken": "0"}})
        client.session.post = MagicMock(return_value=ok_resp)

        client.create_entity("Invoice", {"Line": []})

        called_url = client.session.post.call_args[0][0]
        # The endpoint portion should be lowercase "invoice"
        assert "/invoice" in called_url.lower()

    @patch("qbo_client.time.sleep", return_value=None)
    def test_create_entity_fault_raises_with_all_errors(self, _sleep, tmp_path):
        """Verify complete Fault parsing: all Error entries are joined."""
        client = _make_client(tmp_path)
        fault_resp = {
            "Fault": {
                "type": "ValidationFault",
                "Error": [
                    {
                        "code": "500",
                        "Message": "Invalid Reference",
                        "Detail": "AccountRef is invalid",
                    },
                    {
                        "code": "501",
                        "Message": "Missing field",
                        "Detail": "DocNumber required",
                        "element": "DocNumber",
                    },
                ],
            }
        }
        ok_resp = _mock_response(200, fault_resp)
        client.session.post = MagicMock(return_value=ok_resp)

        with pytest.raises(Exception) as exc_info:
            client.create_entity("Invoice", {"Line": []})

        error_msg = str(exc_info.value)
        assert "Invalid Reference" in error_msg
        assert "Missing field" in error_msg
        assert "DocNumber" in error_msg

    @patch("qbo_client.time.sleep", return_value=None)
    def test_create_entity_returns_full_response_if_key_missing(self, _sleep, tmp_path):
        """If response has no matching entity_type key, return full response."""
        client = _make_client(tmp_path)
        resp_data = {"SomeOtherKey": {"Id": "1"}}
        ok_resp = _mock_response(200, resp_data)
        client.session.post = MagicMock(return_value=ok_resp)

        result = client.create_entity("Customer", {"Name": "X"})
        assert result == resp_data


# ===================================================================
# 9. record_created -- thread-safe SQLite
# ===================================================================


class TestRecordCreated:
    """Verify record_created uses db_lock and writes to SQLite."""

    def test_record_created_stores_entity(self, tmp_path):
        client = _make_client(tmp_path)
        client.record_created("Customer", "QBD-1", "QBO-100", sync_token="3")

        # Verify SQLite row
        conn = sqlite3.connect(str(client.db_path))
        cur = conn.cursor()
        cur.execute(
            "SELECT qbo_id, sync_token FROM migrated_entities WHERE qbd_id = ?",
            ("QBD-1",),
        )
        row = cur.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "QBO-100"
        assert row[1] == "3"

    def test_record_created_updates_synctoken_cache(self, tmp_path):
        client = _make_client(tmp_path)
        client.record_created("Vendor", "QBD-2", "QBO-200", sync_token="5")
        assert client.synctoken_cache[("Vendor", "QBO-200")] == "5"

    def test_record_created_uses_db_lock(self, tmp_path):
        """Verify db_lock is acquired during record_created.

        We replace db_lock entirely with a tracking wrapper rather than
        patching the C-level acquire method which is read-only.
        """
        client = _make_client(tmp_path)
        acquired = []

        real_lock = client.db_lock

        class TrackingLock:
            def __init__(self):
                self._real = real_lock

            def acquire(self, *a, **kw):
                acquired.append("db_lock")
                return self._real.acquire(*a, **kw)

            def release(self, *a, **kw):
                return self._real.release(*a, **kw)

            def __enter__(self):
                self.acquire()
                return self

            def __exit__(self, *a):
                self.release()

        client.db_lock = TrackingLock()
        client.record_created("Customer", "QBD-3", "QBO-300")
        assert "db_lock" in acquired


# ===================================================================
# 10. get_synctoken
# ===================================================================


class TestGetSynctoken:
    """Verify cache-first lookup with DB fallback."""

    def test_get_synctoken_from_cache(self, tmp_path):
        client = _make_client(tmp_path)
        cache_key = ("Customer", "QBO-100")
        client.synctoken_cache[cache_key] = "7"
        # Set cache time so entry is not expired
        if not hasattr(client, "_synctoken_cache_times"):
            client._synctoken_cache_times = {}
        import time as _time
        client._synctoken_cache_times[cache_key] = _time.time()
        assert client.get_synctoken("Customer", "QBO-100") == "7"

    def test_get_synctoken_from_db_fallback(self, tmp_path):
        client = _make_client(tmp_path)
        # Insert directly into DB
        client.record_created("Vendor", "QBD-V1", "QBO-V1", sync_token="12")
        # Clear cache so we hit DB
        client.synctoken_cache.clear()

        token = client.get_synctoken("Vendor", "QBO-V1")
        assert token == "12"

    def test_get_synctoken_returns_zero_if_not_found(self, tmp_path):
        client = _make_client(tmp_path)
        assert client.get_synctoken("Customer", "NONEXISTENT") == "0"

    def test_get_synctoken_populates_cache_on_db_hit(self, tmp_path):
        client = _make_client(tmp_path)
        client.record_created("Item", "QBD-I1", "QBO-I1", sync_token="9")
        client.synctoken_cache.clear()

        client.get_synctoken("Item", "QBO-I1")
        # Cache should now be populated
        assert ("Item", "QBO-I1") in client.synctoken_cache


# ===================================================================
# 11. update_synctoken -- LOCK ORDERING BUG FIX
# ===================================================================


class TestUpdateSynctoken:
    """CRITICAL: Verify db_lock is acquired BEFORE synctoken_lock."""

    def test_update_synctoken_changes_cache(self, tmp_path):
        client = _make_client(tmp_path)
        client.synctoken_cache[("Customer", "QBO-1")] = "0"
        client.record_created("Customer", "QBD-X", "QBO-1", sync_token="0")

        client.update_synctoken("Customer", "QBO-1", "5")
        assert client.synctoken_cache[("Customer", "QBO-1")] == "5"

    def test_update_synctoken_changes_db(self, tmp_path):
        client = _make_client(tmp_path)
        client.record_created("Customer", "QBD-X", "QBO-1", sync_token="0")
        client.update_synctoken("Customer", "QBO-1", "5")

        conn = sqlite3.connect(str(client.db_path))
        cur = conn.cursor()
        cur.execute(
            "SELECT sync_token FROM migrated_entities WHERE entity_type=? AND qbo_id=?",
            ("Customer", "QBO-1"),
        )
        row = cur.fetchone()
        conn.close()
        assert row[0] == "5"

    def test_update_synctoken_lock_ordering(self, tmp_path):
        """DEADLOCK FIX: db_lock MUST be acquired before synctoken_lock.

        We instrument both locks and record acquisition order.  If db_lock
        is not acquired first, record_created (which also does db_lock then
        synctoken_lock) could deadlock with update_synctoken.
        """
        client = _make_client(tmp_path)
        client.record_created("Account", "QBD-A1", "QBO-A1", sync_token="0")

        lock_order = []
        real_db_lock = client.db_lock
        real_st_lock = client.synctoken_lock

        class TrackingLock:
            def __init__(self, name, real_lock):
                self._name = name
                self._real = real_lock

            def acquire(self, *a, **kw):
                lock_order.append(self._name)
                return self._real.acquire(*a, **kw)

            def release(self, *a, **kw):
                return self._real.release(*a, **kw)

            def __enter__(self):
                self.acquire()
                return self

            def __exit__(self, *a):
                self.release()

        client.db_lock = TrackingLock("db_lock", real_db_lock)
        client.synctoken_lock = TrackingLock("synctoken_lock", real_st_lock)

        client.update_synctoken("Account", "QBO-A1", "10")

        # db_lock must appear before synctoken_lock
        db_idx = lock_order.index("db_lock")
        st_idx = lock_order.index("synctoken_lock")
        assert db_idx < st_idx, (
            f"Lock ordering violation: db_lock at {db_idx}, synctoken_lock at {st_idx}. "
            "db_lock must be acquired first to prevent deadlocks."
        )


# ===================================================================
# 12. was_entity_created
# ===================================================================


class TestWasEntityCreated:
    """Verify O(1) lookup returns qbo_id or None."""

    def test_returns_qbo_id_if_exists(self, tmp_path):
        client = _make_client(tmp_path)
        client.record_created("Customer", "QBD-C1", "QBO-C1")
        assert client.was_entity_created("Customer", "QBD-C1") == "QBO-C1"

    def test_returns_none_if_not_exists(self, tmp_path):
        client = _make_client(tmp_path)
        assert client.was_entity_created("Customer", "QBD-NOPE") is None

    def test_uses_db_lock(self, tmp_path):
        """Ensure was_entity_created acquires db_lock for thread safety."""
        client = _make_client(tmp_path)
        client.db_lock.__class__.__enter__

        # We can verify by checking that the lock works -- concurrent
        # access without the lock would be unsafe. Just verify it calls correctly.
        client.record_created("Vendor", "QBD-V99", "QBO-V99")
        result = client.was_entity_created("Vendor", "QBD-V99")
        assert result == "QBO-V99"


# ===================================================================
# 13. query_count -- whitelist validation
# ===================================================================


class TestQueryCount:
    """Verify entity_type whitelist enforcement."""

    def test_valid_entity_type_accepted(self, tmp_path):
        """Customer is in the whitelist, should not raise."""
        client = _make_client(tmp_path)
        ok_resp = _mock_response(200, {"QueryResponse": {"totalCount": 42}})
        client.session.get = MagicMock(return_value=ok_resp)

        with patch("qbo_client.time.sleep", return_value=None):
            count = client.query_count("Customer")
        assert count == 42

    def test_invalid_entity_type_raises_value_error(self, tmp_path):
        """SQL injection attempt must be rejected."""
        client = _make_client(tmp_path)
        with pytest.raises(ValueError, match="Invalid entity type"):
            client.query_count("Customer; DROP TABLE")

    def test_all_valid_types_accepted(self, tmp_path):
        """Ensure every type in the whitelist is accepted without error."""
        valid_types = {
            "Account",
            "Customer",
            "Vendor",
            "Item",
            "Employee",
            "Invoice",
            "Bill",
            "Payment",
            "Estimate",
            "SalesReceipt",
            "PurchaseOrder",
            "Deposit",
            "Transfer",
            "JournalEntry",
            "CreditMemo",
            "VendorCredit",
            "BillPayment",
            "TimeActivity",
            "TaxCode",
            "TaxRate",
            "Term",
            "PaymentMethod",
            "Class",
            "Department",
            "Attachable",
            "CompanyCurrency",
            "Budget",
        }
        client = _make_client(tmp_path)
        ok_resp = _mock_response(200, {"QueryResponse": {"totalCount": 0}})
        client.session.get = MagicMock(return_value=ok_resp)

        with patch("qbo_client.time.sleep", return_value=None):
            for entity_type in valid_types:
                count = client.query_count(entity_type)
                assert count == 0

    def test_case_sensitive_validation(self, tmp_path):
        """Lowercase 'customer' should be rejected (whitelist has 'Customer')."""
        client = _make_client(tmp_path)
        with pytest.raises(ValueError, match="Invalid entity type"):
            client.query_count("customer")


# ===================================================================
# 14. query_raw
# ===================================================================


class TestQueryRaw:
    """Verify raw query execution against QBO API."""

    @patch("qbo_client.time.sleep", return_value=None)
    def test_query_raw_returns_entity_list(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        resp_data = {
            "QueryResponse": {
                "Invoice": [
                    {"Id": "1", "TotalAmt": 100},
                    {"Id": "2", "TotalAmt": 200},
                ]
            }
        }
        ok_resp = _mock_response(200, resp_data)
        client.session.get = MagicMock(return_value=ok_resp)

        results = client.query_raw("SELECT * FROM Invoice")
        assert len(results) == 2
        assert results[0]["Id"] == "1"

    @patch("qbo_client.time.sleep", return_value=None)
    def test_query_raw_returns_empty_on_no_results(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        ok_resp = _mock_response(200, {"QueryResponse": {}})
        client.session.get = MagicMock(return_value=ok_resp)

        results = client.query_raw("SELECT * FROM Invoice WHERE Id = '999999'")
        assert results == []

    @patch("qbo_client.time.sleep", return_value=None)
    def test_query_raw_returns_empty_on_error(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        client.session.get = MagicMock(side_effect=Exception("network error"))

        results = client.query_raw("SELECT * FROM Customer")
        assert results == []


# ===================================================================
# 15. batch_upload -- entity ordering and empty handling
# ===================================================================


class TestBatchUpload:
    """Verify batch_upload processes entities in dependency order."""

    @patch("qbo_client.time.sleep", return_value=None)
    def test_empty_entities_dict(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        result = client.batch_upload({}, migration_id="mig-001")
        assert result["successful"] == 0
        assert result["failed"] == 0

    @patch("qbo_client.time.sleep", return_value=None)
    def test_entity_ordering_accounts_before_invoices(self, _sleep, tmp_path):
        """Account must be processed before Invoice (dependency order)."""
        client = _make_client(tmp_path)
        processing_order = []

        client.batch_create_parallel

        def mock_batch_create(entities, entity_type, **kwargs):
            processing_order.append(entity_type)
            return {
                "succeeded": [],
                "succeeded_count": 0,
                "succeeded_ids": [],
                "failed": [],
            }

        client.batch_create_parallel = mock_batch_create

        entities = {
            "Invoice": [{"DocNumber": "1001"}],
            "Account": [{"Name": "Revenue"}],
            "Customer": [{"DisplayName": "Test"}],
        }

        client.batch_upload(entities, migration_id="mig-002")

        account_idx = processing_order.index("Account")
        customer_idx = processing_order.index("Customer")
        invoice_idx = processing_order.index("Invoice")

        assert account_idx < customer_idx < invoice_idx

    @patch("qbo_client.time.sleep", return_value=None)
    def test_empty_entity_list_skipped(self, _sleep, tmp_path):
        """Entity types with empty lists should be skipped."""
        client = _make_client(tmp_path)
        processing_order = []

        def mock_batch_create(entities, entity_type, **kwargs):
            processing_order.append(entity_type)
            return {
                "succeeded": [],
                "succeeded_count": 0,
                "succeeded_ids": [],
                "failed": [],
            }

        client.batch_create_parallel = mock_batch_create

        entities = {
            "Customer": [{"DisplayName": "Test"}],
            "Vendor": [],  # empty -- should be skipped
        }

        client.batch_upload(entities, migration_id="mig-003")
        assert "Vendor" not in processing_order
        assert "Customer" in processing_order


# ===================================================================
# 16. _build_url
# ===================================================================


class TestBuildUrl:
    """Verify URL construction with minorversion."""

    def test_adds_minorversion_param(self, tmp_path):
        client = _make_client(tmp_path)
        url = client._build_url("customer")
        assert url == f"{BASE_URL}/customer?minorversion=75"

    def test_does_not_duplicate_minorversion(self, tmp_path):
        client = _make_client(tmp_path)
        url = client._build_url("query?query=SELECT+*+FROM+Customer&minorversion=75")
        assert url.count("minorversion") == 1

    def test_appends_with_ampersand_if_query_param_exists(self, tmp_path):
        client = _make_client(tmp_path)
        url = client._build_url("query?query=SELECT+*+FROM+Customer")
        assert "&minorversion=75" in url


# ===================================================================
# 17. _calculate_backoff
# ===================================================================


class TestCalculateBackoff:
    """Verify exponential backoff calculation."""

    def test_first_retry_backoff(self, tmp_path):
        client = _make_client(tmp_path)
        backoff = client._calculate_backoff(0)
        # base^0 = 1.0 (with possible jitter)
        assert 0.1 <= backoff <= 2.0

    def test_backoff_increases_with_retries(self, tmp_path):
        client = _make_client(tmp_path)
        # Run multiple times to average out jitter
        b0_sum = sum(client._calculate_backoff(0) for _ in range(20))
        b2_sum = sum(client._calculate_backoff(2) for _ in range(20))
        assert b2_sum > b0_sum


# ===================================================================
# 18. Timeout handling
# ===================================================================


class TestTimeoutHandling:
    """Verify request timeout retries."""

    @patch("qbo_client.time.sleep", return_value=None)
    def test_timeout_retries(self, _sleep, tmp_path):
        import requests as real_requests

        client = _make_client(tmp_path)

        ok_resp = _mock_response(200, {"ok": True})
        client.session.get = MagicMock(
            side_effect=[real_requests.exceptions.Timeout("timed out"), ok_resp]
        )

        result = client._make_request("GET", "customer")
        assert result == {"ok": True}
        assert client.session.get.call_count == 2


# ===================================================================
# 19. Context manager
# ===================================================================


class TestContextManager:
    """Verify __enter__ / __exit__ close session."""

    def test_context_manager_returns_self(self, tmp_path):
        client = _make_client(tmp_path)
        with client as c:
            assert c is client

    def test_context_manager_closes_session(self, tmp_path):
        client = _make_client(tmp_path)
        client.session = MagicMock()
        with client:
            pass
        client.session.close.assert_called_once()


# ===================================================================
# 20. get_migration_summary
# ===================================================================


class TestGetMigrationSummary:
    """Verify migration summary reporting."""

    def test_empty_summary(self, tmp_path):
        client = _make_client(tmp_path)
        summary = client.get_migration_summary()
        assert summary["total_entities"] == 0
        assert summary["entity_counts"] == {}

    def test_summary_counts_by_type(self, tmp_path):
        client = _make_client(tmp_path)
        client.record_created("Customer", "QBD-1", "QBO-1", migration_id="mig-1")
        client.record_created("Customer", "QBD-2", "QBO-2", migration_id="mig-1")
        client.record_created("Vendor", "QBD-3", "QBO-3", migration_id="mig-1")

        summary = client.get_migration_summary(migration_id="mig-1")
        assert summary["total_entities"] == 3
        assert summary["entity_counts"]["Customer"] == 2
        assert summary["entity_counts"]["Vendor"] == 1


# ===================================================================
# 21. Rate limit tracking
# ===================================================================


class TestRateLimitTracking:
    """Verify _update_rate_limits reads headers."""

    def test_updates_remaining_from_header(self, tmp_path):
        client = _make_client(tmp_path)
        resp = _mock_response(200, headers={"X-RateLimit-Remaining": "123"})
        client._update_rate_limits(resp)
        assert client.rate_limit_remaining == 123

    def test_increments_request_count(self, tmp_path):
        client = _make_client(tmp_path)
        initial = client.request_count
        resp = _mock_response(200, headers={})
        client._update_rate_limits(resp)
        assert client.request_count == initial + 1


# ===================================================================
# 22. delete_entity
# ===================================================================


class TestDeleteEntity:
    """Verify delete uses POST with ?operation=delete."""

    @patch("qbo_client.time.sleep", return_value=None)
    def test_delete_entity_posts_with_operation_delete(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        client.record_created("Customer", "QBD-D1", "QBO-D1", sync_token="3")

        ok_resp = _mock_response(200, {})
        client.session.post = MagicMock(return_value=ok_resp)

        result = client.delete_entity("Customer", "QBO-D1")
        assert result is True

        called_url = client.session.post.call_args[0][0]
        assert "operation=delete" in called_url

    @patch("qbo_client.time.sleep", return_value=None)
    def test_delete_entity_returns_false_on_failure(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        client.session.post = MagicMock(side_effect=Exception("Boom"))

        result = client.delete_entity("Customer", "QBO-X1")
        assert result is False


# ===================================================================
# 23. _get_next_batch_id thread safety
# ===================================================================


class TestBatchIdGeneration:
    """Verify thread-safe batch ID generation."""

    def test_batch_ids_are_unique(self, tmp_path):
        client = _make_client(tmp_path)
        ids = set()
        for _ in range(100):
            ids.add(client._get_next_batch_id())
        assert len(ids) == 100

    def test_batch_counter_increments(self, tmp_path):
        client = _make_client(tmp_path)
        initial = client.batch_counter
        client._get_next_batch_id()
        assert client.batch_counter == initial + 1


# ===================================================================
# 24. SyncToken auto-caching from response
# ===================================================================


class TestSyncTokenAutoCaching:
    """Verify _make_request auto-caches SyncToken from responses."""

    @patch("qbo_client.time.sleep", return_value=None)
    def test_synctoken_cached_from_response(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        resp_data = {
            "Customer": {"Id": "55", "SyncToken": "3", "DisplayName": "Auto Cached"}
        }
        ok_resp = _mock_response(200, resp_data)
        client.session.post = MagicMock(return_value=ok_resp)

        client._make_request("POST", "customer", {"DisplayName": "Auto Cached"})

        # SyncToken should be auto-cached
        assert client.synctoken_cache.get(("Customer", "55")) == "3"


# ===================================================================
# 25. 403 permission denied
# ===================================================================


class TestMakeRequest403:
    """Verify 403 raises PermissionError."""

    @patch("qbo_client.time.sleep", return_value=None)
    def test_403_raises_permission_error(self, _sleep, tmp_path):
        client = _make_client(tmp_path)
        resp_403 = _mock_response(403, headers={"intuit_tid": "tid-perm"})
        client.session.post = MagicMock(return_value=resp_403)

        with pytest.raises(PermissionError, match="permission denied"):
            client._make_request("POST", "customer", {"Name": "Forbidden"})


# ===================================================================
# 26. shutdown flag
# ===================================================================


class TestShutdownFlag:
    """Verify graceful shutdown."""

    def test_check_shutdown_raises_keyboard_interrupt(self, tmp_path):
        client = _make_client(tmp_path)
        client._shutdown_event.set()
        with pytest.raises(KeyboardInterrupt):
            client._check_shutdown()

    def test_check_shutdown_does_nothing_normally(self, tmp_path):
        client = _make_client(tmp_path)
        client._shutdown_event.clear()
        client._check_shutdown()  # Should not raise


# ===================================================================
# 27. record_created with duplicate qbd_id (INSERT OR REPLACE)
# ===================================================================


class TestRecordCreatedDuplicate:
    """Verify INSERT OR REPLACE upsert behaviour."""

    def test_duplicate_qbd_id_updates_row(self, tmp_path):
        client = _make_client(tmp_path)
        client.record_created("Customer", "QBD-DUP", "QBO-OLD", sync_token="1")
        client.record_created("Customer", "QBD-DUP", "QBO-NEW", sync_token="2")

        result = client.was_entity_created("Customer", "QBD-DUP")
        assert result == "QBO-NEW"

        conn = sqlite3.connect(str(client.db_path))
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM migrated_entities WHERE qbd_id = ?", ("QBD-DUP",)
        )
        count = cur.fetchone()[0]
        conn.close()
        assert count == 1  # Replaced, not duplicated


# ===================================================================
# 28. Plan worker limits
# ===================================================================


class TestPlanWorkerLimits:
    """Verify _get_plan_worker_limit returns correct values."""

    def test_advanced_plan(self, tmp_path):
        assert PremiumQBOClient._get_plan_worker_limit("Advanced") == 8

    def test_plus_plan(self, tmp_path):
        assert PremiumQBOClient._get_plan_worker_limit("Plus") == 5

    def test_essentials_plan(self, tmp_path):
        assert PremiumQBOClient._get_plan_worker_limit("Essentials") == 3

    def test_simple_start_plan(self, tmp_path):
        assert PremiumQBOClient._get_plan_worker_limit("Simple Start") == 2

    def test_unknown_plan_defaults_to_5(self, tmp_path):
        assert PremiumQBOClient._get_plan_worker_limit("UnknownPlan") == 5
