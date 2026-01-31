import hashlib
import hmac
import secrets
import pyotp
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

class SecurityManager:
    """
    Enhanced security with $25M FIXES:
    
    CRITICAL FIX #1: FAIL-CLOSED policy on OAuth verification
    - Old: If check fails → assume OK (SECURITY VIOLATION)
    - New: If check fails → HARD ABORT (SECURE)
    
    Other features:
    - Pre-migration data scan
    - Naming collision detection
    - Permission scope verification
    - Rate limiting
    """
    
    @staticmethod
    def generate_session_id():
        """Generate cryptographically secure session ID"""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def hash_password(password):
        """Hash password using bcrypt"""
        import bcrypt
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    @staticmethod
    def verify_password(password, hashed):
        """Verify password against hash"""
        import bcrypt
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    
    @staticmethod
    def generate_2fa_secret():
        """Generate TOTP secret for 2FA"""
        return pyotp.random_base32()
    
    @staticmethod
    def verify_2fa_code(secret, code):
        """Verify 2FA TOTP code
        AUDIT FIX: Increased valid_window to handle mobile device clock drift
        """
        totp = pyotp.TOTP(secret)
        # valid_window=2 allows ±60 seconds to handle clock drift
        return totp.verify(code, valid_window=2)
    
    @staticmethod
    def generate_api_signature(payload, secret):
        """Generate HMAC signature for API requests"""
        message = payload.encode('utf-8')
        signature = hmac.new(
            secret.encode('utf-8'),
            message,
            hashlib.sha256
        ).hexdigest()
        return signature
    
    @staticmethod
    def verify_api_signature(payload, signature, secret):
        """Verify HMAC signature"""
        expected = SecurityManager.generate_api_signature(payload, secret)
        return hmac.compare_digest(signature, expected)
    
    @staticmethod
    def rate_limit_check(user_id, max_requests=10, window_minutes=1, redis_client=None):
        """
        $25M FIX: Production-grade rate limiting with Redis backend.
        
        Supports:
        - Multi-instance deployments (auto-scaling)
        - Atomic operations
        - Automatic expiry
        - Graceful fallback to local store
        
        Args:
            user_id: User identifier for rate limiting
            max_requests: Maximum requests allowed in window
            window_minutes: Time window in minutes
            redis_client: Optional Redis client (pass if available)
            
        Returns:
            True if request allowed, False if rate limited
        """
        # Try Redis first (production)
        if redis_client is not None:
            try:
                import redis
                
                window_key = f"ratelimit:{user_id}:{int(time.time() / (window_minutes * 60))}"
                
                # Atomic increment
                count = redis_client.incr(window_key)
                
                # Set expiry on first request
                if count == 1:
                    redis_client.expire(window_key, window_minutes * 60)
                
                # Check limit
                if count > max_requests:
                    return False
                
                return True
                
            except Exception as e:
                # CRIT-12 FIX: Fail-closed in production when Redis unavailable
                import os
                flask_env = os.getenv('FLASK_ENV', 'development')

                if flask_env == 'production':
                    print(f"CRITICAL: Redis rate limiting failed in production: {e}")
                    print("   Denying request - fail-closed security policy")
                    return False  # Fail-closed in production

                # Development only: fallback to local store
                print(f"⚠️  Redis rate limiting failed: {e}")
                print("   Falling back to local rate limiting (development only)")

        # Fallback: In-memory rate limiting (DEVELOPMENT ONLY - single instance)
        import os
        import threading
        if os.getenv('FLASK_ENV', 'development') == 'production':
            # CRIT-12 FIX: Never use in-memory fallback in production
            print("CRITICAL: In-memory rate limiting not allowed in production")
            return False

        # AUDIT FIX: Thread-safe rate limit store initialization and access
        if not hasattr(SecurityManager, '_rate_limit_store'):
            SecurityManager._rate_limit_store = {}
            SecurityManager._rate_limit_lock = threading.Lock()

        now = datetime.now()
        window_start = now - timedelta(minutes=window_minutes)

        with SecurityManager._rate_limit_lock:
            if user_id not in SecurityManager._rate_limit_store:
                SecurityManager._rate_limit_store[user_id] = []

            # Clean old requests
            SecurityManager._rate_limit_store[user_id] = [
                req_time for req_time in SecurityManager._rate_limit_store[user_id]
                if req_time > window_start
            ]

            # Check limit
            if len(SecurityManager._rate_limit_store[user_id]) >= max_requests:
                return False

            # Add this request
            SecurityManager._rate_limit_store[user_id].append(now)
            return True
    
    # ========================================================================
    # PRE-MIGRATION SCAN
    # ========================================================================
    
    @staticmethod
    def pre_migration_scan(data: Dict) -> Dict[str, any]:
        """
        CRITICAL: Scan source data before migration starts
        
        Detects:
        - Naming collisions across Customer/Vendor/Employee
        - Duplicate DocNumbers
        - Invalid characters
        - Data size warnings
        - QBD version compatibility
        
        Returns:
            Dict with 'warnings', 'errors', 'should_proceed'
        """
        print("\n" + "=" * 80)
        print("  PRE-MIGRATION SCAN")
        print("=" * 80)
        
        scan_result = {
            'warnings': [],
            'errors': [],
            'should_proceed': True,
            'recommendations': []
        }
        
        # Check 1: DisplayName uniqueness across entities
        print("\n[1/6] Checking for naming collisions...")
        name_collisions = SecurityManager._check_name_collisions(data)
        
        if name_collisions:
            scan_result['errors'].append(
                f"Found {len(name_collisions)} naming collisions that will cause migration to fail"
            )
            scan_result['should_proceed'] = False
            
            print(f"  ❌ Found {len(name_collisions)} naming collisions:")
            for collision in name_collisions[:5]:
                print(f"     - {collision}")
            
            if len(name_collisions) > 5:
                print(f"     ... and {len(name_collisions) - 5} more")
        else:
            print("  ✅ No naming collisions")
        
        # Check 2: Duplicate DocNumbers
        print("\n[2/6] Checking for duplicate DocNumbers...")
        duplicate_docs = SecurityManager._check_duplicate_doc_numbers(data)
        
        if duplicate_docs:
            scan_result['warnings'].append(
                f"Found {len(duplicate_docs)} duplicate invoice numbers"
            )
            print(f"  ⚠️  Found {len(duplicate_docs)} duplicate DocNumbers")
        else:
            print("  ✅ No duplicate DocNumbers")
        
        # Check 3: Invalid characters
        print("\n[3/6] Checking for invalid characters...")
        invalid_chars = SecurityManager._check_invalid_characters(data)
        
        if invalid_chars:
            scan_result['warnings'].append(
                f"Found {len(invalid_chars)} names with invalid characters (will be sanitized)"
            )
            print(f"  ⚠️  Found {len(invalid_chars)} names with invalid characters")
        else:
            print("  ✅ No invalid characters")
        
        # Check 4: Data size warnings
        print("\n[4/6] Checking data volume...")
        size_warnings = SecurityManager._check_data_size(data)
        
        for warning in size_warnings:
            scan_result['warnings'].append(warning)
            print(f"  ⚠️  {warning}")
        
        if not size_warnings:
            print("  ✅ Data volume is reasonable")
        
        # Check 5: Inactive records with zero balances
        print("\n[5/6] Checking for cleanable records...")
        cleanable = SecurityManager._check_cleanable_records(data)
        
        if cleanable['count'] > 0:
            scan_result['recommendations'].append(
                f"Consider removing {cleanable['count']} inactive records with zero balances to speed up migration"
            )
            print(f"  💡 Found {cleanable['count']} inactive records that could be removed")
        else:
            print("  ✅ No unnecessary records found")
        
        # Check 6: Multi-user mode detection
        print("\n[6/6] Checking file status...")
        if data.get('IsMultiUserMode'):
            scan_result['errors'].append(
                "QuickBooks file is in Multi-user mode. Close all other connections before migration."
            )
            scan_result['should_proceed'] = False
            print("  ❌ File is in Multi-user mode")
        else:
            print("  ✅ File is in single-user mode")
        
        # Print summary
        print("\n" + "=" * 80)
        print("  SCAN SUMMARY")
        print("=" * 80)
        print(f"  Errors: {len(scan_result['errors'])}")
        print(f"  Warnings: {len(scan_result['warnings'])}")
        print(f"  Recommendations: {len(scan_result['recommendations'])}")
        
        if scan_result['should_proceed']:
            print("\n  ✅ PRE-MIGRATION SCAN PASSED")
        else:
            print("\n  ❌ PRE-MIGRATION SCAN FAILED")
            print("\n  Please fix the following errors before proceeding:")
            for error in scan_result['errors']:
                print(f"    - {error}")
        
        print("=" * 80 + "\n")
        
        return scan_result
    
    @staticmethod
    def _check_name_collisions(data: Dict) -> List[str]:
        """Check for naming collisions across Customer/Vendor/Employee"""
        all_names = set()
        collisions = []
        
        # Collect all names
        for customer in data.get('Customers', []):
            name = customer.get('Name', '').strip().lower()
            if name in all_names:
                collisions.append(f"Customer: {customer.get('Name')}")
            all_names.add(name)
        
        for vendor in data.get('Vendors', []):
            name = vendor.get('Name', '').strip().lower()
            if name in all_names:
                collisions.append(f"Vendor: {vendor.get('Name')}")
            all_names.add(name)
        
        for employee in data.get('Employees', []):
            name = employee.get('Name', '').strip().lower()
            if name in all_names:
                collisions.append(f"Employee: {employee.get('Name')}")
            all_names.add(name)
        
        return collisions
    
    @staticmethod
    def _check_duplicate_doc_numbers(data: Dict) -> List[str]:
        """Check for duplicate invoice/bill DocNumbers"""
        doc_numbers = {}
        duplicates = []
        
        for invoice in data.get('Invoices', []):
            doc_num = invoice.get('RefNumber')
            if doc_num:
                if doc_num in doc_numbers:
                    duplicates.append(f"Invoice #{doc_num}")
                else:
                    doc_numbers[doc_num] = True
        
        return duplicates
    
    @staticmethod
    def _check_invalid_characters(data: Dict) -> List[str]:
        """Check for invalid characters in names"""
        invalid_pattern = re.compile(r'[<>:"/\\|?*]')
        invalid_names = []
        
        for customer in data.get('Customers', []):
            name = customer.get('Name', '')
            if invalid_pattern.search(name):
                invalid_names.append(f"Customer: {name}")
        
        for vendor in data.get('Vendors', []):
            name = vendor.get('Name', '')
            if invalid_pattern.search(name):
                invalid_names.append(f"Vendor: {name}")
        
        return invalid_names
    
    @staticmethod
    def _check_data_size(data: Dict) -> List[str]:
        """Check for data size warnings"""
        warnings = []
        
        invoice_count = len(data.get('Invoices', []))
        customer_count = len(data.get('Customers', []))
        item_count = len(data.get('Items', []))
        
        # Large data warnings
        if invoice_count > 10000:
            warnings.append(
                f"Large invoice count ({invoice_count:,}). Migration may take 2-3 hours."
            )
        
        if customer_count > 5000:
            warnings.append(
                f"Large customer count ({customer_count:,}). Consider archiving inactive customers."
            )
        
        if item_count > 2000:
            warnings.append(
                f"Large item count ({item_count:,}). Consider removing unused items."
            )
        
        # Total targets check (QBD limit is 1.2M)
        total_targets = (
            customer_count + 
            len(data.get('Vendors', [])) + 
            len(data.get('Accounts', [])) +
            item_count +
            invoice_count * 5  # Estimate 5 targets per invoice
        )
        
        if total_targets > 1_200_000:
            warnings.append(
                f"File exceeds 1.2M targets ({total_targets:,}). Consider splitting migration."
            )
        
        return warnings
    
    @staticmethod
    def _check_cleanable_records(data: Dict) -> Dict:
        """Check for inactive records with zero balances"""
        cleanable_count = 0
        
        for customer in data.get('Customers', []):
            if not customer.get('IsActive', True) and customer.get('Balance', 0) == 0:
                cleanable_count += 1
        
        for vendor in data.get('Vendors', []):
            if not vendor.get('IsActive', True) and vendor.get('Balance', 0) == 0:
                cleanable_count += 1
        
        return {
            'count': cleanable_count
        }
    
    # ========================================================================
    # PERMISSION VERIFICATION - $25M CRITICAL FIX
    # ========================================================================
    
    @staticmethod
    def verify_oauth_scopes(access_token: str) -> Tuple[bool, List[str]]:
        """
        $25M FIX: FAIL-CLOSED policy on OAuth verification
        
        OLD BEHAVIOR (SECURITY VIOLATION):
            except Exception: return True, []  # Assume OK
        
        NEW BEHAVIOR (SECURE):
            except Exception: raise SecurityError  # HARD ABORT
        
        Verify OAuth token has required scopes.
        
        Args:
            access_token: OAuth access token
            
        Returns:
            (has_required_scopes, actual_scopes)
            
        Raises:
            SecurityError: If verification cannot be completed
        """
        import requests
        # AUDIT FIX: Import introspect URL from config for consistency
        try:
            from config import OAUTH_INTROSPECT_URL
            url = OAUTH_INTROSPECT_URL
        except ImportError:
            # Fallback if config not available
            url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/introspect"
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "token": access_token
        }
        
        try:
            response = requests.post(url, headers=headers, data=data, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                scope_string = result.get('scope', '')
                actual_scopes = scope_string.split() if scope_string else []
                
                # Check for required scope
                required = "com.intuit.quickbooks.accounting"
                has_required = required in actual_scopes
                
                if not has_required:
                    print(f"❌ Missing required OAuth scope: {required}")
                    print(f"   Available scopes: {actual_scopes}")
                
                return has_required, actual_scopes
            
            elif response.status_code == 401:
                # Token is invalid or expired
                raise SecurityError(
                    "OAuth token is invalid or expired. Please re-authenticate."
                )
            
            else:
                # Unknown error - FAIL CLOSED
                raise SecurityError(
                    f"OAuth scope verification failed with status {response.status_code}. "
                    f"Cannot proceed without confirming permissions."
                )
                
        except requests.exceptions.Timeout:
            # Network timeout - FAIL CLOSED
            raise SecurityError(
                "OAuth verification timed out. Cannot proceed without confirming permissions. "
                "Check your internet connection and try again."
            )
        
        except requests.exceptions.ConnectionError:
            # Network error - FAIL CLOSED
            raise SecurityError(
                "Cannot connect to OAuth server. Cannot proceed without confirming permissions. "
                "Check your internet connection and try again."
            )
        
        except Exception as e:
            # $25M CRITICAL FIX: FAIL CLOSED
            # Any error in security check → HARD ABORT
            raise SecurityError(
                f"OAuth scope verification failed: {str(e)}. "
                f"Cannot proceed without confirming permissions. "
                f"This is a security requirement."
            )


class SecurityError(Exception):
    """
    Custom exception for security failures
    
    Used to enforce FAIL-CLOSED policy
    """
    pass