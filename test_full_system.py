"""
COMPREHENSIVE QB MIGRATION SERVER TEST SUITE - IMPROVED
========================================================

Tests ACTUAL functionality, not just HTTP status codes.
"""

import requests
import json
import time
import hashlib
import os
from datetime import datetime
import sys

# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_URL = "http://localhost:5000"
TEST_EMAIL = f"test_{int(time.time())}@example.com"
TEST_PASSWORD = "Test1234!"
MIGRATION_ID = None
SESSION = requests.Session()

# Colors for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def print_header(text):
    """Print a formatted section header"""
    print(f"\n{'='*80}")
    print(f"{BLUE}{text}{RESET}")
    print('='*80)

def print_test(text):
    """Print test description"""
    print(f"\n{YELLOW}TEST:{RESET} {text}")

def print_success(text):
    """Print success message"""
    print(f"{GREEN}✓ PASS:{RESET} {text}")

def print_fail(text):
    """Print failure message"""
    print(f"{RED}✗ FAIL:{RESET} {text}")

def print_info(text):
    """Print info message"""
    print(f"  ℹ {text}")

def create_test_encrypted_data():
    """Create fake encrypted QB data for testing"""
    fake_data = "X" * 1000
    encrypted_payload = {
        "encrypted_data": f"IV:test123456789:TAG:abcdef123456:CIPHER:{fake_data}:KEY:testkey123",
        "company_name": "Test Company Inc",
        "qb_file_name": "test_company.qbw",
        "qb_version": "2024",
        "file_size": len(fake_data)
    }
    return encrypted_payload

# ============================================================================
# TESTS
# ============================================================================

def test_server_health():
    """Test that the server is running and responding"""
    print_header("TEST 1: SERVER HEALTH CHECK")
    
    try:
        print_test("Checking if server is running...")
        response = SESSION.get(f"{BASE_URL}/api/health", timeout=5)
        
        if response.status_code == 200:
            print_success("Server is running")
            data = response.json()
            print_info(f"Environment: {data.get('environment', 'unknown')}")
            print_info(f"Database: {data.get('database', 'unknown')}")
            print_info(f"AWS Configured: {data.get('aws_configured', False)}")
            return True
        else:
            print_fail(f"Server returned status {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print_fail("Cannot connect to server. Is it running? (python run.py)")
        return False
    except Exception as e:
        print_fail(f"Unexpected error: {str(e)}")
        return False


def test_user_registration():
    """Test user registration endpoint"""
    print_header("TEST 2: USER REGISTRATION")
    
    print_test("Registering new user...")
    payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "first_name": "Test",
        "last_name": "User"
    }
    
    response = SESSION.post(f"{BASE_URL}/api/auth/register", json=payload)
    
    if response.status_code == 201:
        data = response.json()
        if data.get('success'):
            print_success("User registration successful")
            print_info(f"User ID: {data['user']['id']}")
            print_info(f"Email: {data['user']['email']}")
            return True
        else:
            print_fail(f"Registration failed: {data.get('message', 'Unknown error')}")
            return False
    else:
        print_fail(f"Registration returned status {response.status_code}")
        return False


def test_user_login():
    """Test user login endpoint"""
    print_header("TEST 3: USER LOGIN")
    
    print_test("Logging in user...")
    payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    }
    
    response = SESSION.post(f"{BASE_URL}/api/auth/login", json=payload)
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            print_success("User login successful")
            print_info(f"Session established for: {data['user']['email']}")
            return True
        else:
            print_fail(f"Login failed: {data.get('message', 'Unknown error')}")
            return False
    else:
        print_fail(f"Login returned status {response.status_code}")
        return False


def test_authentication_required():
    """Test that protected endpoints require authentication"""
    print_header("TEST 4: AUTHENTICATION PROTECTION")
    
    print_test("Testing unauthenticated access to protected endpoint...")
    
    temp_session = requests.Session()
    response = temp_session.get(f"{BASE_URL}/api/migrations")
    
    if response.status_code == 401:
        print_success("Protected endpoint correctly requires authentication")
        return True
    else:
        print_fail(f"Protected endpoint returned {response.status_code}, expected 401")
        return False


def test_file_upload():
    """Test file upload to S3"""
    print_header("TEST 5: FILE UPLOAD TO S3")
    
    global MIGRATION_ID
    
    print_test("Uploading encrypted QB file...")
    payload = create_test_encrypted_data()
    
    response = SESSION.post(f"{BASE_URL}/api/upload", json=payload)
    
    if response.status_code == 201:
        data = response.json()
        if data.get('success'):
            MIGRATION_ID = data.get('migration_id')
            print_success("File uploaded successfully")
            print_info(f"Migration ID: {MIGRATION_ID}")
            print_info(f"Status: {data.get('status', 'uploaded')}")
            return True
        else:
            print_fail(f"Upload failed: {data.get('error', 'Unknown error')}")
            return False
    else:
        print_fail(f"Upload returned status {response.status_code}")
        print_info(f"Response: {response.text}")
        return False


def test_migration_status():
    """Test migration status retrieval"""
    print_header("TEST 6: MIGRATION STATUS TRACKING")
    
    if not MIGRATION_ID:
        print_fail("No migration ID available")
        return False
    
    print_test("Retrieving migration status...")
    
    response = SESSION.get(f"{BASE_URL}/api/migrations/{MIGRATION_ID}/status")
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            print_success("Migration status retrieved")
            print_info(f"Status: {data.get('status')}")
            print_info(f"Progress: {data.get('progress_percent', 0)}%")
            print_info(f"Created: {data.get('created_at')}")
            return True
        else:
            print_fail(f"Status retrieval failed: {data.get('error')}")
            return False
    else:
        print_fail(f"Status endpoint returned {response.status_code}")
        return False


def test_list_migrations():
    """Test listing user's migrations"""
    print_header("TEST 7: LIST USER MIGRATIONS")
    
    print_test("Listing all user migrations...")
    
    response = SESSION.get(f"{BASE_URL}/api/migrations")
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            migrations = data.get('migrations', [])
            print_success(f"Found {len(migrations)} migration(s)")
            
            if migrations:
                print_info("Recent migrations:")
                for mig in migrations[:3]:
                    print_info(f"  • {mig['migration_id']} - {mig['status']} - {mig.get('created_at', 'N/A')}")
            return True
        else:
            print_fail(f"Listing failed: {data.get('error')}")
            return False
    else:
        print_fail(f"Migrations endpoint returned {response.status_code}")
        print_info(f"Response: {response.text[:200]}")
        return False


def test_ec2_configuration():
    """Test that EC2 configuration is valid"""
    print_header("TEST 8: EC2 CONFIGURATION CHECK")
    
    print_test("Verifying EC2 configuration...")
    
    from dotenv import load_dotenv
    load_dotenv()
    
    required_configs = {
        'AWS_EC2_AMI_ID': os.getenv('AWS_EC2_AMI_ID'),
        'AWS_EC2_INSTANCE_TYPE': os.getenv('AWS_EC2_INSTANCE_TYPE'),
        'AWS_EC2_SECURITY_GROUP': os.getenv('AWS_EC2_SECURITY_GROUP'),
        'AWS_IAM_INSTANCE_PROFILE': os.getenv('AWS_IAM_INSTANCE_PROFILE'),
        'AWS_S3_BUCKET': os.getenv('AWS_S3_BUCKET'),
        'AWS_REGION': os.getenv('AWS_REGION'),
    }
    
    all_present = True
    for key, value in required_configs.items():
        if value and value not in ['', 'your-', 'sg-xxxxxxxxxxxxxxxxx']:
            print_success(f"{key}: {value}")
        else:
            print_fail(f"{key}: MISSING or placeholder")
            all_present = False
    
    if all_present:
        print_success("All EC2 configuration present")
        return True
    else:
        print_fail("Some EC2 configuration missing")
        return False


def test_ec2_process_endpoint():
    """Test EC2 process endpoint actually exists and validates input"""
    print_header("TEST 9: EC2 PROCESS ENDPOINT")
    
    if not MIGRATION_ID:
        print_fail("No migration ID available")
        return False
    
    print_test("Testing EC2 process endpoint with invalid credentials...")
    
    # Try to start migration without proper QBO credentials (should fail with 400)
    response = SESSION.post(
        f"{BASE_URL}/api/migrations/{MIGRATION_ID}/process",
        json={"invalid": "data"}
    )
    
    if response.status_code == 400:
        data = response.json()
        if 'QuickBooks' in data.get('error', ''):
            print_success("Endpoint exists and validates QBO credentials")
            print_info("Returns 400 for missing credentials (correct)")
            return True
        else:
            print_fail(f"Unexpected error message: {data.get('error')}")
            return False
    elif response.status_code == 404:
        print_fail("Endpoint not found (404)")
        print_info("The /process endpoint doesn't exist")
        return False
    else:
        print_fail(f"Unexpected status code: {response.status_code}")
        print_info(f"Response: {response.text[:200]}")
        return False


def test_webhook_endpoint():
    """Test webhook callback endpoint actually works"""
    print_header("TEST 10: WEBHOOK CALLBACK ENDPOINT")
    
    if not MIGRATION_ID:
        print_fail("No migration ID available")
        return False
    
    print_test("Testing webhook progress endpoint...")
    
    # Get webhook secret from environment
    from dotenv import load_dotenv
    load_dotenv()
    webhook_secret = os.getenv('WEBHOOK_SECRET', '')
    
    if not webhook_secret:
        print_fail("WEBHOOK_SECRET not configured in .env")
        return False
    
    # Test with proper authentication
    webhook_payload = {
        "migration_id": MIGRATION_ID,
        "status": "processing",
        "progress_percent": 25,
        "message": "Test progress update",
        "current_step": "Testing webhook"
    }
    
    headers = {
        'X-Webhook-Secret': webhook_secret,
        'X-Migration-Id': MIGRATION_ID,
        'Content-Type': 'application/json'
    }
    
    response = SESSION.post(
        f"{BASE_URL}/api/webhooks/migration-progress",
        json=webhook_payload,
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            print_success("Webhook endpoint working correctly")
            print_info("Progress update accepted")
            
            # Verify the progress was actually updated
            status_response = SESSION.get(f"{BASE_URL}/api/migrations/{MIGRATION_ID}/status")
            if status_response.status_code == 200:
                status_data = status_response.json()
                updated_progress = status_data.get('progress_percent', 0)
                if updated_progress == 25:
                    print_success("Progress update persisted to database")
                else:
                    print_info(f"Progress in DB: {updated_progress}% (expected 25%)")
            
            return True
        else:
            print_fail(f"Webhook failed: {data.get('error')}")
            return False
    elif response.status_code == 401:
        print_fail("Webhook authentication failed")
        print_info("Check WEBHOOK_SECRET in .env")
        return False
    elif response.status_code == 404:
        print_fail("Webhook endpoint not found (404)")
        print_info("The /api/webhooks/migration-progress endpoint doesn't exist")
        return False
    else:
        print_fail(f"Unexpected status code: {response.status_code}")
        print_info(f"Response: {response.text[:200]}")
        return False


def test_error_handling():
    """Test various error conditions"""
    print_header("TEST 11: ERROR HANDLING")
    
    print_test("Testing invalid migration ID...")
    response = SESSION.get(f"{BASE_URL}/api/migrations/invalid-id-12345/status")
    
    if response.status_code in [400, 404]:
        print_success("Invalid ID properly rejected")
    else:
        print_fail(f"Expected 400/404, got {response.status_code}")
        return False
    
    print_test("Testing malformed upload data...")
    response = SESSION.post(f"{BASE_URL}/api/upload", json={"invalid": "data"})
    
    if response.status_code in [400, 422]:
        print_success("Malformed data properly rejected")
    else:
        print_fail(f"Expected 400/422, got {response.status_code}")
        return False
    
    print_success("Error handling works correctly")
    return True


def test_user_logout():
    """Test user logout"""
    print_header("TEST 12: USER LOGOUT")
    
    print_test("Logging out user...")
    
    response = SESSION.post(f"{BASE_URL}/api/auth/logout")
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            print_success("User logged out successfully")
            
            print_test("Verifying session is invalid...")
            verify_response = SESSION.get(f"{BASE_URL}/api/migrations")
            
            if verify_response.status_code == 401:
                print_success("Session properly invalidated")
                return True
            else:
                print_fail("Session still valid after logout!")
                return False
        else:
            print_fail("Logout failed")
            return False
    else:
        print_fail(f"Logout returned status {response.status_code}")
        return False


def run_all_tests():
    """Run all tests and generate summary report"""
    
    print(f"\n{'='*80}")
    print(f"{BLUE}QB MIGRATION SERVER - COMPREHENSIVE TEST SUITE (IMPROVED){RESET}")
    print(f"{'='*80}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Base URL: {BASE_URL}")
    print(f"{'='*80}")
    
    tests = [
        ("Server Health", test_server_health),
        ("User Registration", test_user_registration),
        ("User Login", test_user_login),
        ("Authentication Protection", test_authentication_required),
        ("File Upload to S3", test_file_upload),
        ("Migration Status", test_migration_status),
        ("List Migrations", test_list_migrations),
        ("EC2 Configuration", test_ec2_configuration),
        ("EC2 Process Endpoint", test_ec2_process_endpoint),
        ("Webhook Callback", test_webhook_endpoint),
        ("Error Handling", test_error_handling),
        ("User Logout", test_user_logout),
    ]
    
    results = []
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print_fail(f"Test crashed: {str(e)}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
            failed += 1
    
    # Print summary
    print_header("TEST SUMMARY")
    
    print(f"\n{GREEN}Passed: {passed}/{len(tests)}{RESET}")
    print(f"{RED}Failed: {failed}/{len(tests)}{RESET}")
    print(f"Success Rate: {(passed/len(tests)*100):.1f}%\n")
    
    print("Detailed Results:")
    for test_name, result in results:
        status = f"{GREEN}✓ PASS{RESET}" if result else f"{RED}✗ FAIL{RESET}"
        print(f"  {status}  {test_name}")
    
    print(f"\n{'='*80}")
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)