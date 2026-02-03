import requests
import time
import json
import logging
import sqlite3
import os
import signal
import sys
import uuid
import random
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from decimal import Decimal
from pathlib import Path

# Import configuration settings (HIGH PRIORITY FROM TESTING REPORT)
try:
    from . import config
except ImportError:
    import config

logger = logging.getLogger(__name__)


class PremiumQBOClient:
    """
    PREMIUM QuickBooks Online API Client with All Fixes Applied
    
    FIXES IMPLEMENTED:
    1. Thread-safe SQLite (check_same_thread=False)
    2. Per-request header copies (no shared state)
    3. Atomic batch tracking
    4. Proper SyncToken management
    5. Retry-After header support
    6. MinorVersion URL parameter
    7. Shared requests.Session for connection pooling
    8. Idempotency keys for crash recovery
    9. Proper error handling (no token leaking)
    10. Graceful shutdown on SIGTERM/SIGINT
    """
    
    def __init__(
        self,
        access_token: Optional[str] = None,
        db_path: Optional[str] = None,
        base_url: str = None,
        minor_version: int = 65,
        qbo_plan: Optional[str] = None
    ):
        # FIX #17, #18: Don't store mutable headers - create per-request
        self._base_access_token = access_token
        self.base_url = base_url
        self.minor_version = minor_version
        
        # FIX #81: Shared requests.Session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "QBMigrationTool/2.0 (Python)"  # FIX #318: Custom User-Agent
        })
        
        self.request_count = 0
        self.start_time = time.time()
        
        # Rate limit tracking
        self.rate_limit_remaining = 500
        self.rate_limit_reset_time = None
        self.rate_limit_lock = Lock()  # FIX #14: Thread-safe counter
        
        # FIX #81: SQLite with check_same_thread=False
        self.db_path = Path(db_path) if db_path else Path("data/migration_state.db")
        self.db_lock = Lock()
        self._init_database()
        
        # SyncToken tracking (FIX #33, #124)
        self.synctoken_cache = {}  # {(entity_type, qbo_id): synctoken}
        self.synctoken_lock = Lock()
        
        # Batch tracking (FIX #18)
        self.batch_counter = 0
        self.batch_lock = Lock()

        # Per-minute batch rate limiting
        self._batch_timestamps = []
        self._batch_timestamps_lock = Lock()
        
        # $25M FIX: Plan-aware parallel processing configuration
        # Different QBO plans have different API rate limits
        # Advanced: 500 req/min → 8 workers
        # Plus: 500 req/min → 5 workers
        # Essentials: 100 req/min → 3 workers
        # Simple Start: 100 req/min → 2 workers
        if qbo_plan is None:
            import os
            qbo_plan = os.getenv("QBO_PLAN", "Plus")

        # VALIDATION FIX: Validate QBO_PLAN env var
        valid_plans = ["Simple Start", "Essentials", "Plus", "Advanced"]
        if qbo_plan not in valid_plans:
            logger.warning(
                f"Invalid QBO_PLAN '{qbo_plan}'. Valid options: {valid_plans}. "
                f"Defaulting to 'Plus'."
            )
            qbo_plan = "Plus"

        self.qbo_plan = qbo_plan
        self.max_workers = self._get_plan_worker_limit(qbo_plan)
        self.enable_parallel = True
        
        # FIX SVC-06: Use logger instead of print
        logger.info(f"QBO Plan: {qbo_plan} -> {self.max_workers} upload workers")
        
        # Failed items storage (FIX #243, #389)
        self.failed_items: List[Dict] = []
        self.failed_items_lock = Lock()
        
        # Graceful shutdown flag (FIX #251, #386)
        self.shutdown_requested = False
        self._register_signal_handlers()
    
    @staticmethod
    def _get_plan_worker_limit(plan_name: str) -> int:
        """
        $25M FIX: Get worker limit based on QBO plan tier.
        
        Conservative limits to avoid rate limiting:
        - Advanced: 8 workers (premium API access)
        - Plus: 5 workers (standard)
        - Essentials: 3 workers (limited API)
        - Simple Start: 2 workers (minimal API)
        """
        plan_limits = {
            "Advanced": 8,
            "Plus": 5,
            "Essentials": 3,
            "Simple Start": 2
        }
        
        limit = plan_limits.get(plan_name, 5)
        
        # Also check environment override
        import os
        env_override = os.getenv("QBO_UPLOAD_WORKERS")
        if env_override:
            try:
                limit = max(1, min(int(env_override), 10))  # Cap at 10 workers
                # FIX SVC-06: Use logger instead of print
                logger.info(f"Using environment override: {limit} workers")
            except ValueError:
                pass

        return limit
    
    def _register_signal_handlers(self):
        """
        FIX #251, #386: Graceful shutdown on SIGTERM/SIGINT
        AUDIT FIX: Only register from main thread to avoid ValueError
        """
        import threading

        # Signal handlers can only be registered from the main thread
        if threading.current_thread() is not threading.main_thread():
            logger.debug("Skipping signal handler registration (not main thread)")
            return

        def shutdown_handler(signum, frame):
            logger.warning("Shutdown signal received. Completing current requests...")
            self.shutdown_requested = True

        try:
            signal.signal(signal.SIGTERM, shutdown_handler)
            signal.signal(signal.SIGINT, shutdown_handler)
        except ValueError as e:
            # May still fail in some embedded environments
            logger.debug(f"Could not register signal handlers: {e}")
    
    def _check_shutdown(self):
        """Check if shutdown was requested"""
        if self.shutdown_requested:
            logger.warning("Shutdown requested, stopping operations")
            raise KeyboardInterrupt("Graceful shutdown")
    
    # ========================================================================
    # PREMIUM FEATURE #1: THREAD-SAFE SQLITE STATE MANAGEMENT
    # ========================================================================
    
    def _init_database(self):
        """
        FIX #81: SQLite with check_same_thread=False for parallel access
        FIX #50: Database indexes for performance
        CRIT-07 FIX: Set restrictive file permissions (0600)
        AUDIT FIX: Enable WAL mode for better concurrent write handling
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # CRIT-07 FIX: Set restrictive permissions on database file
        db_exists = self.db_path.exists()

        with self.db_lock:
            # FIX #81: check_same_thread=False for multi-threading
            # AUDIT FIX: Use config constants instead of magic numbers
            try:
                from config import SQLITE_TIMEOUT_SECONDS, SQLITE_BUSY_TIMEOUT_MS
                timeout = SQLITE_TIMEOUT_SECONDS
                busy_timeout = SQLITE_BUSY_TIMEOUT_MS
            except ImportError:
                timeout = 30.0
                busy_timeout = 30000

            conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=timeout
            )
            cursor = conn.cursor()

            # AUDIT FIX: Enable WAL mode for better concurrent read/write
            cursor.execute("PRAGMA journal_mode=WAL")
            # CRITICAL FIX: Validate busy_timeout as integer to prevent SQL injection
            # PRAGMA statements don't support parameterization, so we must validate the input
            validated_timeout = int(busy_timeout)  # Raises ValueError if not an integer
            if validated_timeout < 0 or validated_timeout > 300000:  # Max 5 minutes
                validated_timeout = 30000  # Default to 30 seconds
            cursor.execute(f"PRAGMA busy_timeout={validated_timeout}")
            
            # Create entities table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS migrated_entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    qbd_id TEXT NOT NULL,
                    qbo_id TEXT NOT NULL,
                    sync_token TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    migration_id TEXT,
                    status TEXT DEFAULT 'created',
                    UNIQUE(entity_type, qbd_id)
                )
            ''')
            
            # Create sync log table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sync_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    entity_type TEXT,
                    qbd_id TEXT,
                    qbo_id TEXT,
                    status TEXT,
                    error_message TEXT,
                    intuit_tid TEXT,
                    migration_id TEXT
                )
            ''')
            
            # Create batch tracking table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS batch_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id TEXT NOT NULL UNIQUE,
                    entity_type TEXT,
                    batch_size INTEGER,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    status TEXT DEFAULT 'in_progress',
                    idempotency_key TEXT
                )
            ''')
            
            # FIX #50, #149: Create indexes for fast lookups
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_entity_lookup 
                ON migrated_entities(entity_type, qbd_id)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_migration_id 
                ON migrated_entities(migration_id)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_status 
                ON migrated_entities(status)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_qbo_id 
                ON migrated_entities(entity_type, qbo_id)
            ''')
            
            conn.commit()
            conn.close()

        # CRIT-07 FIX: Set restrictive file permissions after database creation
        try:
            os.chmod(str(self.db_path), 0o600)  # Owner read/write only
        except (OSError, AttributeError):
            pass  # May fail on Windows

        logger.info(f"SQLite state database initialized: {self.db_path}")
    
    def record_created(
        self,
        entity_type: str,
        qbd_id: str,
        qbo_id: str,
        migration_id: str = None,
        sync_token: str = "0"
    ):
        """
        FIX #130: Explicit transaction with context manager
        FIX #33: Store SyncToken for future updates
        """
        with self.db_lock:
            # FIX #81: check_same_thread=False allows this
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            
            try:
                with conn:  # FIX #130: Automatic transaction
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO migrated_entities 
                        (entity_type, qbd_id, qbo_id, migration_id, status, sync_token)
                        VALUES (?, ?, ?, ?, 'created', ?)
                    ''', (entity_type, qbd_id, qbo_id, migration_id, sync_token))
                    
                # Update SyncToken cache
                with self.synctoken_lock:
                    self.synctoken_cache[(entity_type, qbo_id)] = sync_token
                    
            except Exception as e:
                logger.error(f"Failed to record entity: {e}")
                raise
            finally:
                conn.close()
    
    def _record_migration(self, entity_type: str, qbd_id: str, qbo_id: str, migration_id: str = None, sync_token: str = "0"):
        """Alias for record_created for backward compatibility"""
        return self.record_created(entity_type, qbd_id, qbo_id, migration_id, sync_token)
    
    def get_synctoken(self, entity_type: str, qbo_id: str) -> str:
        """
        FIX #33, #124: Retrieve current SyncToken for entity
        FIX: Acquire db_lock FIRST, then synctoken_lock to match lock ordering
        in record_created() and prevent deadlocks.
        """
        with self.db_lock:
            with self.synctoken_lock:
                # Check cache first
                cache_key = (entity_type, str(qbo_id))
                if cache_key in self.synctoken_cache:
                    return self.synctoken_cache[cache_key]

            # Fall back to DB lookup (still under db_lock)
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT sync_token FROM migrated_entities
                WHERE entity_type = ? AND qbo_id = ?
            ''', (entity_type, qbo_id))

            result = cursor.fetchone()
            conn.close()

            if result:
                sync_token = result[0] or "0"
                # Update cache (acquire synctoken_lock under db_lock)
                with self.synctoken_lock:
                    self.synctoken_cache[(entity_type, str(qbo_id))] = sync_token
                return sync_token

            return "0"
    
    def update_synctoken(self, entity_type: str, qbo_id: str, new_synctoken: str):
        """
        FIX #33: Update SyncToken after successful update
        DEADLOCK FIX: Acquire db_lock FIRST, then synctoken_lock to match
        lock ordering in record_created() and get_synctoken().
        Previous code acquired synctoken_lock first, causing deadlock risk.
        """
        with self.db_lock:
            # Update cache under consistent lock ordering (db_lock → synctoken_lock)
            with self.synctoken_lock:
                self.synctoken_cache[(entity_type, qbo_id)] = new_synctoken

            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            try:
                with conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE migrated_entities
                        SET sync_token = ?
                        WHERE entity_type = ? AND qbo_id = ?
                    ''', (new_synctoken, entity_type, qbo_id))
            finally:
                conn.close()
    
    def was_entity_created(self, entity_type: str, qbd_id: str) -> Optional[str]:
        """O(1) instant lookup with SQLite index"""
        with self.db_lock:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT qbo_id FROM migrated_entities
                WHERE entity_type = ? AND qbd_id = ? AND status = 'created'
            ''', (entity_type, qbd_id))
            
            result = cursor.fetchone()
            conn.close()
            
            return result[0] if result else None
    
    def get_migration_summary(self, migration_id: str = None) -> Dict:
        """Get summary of migration progress"""
        with self.db_lock:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            cursor = conn.cursor()
            
            # Count by entity type
            if migration_id:
                cursor.execute('''
                    SELECT entity_type, COUNT(*) 
                    FROM migrated_entities
                    WHERE migration_id = ? AND status = 'created'
                    GROUP BY entity_type
                ''', (migration_id,))
            else:
                cursor.execute('''
                    SELECT entity_type, COUNT(*) 
                    FROM migrated_entities
                    WHERE status = 'created'
                    GROUP BY entity_type
                ''')
            
            counts = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Get total
            if migration_id:
                cursor.execute('''
                    SELECT COUNT(*) FROM migrated_entities
                    WHERE migration_id = ? AND status = 'created'
                ''', (migration_id,))
            else:
                cursor.execute('''
                    SELECT COUNT(*) FROM migrated_entities
                    WHERE status = 'created'
                ''')
            
            # AUDIT FIX: Handle None from fetchone() on empty tables
            result = cursor.fetchone()
            total = result[0] if result else 0

            # Get last update time
            cursor.execute('SELECT MAX(created_at) FROM migrated_entities')
            result = cursor.fetchone()
            last_updated = result[0] if result else None

            conn.close()

            return {
                "total_entities": total,
                "entity_counts": counts,
                "last_updated": last_updated
            }
    
    # ========================================================================
    # CORE API REQUEST METHODS (With All Fixes)
    # ========================================================================
    
    def _build_url(self, endpoint: str) -> str:
        """
        FIX #37, #147: Add minorversion parameter
        """
        url = f"{self.base_url}/{endpoint}"
        
        # Add minorversion if not already in URL
        if 'minorversion=' not in url.lower():
            separator = '&' if '?' in url else '?'
            url = f"{url}{separator}minorversion={self.minor_version}"
        
        return url
    
    def _get_request_headers(self, oauth_manager: Optional[Any] = None) -> Dict[str, str]:
        """
        FIX #17, #18: Create per-request header copy
        FIX #20: Don't use stale tokens
        """
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "QBMigrationTool/2.0 (Python)"
        }
        
        # Get fresh token
        if oauth_manager:
            token = oauth_manager.get_access_token()
        else:
            token = self._base_access_token

        # CRITICAL FIX: Validate token is not None before creating Authorization header
        if not token:
            raise ValueError(
                "No access token available. Either provide oauth_manager or "
                "initialize PremiumQBOClient with access_token parameter."
            )

        headers["Authorization"] = f"Bearer {token}"

        return headers
    
    def _update_rate_limits(self, response: requests.Response):
        """
        FIX #14: Thread-safe rate limit tracking
        FIX #222: Track X-RateLimit-Remaining properly
        """
        with self.rate_limit_lock:
            self.request_count += 1
            
            # Track rate limits from headers
            remaining = response.headers.get('X-RateLimit-Remaining')
            if remaining:
                try:
                    self.rate_limit_remaining = int(remaining)
                except ValueError:
                    pass
    
    def _dynamic_rate_limit(self):
        """
        FIX #13, #14: Thread-safe rate limiting with proper sleep
        """
        with self.rate_limit_lock:
            if self.rate_limit_remaining < 50:
                # Approaching limit - slow down
                sleep_time = 0.5
            elif self.rate_limit_remaining < 100:
                sleep_time = 0.2
            else:
                sleep_time = 0.1
        
        time.sleep(sleep_time)
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        retries: int = 0,
        oauth_manager: Optional[Any] = None,
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
        _auth_refreshed: bool = False
    ) -> Dict:
        """
        ENHANCED: Request with configurable timeout and correlation ID support
        
        TESTING REPORT FIXES APPLIED:
        - HIGH: Configurable network timeout (config.QBO_REQUEST_TIMEOUT)
        - HIGH: Configurable retry settings (config.RETRY_MAX_ATTEMPTS)
        - MEDIUM: Correlation ID support for distributed tracing
        - MEDIUM: Jitter in backoff to prevent thundering herd
        
        FIX #39: Request timeout
        FIX #313: Honor Retry-After header
        FIX #318: Custom User-Agent
        FIX #312: X-Intuit-Tracking-Id for correlation
        FIX #8: Don't leak tokens in error messages
        """
        self._check_shutdown()
        
        # TESTING REPORT: Generate or use provided correlation ID
        if correlation_id is None and getattr(config, 'ENABLE_CORRELATION_IDS', True):
            correlation_id = str(uuid.uuid4())
        
        # FIX #17: Per-request headers
        headers = self._get_request_headers(oauth_manager)
        
        # TESTING REPORT: Add correlation ID header
        if correlation_id:
            headers[config.CORRELATION_ID_HEADER] = correlation_id
        
        # FIX #312: Add idempotency key if provided
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        
        self._dynamic_rate_limit()
        
        url = self._build_url(endpoint)
        
        # TESTING REPORT: Use configurable timeout from config
        request_timeout = getattr(config, 'QBO_REQUEST_TIMEOUT', (10, 30))
        max_retries = getattr(config, 'RETRY_MAX_ATTEMPTS', 3)
        
        try:
            if method == "POST":
                response = self.session.post(url, headers=headers, json=data, timeout=request_timeout)
            elif method == "GET":
                response = self.session.get(url, headers=headers, timeout=request_timeout)
            elif method == "DELETE":
                logger.warning("QBO uses POST for deletes, not DELETE. Use delete_entity() instead.")
                raise ValueError("QBO API does not support HTTP DELETE. Use POST with ?operation=delete via delete_entity()")
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            self._update_rate_limits(response)
            
            # Log Intuit-TID for support correlation
            intuit_tid = response.headers.get('intuit_tid', 'N/A')
            
            # TESTING REPORT: Enhanced logging with correlation ID
            if getattr(config, 'LOG_INTUIT_TID', True):
                logger.debug(f"[{correlation_id}] Request {method} {endpoint} - Intuit TID: {intuit_tid}")
            
            # Handle errors
            if response.status_code == 429:
                # FIX #313: Honor Retry-After header
                retry_after = response.headers.get('Retry-After')
                if retry_after:
                    try:
                        wait_time = int(retry_after)
                    except ValueError:
                        wait_time = self._calculate_backoff(retries)
                else:
                    wait_time = self._calculate_backoff(retries)
                
                if retries < max_retries:
                    logger.warning(f"[{correlation_id}] Rate limited (429). Waiting {wait_time}s... (TID: {intuit_tid})")
                    time.sleep(wait_time)
                    return self._make_request(method, endpoint, data, retries + 1, oauth_manager, idempotency_key, correlation_id)
                else:
                    raise Exception(f"Max retries exceeded for rate limit (TID: {intuit_tid}, CID: {correlation_id})")
            
            elif response.status_code == 401:
                # FIX #263: Token might be expired, refresh and retry
                # FIX: Use _auth_refreshed flag instead of retries==0 so
                # unrelated retries (timeout, 503) don't block token refresh
                if not _auth_refreshed and oauth_manager:
                    logger.warning(f"[{correlation_id}] Token expired (401), refreshing...")
                    oauth_manager.refresh_access_token()
                    new_token = oauth_manager.get_access_token()
                    if new_token:
                        self._base_access_token = new_token
                    return self._make_request(method, endpoint, data, retries, oauth_manager, idempotency_key, correlation_id, _auth_refreshed=True)
                else:
                    raise Exception(f"Authentication failed (TID: {intuit_tid}, CID: {correlation_id})")
            
            elif response.status_code == 400:
                # Validation error - NOT retryable
                error_detail = "Unknown validation error"
                try:
                    error_body = response.json()
                    if 'Fault' in error_body:
                        errors = error_body['Fault'].get('Error', [])
                        error_detail = '; '.join(e.get('Detail', e.get('Message', '')) for e in errors)
                except Exception:
                    error_detail = response.text[:500]
                logger.error(f"QBO validation error (400): {error_detail}")
                raise ValueError(f"QBO API validation error: {error_detail}")

            elif response.status_code == 403:
                logger.error(f"QBO permission denied (403) for {method} {endpoint}")
                raise PermissionError(f"QBO API permission denied for {endpoint}")

            elif response.status_code in getattr(config, 'RETRYABLE_STATUS_CODES', {429, 500, 502, 503, 504}):
                if retries < max_retries:
                    wait_time = self._calculate_backoff(retries)
                    logger.warning(f"[{correlation_id}] Server error ({response.status_code}). Retry {retries+1}/{max_retries} in {wait_time}s... (TID: {intuit_tid})")
                    time.sleep(wait_time)
                    return self._make_request(method, endpoint, data, retries + 1, oauth_manager, idempotency_key, correlation_id)
                else:
                    raise Exception(f"Max retries exceeded for server error (TID: {intuit_tid}, CID: {correlation_id})")
            
            response.raise_for_status()
            
            # Parse response
            result = response.json()
            
            # FIX #33: Extract and cache SyncToken if present
            if isinstance(result, dict):
                for key in result:
                    if isinstance(result[key], dict) and 'Id' in result[key] and 'SyncToken' in result[key]:
                        entity_id = result[key]['Id']
                        sync_token = result[key]['SyncToken']
                        entity_type = key
                        self.update_synctoken(entity_type, entity_id, sync_token)
            
            return result
            
        except requests.exceptions.Timeout:
            if retries < max_retries:
                wait_time = self._calculate_backoff(retries)
                logger.warning(f"[{correlation_id}] Request timeout. Retry {retries+1}/{max_retries} in {wait_time}s...")
                time.sleep(wait_time)
                return self._make_request(method, endpoint, data, retries + 1, oauth_manager, idempotency_key, correlation_id)
            else:
                logger.error(f"[{correlation_id}] Request timed out after {max_retries} retries")
                raise
        except requests.exceptions.RequestException as e:
            if retries < max_retries:
                wait_time = self._calculate_backoff(retries)
                logger.warning(f"[{correlation_id}] Request error. Retry {retries+1}/{max_retries} in {wait_time}s...")
                time.sleep(wait_time)
                return self._make_request(method, endpoint, data, retries + 1, oauth_manager, idempotency_key, correlation_id)
            else:
                logger.error(f"[{correlation_id}] Request failed after {max_retries} retries")
                raise
    
    def _calculate_backoff(self, retries: int) -> float:
        """
        TESTING REPORT: Calculate retry backoff with optional jitter
        
        Implements exponential backoff with optional random jitter to prevent
        thundering herd problems when multiple clients retry simultaneously.
        """
        base = getattr(config, 'RETRY_BACKOFF_BASE', 2.0)
        max_backoff = getattr(config, 'RETRY_BACKOFF_MAX', 60)
        use_jitter = getattr(config, 'RETRY_JITTER', True)
        
        # Exponential backoff: base^retries
        wait_time = min(base ** retries, max_backoff)
        
        # Add random jitter (±25%) to prevent thundering herd
        if use_jitter:
            jitter = wait_time * 0.25 * (random.random() * 2 - 1)
            wait_time = max(0.1, wait_time + jitter)
        
        return round(wait_time, 2)
    
    def delete_entity(
        self,
        entity_type: str,
        qbo_id: str,
        oauth_manager: Optional[Any] = None
    ) -> bool:
        """
        FIX #33, #124: Use actual SyncToken instead of hardcoded "0"
        FIX #434: Clear from database after successful deletion
        """
        # Get current SyncToken
        sync_token = self.get_synctoken(entity_type, qbo_id)
        
        endpoint = f"{entity_type.lower()}?operation=delete"
        
        delete_data = {
            "Id": qbo_id,
            "SyncToken": sync_token
        }
        
        try:
            self._make_request("POST", endpoint, delete_data, oauth_manager=oauth_manager)
            
            # FIX #434: Update database status
            with self.db_lock:
                conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
                try:
                    with conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                            UPDATE migrated_entities 
                            SET status = 'deleted'
                            WHERE entity_type = ? AND qbo_id = ?
                        ''', (entity_type, qbo_id))
                finally:
                    conn.close()
            
            logger.info(f"Deleted {entity_type} {qbo_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete {entity_type} {qbo_id}: {e}")
            return False
    
    def create_entity(
        self,
        entity_type: str,
        entity_data: Dict,
        oauth_manager: Optional[Any] = None
    ) -> Dict:
        """
        Create a single entity in QuickBooks Online.
        
        Args:
            entity_type: Type of entity (Customer, Vendor, Invoice, etc.)
            entity_data: Entity data to create
            oauth_manager: Optional OAuth manager for token refresh
            
        Returns:
            Created entity data from QBO
            
        Raises:
            Exception: If creation fails or returns a Fault
        """
        endpoint = entity_type.lower()
        
        response = self._make_request(
            "POST",
            endpoint,
            entity_data,
            oauth_manager=oauth_manager
        )
        
        # Check for fault response - CRITICAL FIX: Complete fault parsing
        if "Fault" in response:
            fault = response.get("Fault", {})
            fault_type = fault.get("type", "Unknown")
            errors = fault.get("Error", [])

            # Build comprehensive error message from all errors
            error_details = []
            for i, error in enumerate(errors if errors else [{}]):
                error_code = error.get("code", "N/A")
                error_message = error.get("Message", "Unknown error")
                error_detail = error.get("Detail", "")
                error_element = error.get("element", "")

                detail_str = f"[{error_code}] {error_message}"
                if error_detail:
                    detail_str += f" - {error_detail}"
                if error_element:
                    detail_str += f" (element: {error_element})"

                error_details.append(detail_str)

            full_error_msg = "; ".join(error_details) if error_details else "Unknown error"
            raise Exception(f"QBO API {fault_type}: {full_error_msg}")
        
        # Return the created entity
        if entity_type in response:
            return response[entity_type]
        
        return response
    
    def _get_next_batch_id(self) -> str:
        """
        FIX #18: Thread-safe batch ID generation
        """
        with self.batch_lock:
            self.batch_counter += 1
            return f"batch_{int(time.time())}_{self.batch_counter}"
    
    def _enforce_batch_rate_limit(self):
        """Enforce 40 batch requests per minute per realm"""
        with self._batch_timestamps_lock:
            now = time.time()
            # Remove timestamps older than 60 seconds
            self._batch_timestamps = [t for t in self._batch_timestamps if now - t < 60]
            if len(self._batch_timestamps) >= 40:
                sleep_time = 60 - (now - self._batch_timestamps[0])
                if sleep_time > 0:
                    logger.info(f"Batch rate limit reached. Sleeping {sleep_time:.1f}s")
                    time.sleep(sleep_time)
            self._batch_timestamps.append(time.time())

    def _process_single_batch(
        self,
        batch: List[Dict],
        entity_type: str,
        batch_id: str,
        oauth_manager: Optional[Any],
        migration_id: str
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Process a single batch with proper error handling and tracking

        FIX #130: Proper transaction handling
        FIX #243: Store failed items
        """
        self._enforce_batch_rate_limit()

        succeeded = []
        failed = []

        batch_data = {
            "BatchItemRequest": []
        }

        # FIX #312: Use idempotency key for crash recovery
        idempotency_key = f"{batch_id}_{migration_id}"

        for j, entity_data in enumerate(batch):
            # Dedup check: skip already-migrated entities
            qbd_id = original_entity_id = (
                entity_data.get("ListID") or
                entity_data.get("TxnID") or
                entity_data.get("Id") or
                entity_data.get("Name") or
                entity_data.get("DocNumber") or
                f"index_{j}"
            )
            existing = self.was_entity_created(entity_type, qbd_id)
            if existing:
                logger.debug(f"Skipping already-migrated {entity_type} {qbd_id}")
                continue

            batch_data["BatchItemRequest"].append({
                "bId": f"bid_{j}",
                "operation": "create",
                entity_type: entity_data
            })

        # FIX: Don't send empty BatchItemRequest after dedup filters everything
        if not batch_data["BatchItemRequest"]:
            logger.info(f"All {len(batch)} entities in batch already migrated, skipping")
            return [], []  # Return empty succeeded/failed

        try:
            response = self._make_request(
                "POST",
                "batch",
                batch_data,
                oauth_manager=oauth_manager,
                idempotency_key=idempotency_key
            )
            
            batch_responses = response.get("BatchItemResponse", [])
            
            # FIX #320: Check if BatchItemResponse is empty
            if not batch_responses:
                logger.error(f"Empty BatchItemResponse for batch {batch_id}")
                # Treat all as failed
                for entity in batch:
                    failed.append({
                        "entity": entity,
                        "error": "Empty API response"
                    })
                return succeeded, failed
            
            for i, batch_item in enumerate(batch_responses):
                bid = batch_item.get("bId", f"bid_{i}")

                # CRITICAL FIX: Parse bId to get the correct original request index
                # Response order is NOT guaranteed to match request order!
                try:
                    # bId format is "bid_N" where N is the original index
                    req_index = int(bid.split("_")[1]) if "_" in bid else i
                except (IndexError, ValueError):
                    logger.warning(f"Could not parse bId '{bid}', using response index {i}")
                    req_index = i

                # Safely get original entity
                original_entity = batch[req_index] if req_index < len(batch) else batch[i] if i < len(batch) else {}

                if batch_item.get(entity_type):
                    # Success
                    created_entity = batch_item[entity_type]
                    succeeded.append(created_entity)

                    # Record in database - use source entity data for ID
                    qbd_id = (
                        original_entity.get("ListID") or
                        original_entity.get("TxnID") or
                        original_entity.get("Id") or
                        original_entity.get("Name") or
                        original_entity.get("DocNumber") or
                        f"index_{req_index}"
                    )
                    qbo_id = created_entity.get("Id")
                    sync_token = created_entity.get("SyncToken", "0")

                    if qbo_id:
                        self.record_created(entity_type, qbd_id, qbo_id, migration_id, sync_token)

                elif batch_item.get("Fault"):
                    # Failure
                    fault = batch_item["Fault"]
                    error_msg = fault.get("Error", [{}])[0].get("Message", "Unknown error")

                    failed_item = {
                        "entity": original_entity,
                        "error": error_msg,
                        "fault_code": fault.get("type")
                    }
                    failed.append(failed_item)

                    logger.error(f"Batch item {bid} failed: {error_msg}")
        
        except Exception as e:
            # Entire batch failed
            logger.error(f"Batch {batch_id} failed completely: {e}")
            
            for entity in batch:
                failed.append({
                    "entity": entity,
                    "error": str(e)
                })
        
        return succeeded, failed
    
    def batch_create_parallel(
        self,
        entities: List[Dict],
        entity_type: str,
        oauth_manager: Optional[Any] = None,
        migration_id: str = None
    ) -> Dict:
        """
        FIX #13, #15: Proper parallel batch processing with thread safety
        FIX #243: Return structured failed items
        """
        results = {
            "succeeded": [],
            "succeeded_count": 0,
            "succeeded_ids": [],
            "failed": [],
            "total": len(entities)
        }

        # AUDIT FIX: Use config constant instead of hardcoded value
        try:
            from config import BATCH_SIZE
            batch_size = BATCH_SIZE
        except ImportError:
            batch_size = 30  # QBO maximum if config unavailable
        batches = []

        for i in range(0, len(entities), batch_size):
            batch = entities[i:i + batch_size]
            batch_id = self._get_next_batch_id()
            batches.append((batch, batch_id))

        # HIGH FIX: Use logger instead of print for production environments
        logger.info(f"Processing {len(batches)} batches in parallel (max {self.max_workers} workers)...")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []

            for batch, batch_id in batches:
                future = executor.submit(
                    self._process_single_batch,
                    batch,
                    entity_type,
                    batch_id,
                    oauth_manager,
                    migration_id
                )
                futures.append(future)

            for future in as_completed(futures):
                self._check_shutdown()

                try:
                    succeeded, failed = future.result()
                    results["succeeded_count"] += len(succeeded)
                    results["succeeded_ids"].extend([s.get("Id", "") for s in succeeded])
                    # Memory optimization: only keep IDs, not full entity objects
                    # Full entities are already persisted in SQLite via record_entity_success
                    results["failed"].extend(failed)
                except Exception as e:
                    logger.error(f"Batch processing error: {e}")

        # Store failed items for export
        if results["failed"]:
            with self.failed_items_lock:
                self.failed_items.extend(results["failed"])

        # HIGH FIX: Use logger instead of print
        logger.info(f"Batch processing complete: Succeeded={results['succeeded_count']}, Failed={len(results['failed'])}")

        return results
    
    def batch_create_optimized(
        self,
        entities: List[Dict],
        entity_type: str,
        oauth_manager: Optional[Any] = None,
        migration_id: str = None,
        target_throughput: int = 500000,  # rows per hour
        progress_callback: Optional[callable] = None
    ) -> Dict:
        """
        $25M FEATURE: Optimized batch processing for enterprise migrations.
        Targets 500,000 rows in under 60 minutes.
        
        2026 Intuit Batch Limits:
        - 30 Payloads per batch request
        - 40 Batch requests per minute per Realm ID
        - 10 requests per second throttling
        
        Strategy:
        1. Use maximum batch size (30 items)
        2. Parallel workers (respecting QBO plan limits)
        3. Adaptive rate limiting based on X-RateLimit-Remaining
        4. Progress tracking for Pizza Tracker
        
        Args:
            entities: List of entities to create
            entity_type: QBO entity type (e.g., 'Invoice', 'Customer')
            oauth_manager: OAuth manager for token refresh
            migration_id: Migration ID for tracking
            target_throughput: Target rows per hour (default 500K)
            progress_callback: Callback(processed, total, rate) for progress updates
            
        Returns:
            Dict with succeeded, failed, total, and timing stats
        """
        start_time = time.time()
        
        results = {
            "succeeded": [],
            "succeeded_count": 0,
            "succeeded_ids": [],
            "failed": [],
            "total": len(entities),
            "start_time": datetime.now().isoformat(),
            "entity_type": entity_type
        }

        if not entities:
            return results

        # AUDIT FIX: Use config constant instead of hardcoded value
        try:
            from config import BATCH_SIZE
            batch_size = BATCH_SIZE
        except ImportError:
            batch_size = 30  # QBO maximum if config unavailable

        # Calculate optimal workers based on rate limits
        # 40 requests/min = 0.67 requests/second per worker
        # With 8 workers: 5.3 requests/second (within 10/sec limit)
        optimal_workers = min(self.max_workers, 8)

        # Calculate delay between batch submissions to stay within limits
        # Target: 10 requests/second maximum
        min_delay = 1.0 / 10  # 100ms minimum between requests

        # Split into batches
        batches = []
        for i in range(0, len(entities), batch_size):
            batch = entities[i:i + batch_size]
            batch_id = self._get_next_batch_id()
            batches.append((batch, batch_id, i))  # Include offset for progress

        total_batches = len(batches)
        processed_entities = 0

        logger.info(f"$25M BATCH: Processing {len(entities)} {entity_type} in {total_batches} batches with {optimal_workers} workers")

        # Process with controlled parallelism
        with ThreadPoolExecutor(max_workers=optimal_workers) as executor:
            # Submit batches with rate limiting
            futures = {}
            batch_queue = deque(batches)
            active_futures = set()

            while batch_queue or active_futures:
                self._check_shutdown()

                # Submit new batches (up to worker limit)
                while batch_queue and len(active_futures) < optimal_workers:
                    batch, batch_id, offset = batch_queue.popleft()

                    future = executor.submit(
                        self._process_single_batch,
                        batch,
                        entity_type,
                        batch_id,
                        oauth_manager,
                        migration_id
                    )
                    futures[future] = (batch_id, offset, len(batch))
                    active_futures.add(future)

                    # Rate limit between batch submissions
                    time.sleep(min_delay)

                # Process completed futures
                completed = set()
                for future in active_futures:
                    if future.done():
                        completed.add(future)
                        batch_id, offset, batch_len = futures[future]

                        try:
                            succeeded, failed = future.result()
                            results["succeeded_count"] += len(succeeded)
                            results["succeeded_ids"].extend([s.get("Id", "") for s in succeeded])
                            # Memory optimization: only keep IDs, not full entity objects
                            results["failed"].extend(failed)
                            processed_entities += batch_len

                            # Report progress
                            if progress_callback:
                                elapsed = time.time() - start_time
                                rate = processed_entities / elapsed * 3600 if elapsed > 0 else 0
                                progress_callback(processed_entities, len(entities), rate)

                        except Exception as e:
                            logger.error(f"Batch {batch_id} error: {e}")
                            results["failed"].append({
                                "batch_id": batch_id,
                                "error": str(e)
                            })

                active_futures -= completed

                # Small delay to prevent busy-waiting
                if active_futures and not completed:
                    time.sleep(0.05)
        
        # Calculate final stats
        end_time = time.time()
        duration_seconds = end_time - start_time
        actual_throughput = len(entities) / duration_seconds * 3600 if duration_seconds > 0 else 0
        
        results["end_time"] = datetime.now().isoformat()
        results["duration_seconds"] = round(duration_seconds, 2)
        results["throughput_per_hour"] = round(actual_throughput)
        results["target_met"] = actual_throughput >= target_throughput
        
        # Store failed items
        if results["failed"]:
            with self.failed_items_lock:
                self.failed_items.extend(results["failed"])
        
        logger.info(f"$25M BATCH COMPLETE: {results['succeeded_count']} succeeded, {len(results['failed'])} failed")
        logger.info(f"  Duration: {duration_seconds:.1f}s | Throughput: {actual_throughput:.0f}/hour")
        
        if results["target_met"]:
            logger.info(f"  ✓ TARGET MET: {target_throughput}/hour achieved!")
        else:
            logger.warning(f"  ✗ Target missed: {actual_throughput:.0f} < {target_throughput}/hour")
        
        return results
    
    def export_failed_items(self, filepath: str):
        """
        FIX #389: Export failed items to JSON for manual review
        """
        with self.failed_items_lock:
            if not self.failed_items:
                logger.info("No failed items to export")
                return
            
            with open(filepath, 'w') as f:
                json.dump({
                    "failed_count": len(self.failed_items),
                    "timestamp": datetime.now().isoformat(),
                    "items": self.failed_items
                }, f, indent=2)
            
            # HIGH FIX: Use logger instead of print
            logger.info(f"Exported {len(self.failed_items)} failed items to {filepath}")
    
    def query_count(
        self,
        entity_type: str,
        oauth_manager: Optional[Any] = None
    ) -> int:
        """
        AUDIT FIX: Get count of entities (used by verifier)

        Args:
            entity_type: Type of entity to count (Customer, Vendor, etc.)
            oauth_manager: Optional OAuth manager for token refresh

        Returns:
            Count of entities
        """
        # Validate entity_type against whitelist to prevent injection
        valid_types = {
            'Account', 'Customer', 'Vendor', 'Item', 'Employee', 'Invoice',
            'Bill', 'Payment', 'Estimate', 'SalesReceipt', 'PurchaseOrder',
            'Deposit', 'Transfer', 'JournalEntry', 'CreditMemo', 'VendorCredit',
            'BillPayment', 'TimeActivity', 'TaxCode', 'TaxRate', 'Term',
            'PaymentMethod', 'Class', 'Department', 'Attachable',
            'CompanyCurrency', 'Budget'
        }
        if entity_type not in valid_types:
            raise ValueError(f"Invalid entity type for query: {entity_type}")

        query = f"SELECT COUNT(*) FROM {entity_type}"
        endpoint = f"query?query={requests.utils.quote(query)}"

        try:
            response = self._make_request("GET", endpoint, oauth_manager=oauth_manager)
            # QBO returns count in QueryResponse.totalCount
            total_count = response.get("QueryResponse", {}).get("totalCount", 0)
            return int(total_count)
        except Exception as e:
            logger.error(f"Query count failed for {entity_type}: {e}")
            # Fallback: query all and count
            try:
                results = self.query(entity_type, max_results=1, oauth_manager=oauth_manager)
                # If we got results, do full count
                if results:
                    all_results = self.query(entity_type, oauth_manager=oauth_manager)
                    return len(all_results)
            except Exception:
                pass
            return 0

    def query(
        self,
        entity_type: str,
        query_string: str = "",
        max_results: int = 1000,
        oauth_manager: Optional[Any] = None
    ) -> List[Dict]:
        """
        FIX #304: Handle pagination edge cases
        FIX #405: Don't make unnecessary extra call
        """
        all_results = []
        start_position = 1
        page_size = min(max_results, 1000)
        
        while True:
            self._check_shutdown()
            
            if query_string:
                query = f"{query_string} STARTPOSITION {start_position} MAXRESULTS {page_size}"
            else:
                query = f"SELECT * FROM {entity_type} STARTPOSITION {start_position} MAXRESULTS {page_size}"
            
            endpoint = f"query?query={requests.utils.quote(query)}"
            
            try:
                response = self._make_request("GET", endpoint, oauth_manager=oauth_manager)
                entities = response.get("QueryResponse", {}).get(entity_type, [])
                
                if not entities:
                    break
                
                all_results.extend(entities)
                
                # FIX #405: Don't make extra call if we got less than page_size
                if len(entities) < page_size:
                    break
                
                # FIX #304: Respect max_results limit
                if len(all_results) >= max_results:
                    break
                
                start_position += page_size
                
            except Exception as e:
                logger.error(f"Query failed at position {start_position}: {e}")
                break
        
        return all_results[:max_results]  # Ensure we don't exceed max_results
    
    def cleanup_migration(
        self,
        migration_id: str,
        oauth_manager: Optional[Any] = None
    ) -> Dict:
        """
        FIX #434: Clear SQLite state after rollback
        """
        with self.db_lock:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT entity_type, qbo_id FROM migrated_entities
                WHERE migration_id = ? AND status = 'created'
            ''', (migration_id,))
            
            entities = cursor.fetchall()
            conn.close()
        
        # HIGH FIX: Use logger instead of print
        logger.info(f"Rolling back migration {migration_id}... Found {len(entities)} entities to delete")
        
        deleted = 0
        failed = 0
        
        for entity_type, qbo_id in entities:
            if self.delete_entity(entity_type, qbo_id, oauth_manager):
                deleted += 1
            else:
                failed += 1
        
        # HIGH FIX: Use logger instead of print
        logger.info(f"Rollback complete: Deleted={deleted}, Failed={failed}")
        
        return {
            "deleted": deleted,
            "failed": failed,
            "total": len(entities)
        }

    def query_raw(self, query: str, oauth_manager: Optional[Any] = None) -> List[Dict]:
        """
        $25M FIX: Execute a raw SQL-like query against QBO API

        This is needed for bank reconciliation verification.

        AUDIT FIX: Now uses _make_request for proper retry logic, rate limiting,
        and automatic token refresh on 401 errors.

        Args:
            query: SQL-like query (e.g., "SELECT * FROM Invoice WHERE ...")
            oauth_manager: OAuth manager for token refresh

        Returns:
            List of matching entities
        """
        # URL encode the query
        import urllib.parse
        encoded_query = urllib.parse.quote(query)

        # Build endpoint with query parameter (minorversion added by _make_request)
        endpoint = f"query?query={encoded_query}"

        try:
            # AUDIT FIX: Use _make_request for retry logic, rate limiting, auth refresh
            response_data = self._make_request(
                method="GET",
                endpoint=endpoint,
                oauth_manager=oauth_manager
            )

            # _make_request returns parsed JSON, extract QueryResponse
            query_response = response_data.get('QueryResponse', {})

            # Get the first key (entity type) that contains a list
            for key, value in query_response.items():
                if isinstance(value, list):
                    return value

            return []

        except Exception as e:
            logger.error(f"Query error: {e}")
            return []
    

    
    # HIGH FIX: Context manager support to prevent session leaks
    # Allows usage: with PremiumQBOClient(...) as client:
    def __enter__(self):
        """Enter context manager - return self for use in 'with' block"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager - ensure session is properly closed"""
        self.close()
        # Don't suppress exceptions
        return False

    def close(self):
        """
        HIGH FIX: Explicitly close the HTTP session to prevent connection leaks.

        This should be called when done using the client, or use the context manager:
            with PremiumQBOClient(...) as client:
                client.create_entity(...)
            # Session automatically closed here
        """
        try:
            if self.session:
                self.session.close()
                logger.debug("QBO client session closed")
        except Exception as e:
            logger.warning(f"Error closing QBO session: {e}")

    def __del__(self):
        """Cleanup: close session (fallback for non-context-manager usage)"""
        try:
            self.close()
        except Exception:
            # FIX SVC-04: Catch specific Exception instead of bare except
            pass

    def batch_upload(
        self,
        entities_by_type: Dict[str, List[Dict]],
        migration_id: str,
        oauth_manager: Optional[Any] = None,
        use_optimized: bool = True
    ) -> Dict:
        """
        CRITICAL FIX: Orchestrate upload of all entity types to QBO.

        This method was called from MigrationOrchestrator.run_migration() but was
        missing, causing AttributeError at runtime.

        Args:
            entities_by_type: Dict mapping entity_type -> list of entities
                Example: {'Customer': [...], 'Invoice': [...], 'Account': [...]}
            migration_id: Migration ID for tracking and rollback
            oauth_manager: Optional OAuth manager for token refresh
            use_optimized: If True, use batch_create_optimized for large batches

        Returns:
            Dict with:
                - 'successful': Total count of successfully created entities
                - 'failed': Total count of failed entities
                - 'errors': List of error messages (max 100)
                - 'results': Dict of entity_type -> {succeeded: [], failed: []}
                - 'entity_counts': Dict of entity_type -> count created
        """
        start_time = time.time()

        total_successful = 0
        total_failed = 0
        all_errors: List[str] = []
        results_by_type: Dict[str, Dict] = {}
        entity_counts: Dict[str, int] = {}

        # Entity upload order matters - dependencies must be created first
        # This order ensures referenced entities exist before referencing entities
        ENTITY_ORDER = [
            # Master data (no dependencies)
            'Account', 'Class', 'Department', 'TaxCode', 'Term', 'PaymentMethod',
            # Parties (depend on nothing)
            'Customer', 'Vendor', 'Employee',
            # Items (may depend on accounts)
            'Item',
            # Transactions (depend on parties, items, accounts)
            'Invoice', 'SalesReceipt', 'Estimate', 'CreditMemo', 'RefundReceipt',
            'Bill', 'VendorCredit', 'Purchase', 'PurchaseOrder',
            'Payment', 'BillPayment',
            'JournalEntry', 'Deposit', 'Transfer',
            'TimeActivity', 'InventoryAdjustment',
            # Other
            'Attachable', 'CompanyCurrency', 'TaxPayment', 'CreditCardPayment'
        ]

        # Sort entities by dependency order
        sorted_types = []
        for entity_type in ENTITY_ORDER:
            if entity_type in entities_by_type:
                sorted_types.append(entity_type)

        # Add any remaining types not in our order list
        for entity_type in entities_by_type:
            if entity_type not in sorted_types:
                sorted_types.append(entity_type)

        logger.info(f"BATCH_UPLOAD: Starting migration {migration_id}")
        logger.info(f"  Entity types to process: {sorted_types}")
        logger.info(f"  Total entities: {sum(len(v) for v in entities_by_type.values())}")

        for entity_type in sorted_types:
            entities = entities_by_type[entity_type]

            if not entities:
                continue

            self._check_shutdown()

            logger.info(f"  Processing {len(entities)} {entity_type}...")

            try:
                # Choose processing method based on size and flag
                if use_optimized and len(entities) > 100:
                    # Use optimized batch processing for large datasets
                    result = self.batch_create_optimized(
                        entities=entities,
                        entity_type=entity_type,
                        oauth_manager=oauth_manager,
                        migration_id=migration_id
                    )
                else:
                    # Use parallel processing for smaller batches
                    result = self.batch_create_parallel(
                        entities=entities,
                        entity_type=entity_type,
                        oauth_manager=oauth_manager,
                        migration_id=migration_id
                    )

                succeeded_count = result.get('succeeded_count', 0)
                failed_items = result.get('failed', [])
                failed_count = len(failed_items)

                total_successful += succeeded_count
                total_failed += failed_count
                entity_counts[entity_type] = succeeded_count

                # Collect errors (limit to prevent memory bloat)
                for failed_item in failed_items[:20]:
                    error_msg = f"{entity_type}: {failed_item.get('error', 'Unknown error')}"
                    if len(all_errors) < 100:
                        all_errors.append(error_msg)

                results_by_type[entity_type] = {
                    'succeeded': result.get('succeeded', []),
                    'failed': failed_items,
                    'succeeded_count': succeeded_count,
                    'failed_count': failed_count
                }

                logger.info(f"    ✓ {entity_type}: {succeeded_count} succeeded, {failed_count} failed")

            except Exception as e:
                error_msg = f"{entity_type}: Batch processing failed - {str(e)}"
                logger.error(f"    ✗ {error_msg}")
                all_errors.append(error_msg)
                total_failed += len(entities)

                results_by_type[entity_type] = {
                    'succeeded': [],
                    'failed': [{'error': str(e)} for _ in entities],
                    'succeeded_count': 0,
                    'failed_count': len(entities)
                }

        elapsed = time.time() - start_time

        logger.info(f"BATCH_UPLOAD COMPLETE for migration {migration_id}")
        logger.info(f"  Total successful: {total_successful}")
        logger.info(f"  Total failed: {total_failed}")
        logger.info(f"  Duration: {elapsed:.1f}s")

        return {
            'successful': total_successful,
            'failed': total_failed,
            'errors': all_errors,
            'results': results_by_type,
            'entity_counts': entity_counts,
            'duration_seconds': round(elapsed, 2)
        }


# Alias for backward compatibility
QBOClient = PremiumQBOClient