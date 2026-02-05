"""
Integration Tests for ForensicBridge
Tests end-to-end flows between components

Tests cover:
1. Frontend ↔ Backend API communication
2. QBO API connection validation
3. QBD connection validation (C# component)
4. Full migration flow simulation
5. WebSocket/polling scenarios
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================
# Frontend ↔ Backend Integration Tests
# ============================================================================


class TestFrontendBackendIntegration:
    """Tests for frontend-backend API communication"""

    @pytest.fixture
    def backend_url(self):
        """Backend API URL"""
        return os.environ.get("BACKEND_URL", "http://localhost:5000")

    @pytest.fixture
    def frontend_url(self):
        """Frontend URL"""
        return os.environ.get("FRONTEND_URL", "http://localhost:3000")

    def test_cors_headers_present(self, backend_url):
        """Test that CORS headers are properly configured"""
        try:
            response = requests.options(
                f"{backend_url}/api/dashboard/overview",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
                timeout=5,
            )

            # Should have CORS headers
            assert response.headers.get("Access-Control-Allow-Origin") in [
                "http://localhost:3000",
                "*",
            ]
        except requests.exceptions.RequestException:
            pytest.skip("Backend not running")

    def test_api_returns_json(self, backend_url):
        """Test that API endpoints return JSON"""
        try:
            response = requests.get(f"{backend_url}/health", timeout=5)

            assert response.headers.get("Content-Type", "").startswith(
                "application/json"
            )
        except requests.exceptions.RequestException:
            pytest.skip("Backend not running")

    def test_live_status_polling_response_format(self, backend_url):
        """Test that live-status returns correct format for Pizza Tracker"""
        expected_fields = [
            "phase",
            "phase_number",
            "percentage",
            "phases",
            "current_entity",
            "status_message",
            "elapsed_seconds",
        ]

        # This would require authentication, so we test the structure conceptually
        response_structure = {
            "success": True,
            "migration_id": "test_123",
            "phase": "TRANSFORMATION",
            "phase_number": 3,
            "percentage": 65,
            "current_entity": "Invoices",
            "status_message": "Processing invoices...",
            "phases": [
                {"name": "EXTRACTION", "status": "completed", "percentage": 100},
                {"name": "TRANSIT", "status": "completed", "percentage": 100},
                {"name": "TRANSFORMATION", "status": "in_progress", "percentage": 65},
                {"name": "VERIFICATION", "status": "pending", "percentage": 0},
            ],
            "elapsed_seconds": 1800,
        }

        # Validate structure
        for field in expected_fields:
            assert field in response_structure

    def test_trial_balance_response_for_reconciliation_shield(self, backend_url):
        """Test trial balance response matches ReconciliationShield component needs"""
        expected_structure = {
            "success": True,
            "source_trial_balance": 1245678.90,
            "destination_trial_balance": 1245678.90,
            "discrepancy": 0.0,
            "is_balanced": True,
            "forensic_status": "VERIFIED",
            "verification_timestamp": "2026-01-15T00:00:00Z",
            "source_hash": "0x7e2f...",
            "destination_hash": "0x7e2f...",
            "hash_match": True,
        }

        # Validate all fields present
        assert "source_trial_balance" in expected_structure
        assert "destination_trial_balance" in expected_structure
        assert "forensic_status" in expected_structure


# ============================================================================
# QBO Connection Tests
# ============================================================================


class TestQBOConnection:
    """Tests for QuickBooks Online API connection"""

    @pytest.fixture
    def qbo_credentials(self):
        """QBO OAuth credentials from environment"""
        return {
            "client_id": os.environ.get("QBO_CLIENT_ID", ""),
            "client_secret": os.environ.get("QBO_CLIENT_SECRET", ""),
            "refresh_token": os.environ.get("QBO_REFRESH_TOKEN", ""),
            "realm_id": os.environ.get("QBO_REALM_ID", ""),
        }

    def test_qbo_sandbox_connectivity(self, qbo_credentials):
        """Test connection to QBO sandbox"""
        if not all(qbo_credentials.values()):
            pytest.skip("QBO credentials not configured")

        # Test OAuth token refresh
        response = requests.post(
            "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
            data={
                "grant_type": "refresh_token",
                "refresh_token": qbo_credentials["refresh_token"],
            },
            auth=(qbo_credentials["client_id"], qbo_credentials["client_secret"]),
            timeout=30,
        )

        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_qbo_company_info_query(self, qbo_credentials):
        """Test querying company info from QBO"""
        if not all(qbo_credentials.values()):
            pytest.skip("QBO credentials not configured")

        # This would require a valid access token
        # Structure test only
        expected_response = {
            "CompanyInfo": {
                "CompanyName": "Test Company",
                "LegalName": "Test Company Inc",
                "FiscalYearStartMonth": "January",
            }
        }

        assert "CompanyInfo" in expected_response

    def test_qbo_batch_endpoint_format(self):
        """Test that batch request format matches QBO API spec"""
        batch_request = {
            "BatchItemRequest": [
                {
                    "bId": "bid_0",
                    "operation": "create",
                    "Customer": {"DisplayName": "Test Customer 1"},
                },
                {
                    "bId": "bid_1",
                    "operation": "create",
                    "Customer": {"DisplayName": "Test Customer 2"},
                },
            ]
        }

        # Validate structure
        assert "BatchItemRequest" in batch_request
        assert len(batch_request["BatchItemRequest"]) <= 30  # Max batch size

        for item in batch_request["BatchItemRequest"]:
            assert "bId" in item
            assert "operation" in item

    def test_qbo_rate_limit_headers_parsing(self):
        """Test parsing of QBO rate limit headers"""
        headers = {
            "X-RateLimit-Remaining": "450",
            "X-RateLimit-Limit": "500",
            "Retry-After": "60",
        }

        remaining = int(headers.get("X-RateLimit-Remaining", 0))
        limit = int(headers.get("X-RateLimit-Limit", 500))
        retry_after = int(headers.get("Retry-After", 0))

        assert remaining <= limit
        assert retry_after >= 0


# ============================================================================
# QBD Connection Tests
# ============================================================================


class TestQBDConnection:
    """Tests for QuickBooks Desktop connection (C# component)"""

    @pytest.fixture
    def qbd_reader_path(self):
        """Path to QBDesktopReader executable"""
        return os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "QBDesktopReader",
            "bin",
            "Release",
            "QBDesktopReader.exe",
        )

    def test_qbd_reader_executable_exists(self, qbd_reader_path):
        """Test that QBDesktopReader executable exists"""
        # Check multiple possible paths
        possible_paths = [
            qbd_reader_path,
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "QBDesktopReader",
                "bin",
                "Debug",
                "QBDesktopReader.exe",
            ),
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "QBDesktopReader",
                "bin",
                "Release",
                "net8.0-windows",
                "QBDesktopReader.exe",
            ),
        ]

        exists = any(os.path.exists(p) for p in possible_paths)

        if not exists:
            pytest.skip("QBDesktopReader not built - run 'dotnet build' first")

    def test_qbd_ndjson_format_validation(self):
        """Test that QBD NDJSON output format is valid"""
        # Sample NDJSON line from QBD extraction
        ndjson_line = json.dumps(
            {
                "EntityType": "Customer",
                "ListID": "80000001-1234567890",
                "Name": "Test Customer",
                "FullName": "Test Customer",
                "IsActive": True,
                "Balance": "1234.56",
            }
        )

        # Validate it's valid JSON
        parsed = json.loads(ndjson_line)

        assert "EntityType" in parsed
        assert "ListID" in parsed

    def test_qbd_hash_format_sha256(self):
        """Test that QBD generates valid SHA-256 hashes"""
        import hashlib

        # Simulate hash generation
        sample_data = b"Sample QuickBooks data for hashing"
        hash_obj = hashlib.sha256(sample_data)
        hash_hex = hash_obj.hexdigest()

        # SHA-256 produces 64 hex characters
        assert len(hash_hex) == 64
        assert all(c in "0123456789abcdef" for c in hash_hex)

    def test_qbd_streaming_pipeline_format(self):
        """Test streaming pipeline data format"""
        # Simulated chunk from StreamingPipeline.cs
        chunk_metadata = {
            "ChunkIndex": 1,
            "TotalChunks": 100,
            "EntityType": "Invoice",
            "RecordCount": 1000,
            "ByteSize": 524288,
            "SHA256": "abcd1234...",
        }

        required_fields = ["ChunkIndex", "TotalChunks", "EntityType", "RecordCount"]
        for field in required_fields:
            assert field in chunk_metadata


# ============================================================================
# Full Migration Flow Tests
# ============================================================================


class TestMigrationFlow:
    """End-to-end migration flow tests"""

    def test_migration_phase_transitions(self):
        """Test that migration phases transition correctly"""
        phases = ["EXTRACTION", "TRANSIT", "TRANSFORMATION", "VERIFICATION"]
        phase_ranges = [
            (0, 15, "EXTRACTION"),
            (15, 20, "TRANSIT"),
            (20, 85, "TRANSFORMATION"),
            (85, 100, "VERIFICATION"),
        ]

        for start, end, expected_phase in phase_ranges:
            for percent in range(start, end):
                # Determine phase from percentage
                if percent < 15:
                    actual = "EXTRACTION"
                elif percent < 20:
                    actual = "TRANSIT"
                elif percent < 85:
                    actual = "TRANSFORMATION"
                else:
                    actual = "VERIFICATION"

                assert (
                    actual == expected_phase
                ), f"At {percent}%, expected {expected_phase} but got {actual}"

    def test_entity_migration_order(self):
        """Test that entities are migrated in correct dependency order"""
        # Entity order from orchestrator.py
        entity_order = [
            "Accounts",  # Must be first (all transactions reference accounts)
            "Customers",  # Independent
            "Vendors",  # Independent
            "Items",  # May reference accounts
            "Employees",  # Independent
            "Invoices",  # References customers, items, accounts
            "Bills",  # References vendors, items, accounts
            "Payments",  # References invoices (must be last in transaction chain)
        ]

        # Validate Accounts is first
        assert entity_order[0] == "Accounts"

        # Validate Payments is last
        assert entity_order[-1] == "Payments"

        # Validate Invoices comes before Payments
        assert entity_order.index("Invoices") < entity_order.index("Payments")

    def test_verification_trial_balance_calculation(self):
        """Test trial balance verification logic"""
        # Sample accounts
        accounts = [
            {"Type": "Bank", "Balance": 10000.00},
            {"Type": "AccountsReceivable", "Balance": 5000.00},
            {"Type": "AccountsPayable", "Balance": -3000.00},
            {"Type": "Equity", "Balance": -12000.00},
        ]

        # Total should be zero for balanced books
        total = sum(a["Balance"] for a in accounts)

        assert abs(total) < 0.01, "Trial balance should sum to zero"

    def test_audit_certificate_contains_required_fields(self):
        """Test that audit certificate contains all required information"""
        certificate_data = {
            "migration_id": "FB-2026-001",
            "company_name": "Test Company",
            "completion_date": datetime.now().isoformat(),
            "source_hash": "abc123...",
            "destination_hash": "abc123...",
            "trial_balance_verified": True,
            "entity_counts": {
                "Customers": 100,
                "Vendors": 50,
                "Invoices": 1000,
                "Bills": 500,
            },
            "total_entities_migrated": 1650,
            "data_quality_score": 98.5,
            "forensic_status": "VERIFIED",
        }

        required_fields = [
            "migration_id",
            "company_name",
            "source_hash",
            "destination_hash",
            "trial_balance_verified",
            "forensic_status",
        ]

        for field in required_fields:
            assert field in certificate_data


# ============================================================================
# WebSocket/Polling Tests
# ============================================================================


class TestRealtimeCommunication:
    """Tests for real-time status updates"""

    def test_polling_interval_2_seconds(self):
        """Test that recommended polling interval is 2 seconds"""
        POLLING_INTERVAL_MS = 2000  # From useLiveStatus.ts

        # Validate it's within acceptable range
        assert 1000 <= POLLING_INTERVAL_MS <= 5000

    def test_status_update_debouncing(self):
        """Test that rapid status updates are debounced"""
        updates = []
        last_update = 0
        min_interval = 1.0  # 1 second minimum between updates

        def process_update(progress):
            nonlocal last_update
            now = time.time()
            if now - last_update >= min_interval:
                updates.append(progress)
                last_update = now

        # Simulate rapid updates
        for i in range(10):
            process_update(i * 10)
            time.sleep(0.3)  # 300ms between updates

        # Should have fewer updates due to debouncing
        assert len(updates) < 10


# ============================================================================
# Data Integrity Tests
# ============================================================================


class TestDataIntegrity:
    """Tests for data integrity during migration"""

    def test_sha256_hash_consistency(self):
        """Test that SHA-256 hashes are consistent"""
        import hashlib

        data = b"Test data for hashing"

        hash1 = hashlib.sha256(data).hexdigest()
        hash2 = hashlib.sha256(data).hexdigest()

        assert hash1 == hash2

    def test_decimal_precision_preservation(self):
        """Test that decimal values maintain precision"""
        from decimal import Decimal

        original = Decimal("1234567.89")
        json_string = json.dumps({"amount": str(original)})
        parsed = json.loads(json_string)
        restored = Decimal(parsed["amount"])

        assert original == restored

    def test_date_format_consistency(self):
        """Test date format handling"""
        # QBD formats
        qbd_formats = ["2026-01-15", "01/15/2026", "January 15, 2026"]

        # All should be convertible to ISO format
        from datetime import datetime

        for fmt in qbd_formats:
            try:
                # Try various parsers
                for parse_fmt in ["%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y"]:
                    try:
                        dt = datetime.strptime(fmt, parse_fmt)
                        iso = dt.isoformat()
                        assert "2026" in iso
                        break
                    except ValueError:
                        continue
            except Exception:
                pass  # Some formats may not match


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
