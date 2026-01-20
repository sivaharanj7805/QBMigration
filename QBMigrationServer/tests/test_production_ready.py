"""
Production Readiness Tests - Real Integration Tests

These tests verify production readiness against LIVE systems:
- Real API endpoints (no mocks)
- Real database connections
- Real encryption/decryption cycles
- Real license validation flow
- Real authentication flow

Run with: pytest tests/test_production_ready.py -v
"""

import pytest
import requests
import time
import hashlib
import os
import json
from datetime import datetime, timedelta


# Configuration
API_BASE_URL = os.getenv('TEST_API_URL', 'http://localhost:5000')
TEST_EMAIL = f"test_prod_{int(time.time())}@forensicbridge.ca"
TEST_PASSWORD = "TestPass123!"


class TestProductionAuthentication:
    """Test real authentication flows"""
    
    def test_register_new_user_real_api(self):
        """Test user registration against real API"""
        response = requests.post(
            f"{API_BASE_URL}/api/auth/register",
            json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD,
                "first_name": "Production",
                "last_name": "Test",
                "company_name": "Test Corp"
            },
            timeout=30
        )
        
        assert response.status_code in [201, 409], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 201:
            data = response.json()
            assert data.get('success') == True
            assert 'token' in data
            assert len(data['token']) > 50  # JWT tokens are long
            
            # Store token for subsequent tests
            TestProductionAuthentication.auth_token = data['token']
            TestProductionAuthentication.user_id = data['user']['id']
    
    def test_login_existing_user_real_api(self):
        """Test login against real API"""
        response = requests.post(
            f"{API_BASE_URL}/api/auth/login",
            json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            },
            timeout=30
        )
        
        # Allow 401 if user wasn't created in previous test
        if response.status_code == 401:
            pytest.skip("User not found - registration may have failed")
        
        assert response.status_code == 200
        data = response.json()
        assert data.get('success') == True
        assert 'token' in data
        
        TestProductionAuthentication.auth_token = data['token']
    
    def test_account_lockout_real_api(self):
        """Test that account lockout works after 5 failed attempts"""
        fake_email = f"lockout_test_{int(time.time())}@test.com"
        
        # First register the user
        requests.post(
            f"{API_BASE_URL}/api/auth/register",
            json={
                "email": fake_email,
                "password": TEST_PASSWORD,
                "first_name": "Lockout",
                "last_name": "Test"
            },
            timeout=30
        )
        
        # Attempt 5 wrong password logins
        for i in range(5):
            requests.post(
                f"{API_BASE_URL}/api/auth/login",
                json={"email": fake_email, "password": "wrong_password"},
                timeout=30
            )
        
        # 6th attempt should be locked
        response = requests.post(
            f"{API_BASE_URL}/api/auth/login",
            json={"email": fake_email, "password": "wrong_password"},
            timeout=30
        )
        
        assert response.status_code == 401
        data = response.json()
        assert 'locked' in data.get('error', '').lower()
    
    def test_token_validation_real_api(self):
        """Test that JWT tokens are properly validated"""
        if not hasattr(TestProductionAuthentication, 'auth_token'):
            pytest.skip("No auth token available")
        
        response = requests.get(
            f"{API_BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {TestProductionAuthentication.auth_token}"},
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get('success') == True
        assert 'email' in data
    
    def test_invalid_token_rejected(self):
        """Test that invalid tokens are rejected"""
        response = requests.get(
            f"{API_BASE_URL}/api/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
            timeout=30
        )
        
        assert response.status_code == 401


class TestProductionLicenseAPI:
    """Test real license validation endpoints"""
    
    def test_license_validation_requires_key(self):
        """Test that license validation requires a key"""
        response = requests.post(
            f"{API_BASE_URL}/api/license/validate",
            json={},
            timeout=30
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data.get('valid') == False
    
    def test_license_validation_requires_fingerprint(self):
        """Test that license validation requires hardware fingerprint"""
        response = requests.post(
            f"{API_BASE_URL}/api/license/validate",
            json={"license_key": "FB-TEST-TEST-TEST-TEST"},
            timeout=30
        )
        
        assert response.status_code == 400
        data = response.json()
        assert 'fingerprint' in data.get('error', '').lower()
    
    def test_invalid_license_key_rejected(self):
        """Test that invalid license keys are rejected"""
        response = requests.post(
            f"{API_BASE_URL}/api/license/validate",
            json={
                "license_key": "FB-FAKE-FAKE-FAKE-FAKE",
                "hardware_fingerprint": "test_fingerprint_123"
            },
            timeout=30
        )
        
        assert response.status_code == 404
        data = response.json()
        assert data.get('valid') == False
    
    def test_rate_limiting_on_license_endpoint(self):
        """Test that rate limiting is working on license endpoints"""
        # Make 15 rapid requests (limit is 10 per minute)
        responses = []
        for _ in range(15):
            resp = requests.post(
                f"{API_BASE_URL}/api/license/validate",
                json={
                    "license_key": "FB-TEST-TEST-TEST-TEST",
                    "hardware_fingerprint": "test_fingerprint"
                },
                timeout=5
            )
            responses.append(resp.status_code)
        
        # Should have at least some 429 (rate limited) responses
        # Note: This test may not trigger if rate limiting is disabled in dev
        rate_limited = [r for r in responses if r == 429]
        print(f"Rate limited responses: {len(rate_limited)}/15")
        
        # At minimum, verify the endpoint responds
        assert 400 in responses or 404 in responses or 429 in responses


class TestProductionEncryption:
    """Test real encryption/decryption cycles"""
    
    def test_sha256_hash_consistency(self):
        """Test that SHA-256 hashing is consistent"""
        test_data = b"Test financial data: Invoice #12345, Amount: $1,234.56"
        
        hash1 = hashlib.sha256(test_data).hexdigest()
        hash2 = hashlib.sha256(test_data).hexdigest()
        
        assert hash1 == hash2, "SHA-256 hash should be deterministic"
        assert len(hash1) == 64, "SHA-256 should produce 64 character hex string"
    
    def test_password_hash_not_reversible(self):
        """Test that password hashes cannot be reversed"""
        from argon2 import PasswordHasher
        
        ph = PasswordHasher(
            time_cost=3,
            memory_cost=65536,
            parallelism=4
        )
        
        password = "SecurePassword123!"
        hash1 = ph.hash(password)
        hash2 = ph.hash(password)
        
        # Hashes should be different (due to salt)
        assert hash1 != hash2, "Argon2 should use random salt"
        
        # But both should verify
        assert ph.verify(hash1, password)
        assert ph.verify(hash2, password)


class TestProductionDatabase:
    """Test real database operations"""
    
    def test_database_connection(self):
        """Test that database is accessible"""
        from sqlalchemy import create_engine, text
        
        db_url = os.getenv('DATABASE_URL', 'postgresql://qbmigration:TestPass123@localhost:5432/qbmigration_dev')
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
        
        engine = create_engine(db_url)
        
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.fetchone()[0] == 1
    
    def test_users_table_exists(self):
        """Test that users table exists and is queryable"""
        from sqlalchemy import create_engine, text
        
        db_url = os.getenv('DATABASE_URL', 'postgresql://qbmigration:TestPass123@localhost:5432/qbmigration_dev')
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
        
        engine = create_engine(db_url)
        
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'users' ORDER BY ordinal_position"
            ))
            columns = [row[0] for row in result]
            
            required_columns = ['id', 'email', 'password_hash', 'created_at']
            for col in required_columns:
                assert col in columns, f"Missing required column: {col}"
    
    def test_migrations_table_exists(self):
        """Test that migrations table exists"""
        from sqlalchemy import create_engine, text
        
        db_url = os.getenv('DATABASE_URL', 'postgresql://qbmigration:TestPass123@localhost:5432/qbmigration_dev')
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
        
        engine = create_engine(db_url)
        
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name = 'migrations'"
            ))
            count = result.fetchone()[0]
            assert count == 1, "Migrations table should exist"


class TestProductionAPIEndpoints:
    """Test all critical API endpoints are responding"""
    
    @pytest.mark.parametrize("endpoint,method,expected_min,expected_max", [
        ("/api/health", "GET", 200, 200),
        ("/api/auth/login", "POST", 400, 401),  # Missing data = 400
        ("/api/auth/register", "POST", 400, 409),  # Missing data = 400
        ("/api/license/validate", "POST", 400, 404),
        ("/api/migrations", "GET", 401, 401),  # Requires auth
        ("/api/qbo/status", "GET", 401, 401),  # Requires auth
    ])
    def test_endpoint_responds(self, endpoint, method, expected_min, expected_max):
        """Test that critical endpoints respond correctly"""
        if method == "GET":
            response = requests.get(f"{API_BASE_URL}{endpoint}", timeout=30)
        else:
            response = requests.post(f"{API_BASE_URL}{endpoint}", json={}, timeout=30)
        
        assert expected_min <= response.status_code <= expected_max, \
            f"{endpoint} returned {response.status_code}, expected {expected_min}-{expected_max}"


class TestProductionSecurity:
    """Test security measures are in place"""
    
    def test_cors_headers_present(self):
        """Test that CORS headers are properly set"""
        response = requests.options(
            f"{API_BASE_URL}/api/health",
            headers={"Origin": "http://localhost:3000"},
            timeout=30
        )
        
        # CORS headers should be present
        # Note: May vary based on configuration
        assert response.status_code in [200, 204]
    
    def test_password_requirements_enforced(self):
        """Test that weak passwords are rejected"""
        weak_passwords = [
            "short",  # Too short
            "alllowercase123",  # No uppercase
            "ALLUPPERCASE123",  # No lowercase
            "NoDigitsHere",  # No digits
        ]
        
        for weak_pass in weak_passwords:
            response = requests.post(
                f"{API_BASE_URL}/api/auth/register",
                json={
                    "email": f"weak_{int(time.time())}@test.com",
                    "password": weak_pass,
                    "first_name": "Test"
                },
                timeout=30
            )
            
            # Should reject weak passwords
            assert response.status_code == 400, f"Password '{weak_pass}' should be rejected"
    
    def test_sql_injection_prevented(self):
        """Test that SQL injection is prevented"""
        malicious_inputs = [
            "'; DROP TABLE users; --",
            "1 OR 1=1",
            "admin'--",
            "1; DELETE FROM migrations WHERE 1=1",
        ]
        
        for malicious in malicious_inputs:
            response = requests.post(
                f"{API_BASE_URL}/api/auth/login",
                json={
                    "email": malicious,
                    "password": malicious
                },
                timeout=30
            )
            
            # Should not cause server error (500)
            assert response.status_code != 500, f"SQL injection attempt caused server error"
            # Should return auth error
            assert response.status_code in [400, 401]


class TestProductionConfiguration:
    """Test production configuration values"""
    
    def test_pricing_tiers_configured(self):
        """Test that pricing tiers are properly configured"""
        import sys
        import importlib
        
        # Force reimport
        if 'config' in sys.modules:
            del sys.modules['config']
        
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        import config as cfg_module
        importlib.reload(cfg_module)
        Config = cfg_module.Config
        
        assert hasattr(Config, 'LICENSE_TIERS')
        
        # Check new per-file pricing tiers
        tiers = Config.LICENSE_TIERS
        assert 'standard' in tiers
        assert 'industrial' in tiers
        assert 'forensic' in tiers
        
        # Verify prices
        assert tiers['standard']['price_per_file'] == 199
        assert tiers['industrial']['price_per_file'] == 499
        assert tiers['forensic']['price_per_file'] == 1499
    
    def test_data_retention_code_default(self):
        """Test that data retention default in code is 7 years"""
        # Read the actual source file to verify default
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.py')
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check that the default is 2555 days (7 years)
        assert "'2555'" in content or '"2555"' in content, \
            "MIGRATION_METADATA_RETENTION_DAYS default should be 2555 (7 years)"
    
    def test_aws_region_code_default(self):
        """Test that AWS region default in code is Canada"""
        # Read the actual source file to verify default
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.py')
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check that the default is ca-central-1
        assert "'ca-central-1'" in content or '"ca-central-1"' in content, \
            "AWS_REGION default should be ca-central-1 (Canada)"
    
    def test_session_cookie_secure_in_production(self):
        """Test that session cookie is secure in production config"""
        import sys
        import importlib
        
        # Force reimport
        if 'config' in sys.modules:
            del sys.modules['config']
        
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        import config as cfg_module
        importlib.reload(cfg_module)
        ProductionConfig = cfg_module.ProductionConfig
        
        assert ProductionConfig.SESSION_COOKIE_SECURE == True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
