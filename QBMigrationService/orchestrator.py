"""
Migration Orchestrator - Single Entry Point for End-to-End Migration

This module provides a unified interface for QBMigrationServer workers to call
QBMigrationService functionality without needing to import individual modules.

Usage:
    from orchestrator import MigrationOrchestrator

    orchestrator = MigrationOrchestrator(
        qbo_client_id="...",
        qbo_client_secret="...",
        qbo_refresh_token="...",
        realm_id="...",
        qbo_environment="sandbox",
        progress_callback=lambda pct, msg: print(f"{pct}%: {msg}")
    )

    result = orchestrator.run_migration(encrypted_data, encryption_metadata)
"""

import os
import sys
import json
import logging
import time
import uuid
from typing import Dict, Any, Callable, Optional, List, Tuple, TYPE_CHECKING
from datetime import datetime, timezone
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# FIX #35: TYPE_CHECKING for forward references without circular imports
if TYPE_CHECKING:
    from encryption import EncryptionManager
    from oauth_manager import OAuthManager
    from qbo_client import PremiumQBOClient
    from data_transformer import QBDataTransformer
    from verifier import PremiumMigrationVerifier

# Configure logging
logger = logging.getLogger(__name__)


class MigrationOrchestrator:
    """
    Unified orchestrator for QB Desktop → QBO migration.
    
    Handles:
    1. Decryption of uploaded data
    2. Data transformation (31 entity types)
    3. QBO API operations with rate limiting
    4. Trial balance verification
    5. Progress reporting
    """
    
    def __init__(
        self,
        qbo_client_id: str,
        qbo_client_secret: str,
        qbo_refresh_token: str,
        realm_id: str,
        qbo_environment: str = "sandbox",
        progress_callback: Optional[Callable[[int, str], None]] = None,
        log_level: int = logging.INFO
    ):
        """
        Initialize the orchestrator with QBO credentials.
        
        Args:
            qbo_client_id: QuickBooks Online OAuth client ID
            qbo_client_secret: QuickBooks Online OAuth client secret
            qbo_refresh_token: OAuth refresh token
            realm_id: QBO company ID
            qbo_environment: 'sandbox' or 'production'
            progress_callback: Function(percent, message) called for progress updates
            log_level: Logging level
        """
        if not qbo_client_id or not qbo_client_secret or not qbo_refresh_token or not realm_id:
            raise ValueError(
                "All QBO credentials are required: client_id, client_secret, refresh_token, realm_id"
            )

        self.qbo_client_id = qbo_client_id
        self.qbo_client_secret = qbo_client_secret
        self.qbo_refresh_token = qbo_refresh_token
        self.realm_id = realm_id
        self.qbo_environment = qbo_environment
        self.progress_callback = progress_callback or (lambda p, m: None)

        # Set level on our own logger only — don't call basicConfig() which
        # overwrites the caller's logging configuration.
        logger.setLevel(log_level)

        # Will be initialized lazily
        self._encryption_manager = None
        self._oauth_manager = None
        self._qbo_client = None
        self._transformer = None
        self._verifier = None
    
    def _report_progress(self, percent: int, message: str) -> None:
        """Report progress to callback."""
        logger.info(f"[{percent}%] {message}")
        try:
            self.progress_callback(percent, message)
        except Exception as e:
            logger.error(f"progress_callback failed: {e} — caller may not see status updates")

    def _init_encryption(self) -> 'EncryptionManager':
        """Initialize encryption manager"""
        if self._encryption_manager is None:
            from encryption import EncryptionManager
            self._encryption_manager = EncryptionManager()
        return self._encryption_manager

    def _init_oauth(self) -> 'OAuthManager':
        """Initialize OAuth manager"""
        if self._oauth_manager is None:
            from oauth_manager import OAuthManager
            from pathlib import Path
            import config as svc_config

            # Get OAuth URLs from config module
            self._oauth_manager = OAuthManager(
                client_id=self.qbo_client_id,
                client_secret=self.qbo_client_secret,
                refresh_token=self.qbo_refresh_token,
                oauth_token_url=svc_config.OAUTH_TOKEN_URL,
                oauth_introspect_url=svc_config.OAUTH_INTROSPECT_URL,
                oauth_revoke_url=svc_config.OAUTH_REVOKE_URL,
                data_dir=Path(svc_config.DATA_DIR)
            )
        return self._oauth_manager

    def _init_qbo_client(self, access_token: str) -> 'PremiumQBOClient':
        """Initialize or update QBO client with current access token."""
        if self._qbo_client is None:
            from qbo_client import PremiumQBOClient
            import config as svc_config

            self._qbo_client = PremiumQBOClient(
                access_token=access_token,
                base_url=svc_config.BASE_URL,
                db_path=str(svc_config.DATA_DIR / "migration_state.db")
            )
        else:
            # Update access token in case it was refreshed
            self._qbo_client._base_access_token = access_token
        return self._qbo_client

    def _init_transformer(self) -> 'QBDataTransformer':
        """Initialize data transformer"""
        if self._transformer is None:
            from data_transformer import QBDataTransformer
            self._transformer = QBDataTransformer()
        return self._transformer

    def _init_verifier(self, qbo_client: 'PremiumQBOClient') -> 'PremiumMigrationVerifier':
        """Initialize migration verifier"""
        if self._verifier is None:
            from verifier import PremiumMigrationVerifier
            self._verifier = PremiumMigrationVerifier(qbo_client)
        return self._verifier
    
    def run_migration(
        self,
        encrypted_data: bytes,
        encryption_metadata: Dict[str, Any],
        company_name: str = "Unknown",
        timeout_seconds: int = 7200  # 2 hour default timeout
    ) -> Dict[str, Any]:
        """
        Run the complete migration process.

        Args:
            encrypted_data: AES-256-GCM encrypted data from QBDesktopReader
            encryption_metadata: Dict with iv, tag, algorithm, etc.
            company_name: Company name for logging
            timeout_seconds: Maximum time allowed for migration (default: 2 hours)

        Returns:
            Dict with migration results:
            {
                'success': bool,
                'migration_id': str,
                'entities_migrated': {
                    'Customers': 100,
                    'Vendors': 50,
                    ...
                },
                'verification': {...},
                'duration_seconds': float
            }

        Raises:
            TimeoutError: If migration exceeds timeout_seconds
        """
        import signal
        import threading as _threading

        # FIX: Cross-platform timeout protection
        def _migration_timeout_handler(signum, frame):
            raise TimeoutError(
                f"Migration exceeded {timeout_seconds} second ({timeout_seconds // 3600}h) timeout. "
                f"Company: {company_name}. Migration may need to be split into smaller batches."
            )

        old_handler = None
        timer = None

        if hasattr(signal, 'SIGALRM'):
            # Unix: Use SIGALRM for precise timeout
            old_handler = signal.signal(signal.SIGALRM, _migration_timeout_handler)
            signal.alarm(timeout_seconds)
            logger.info(f"Migration timeout set to {timeout_seconds}s (SIGALRM)")
        else:
            # Windows: Use threading.Timer as fallback
            import _thread
            def _timer_timeout():
                logger.error(
                    f"Migration exceeded {timeout_seconds}s timeout (Windows timer). "
                    f"Company: {company_name}. Raising interrupt."
                )
                _thread.interrupt_main()
            timer = _threading.Timer(timeout_seconds, _timer_timeout)
            timer.daemon = True
            timer.start()
            logger.info(f"Migration timeout set to {timeout_seconds}s (threading.Timer)")

        try:
            return self._run_migration_impl(encrypted_data, encryption_metadata, company_name)
        except KeyboardInterrupt:
            raise TimeoutError(
                f"Migration exceeded {timeout_seconds} second ({timeout_seconds // 3600}h) timeout. "
                f"Company: {company_name}. Migration may need to be split into smaller batches."
            )
        finally:
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)
                if old_handler is not None:
                    signal.signal(signal.SIGALRM, old_handler)
            if timer is not None:
                timer.cancel()

    def _run_migration_impl(
        self,
        encrypted_data: bytes,
        encryption_metadata: Dict[str, Any],
        company_name: str = "Unknown"
    ) -> Dict[str, Any]:
        """Internal implementation of migration (called with timeout wrapper)."""
        start_time = datetime.now(timezone.utc)
        migration_id = f"mig_{uuid.uuid4().hex[:16]}"

        logger.info(f"Starting migration {migration_id} for {company_name}")
        transformer = None  # Initialize before try so except block can access it

        # FIX #13: Track created entity IDs for potential rollback
        self._created_entity_ids: Dict[str, List[str]] = defaultdict(list)

        try:
            # Step 1: Decrypt data (5%)
            self._report_progress(5, "Decrypting data")
            
            enc_mgr = self._init_encryption()
            aes_key = encryption_metadata.get('key') or encryption_metadata.get('aes_key')
            if not aes_key:
                raise ValueError("Missing encryption key in metadata (expected 'key' or 'aes_key')")
            iv = encryption_metadata.get('iv')
            if not iv:
                raise ValueError("Missing 'iv' in encryption metadata")
            tag = encryption_metadata.get('tag')
            if not tag:
                raise ValueError("Missing 'tag' in encryption metadata - required for authenticated decryption")

            decrypted_json = enc_mgr.decrypt_chunked(
                encrypted_data,
                key=aes_key,
                iv=iv,
                tag=tag
            )
            
            data = json.loads(decrypted_json)
            if not isinstance(data, dict):
                raise ValueError(f"Expected JSON object from decrypted data, got {type(data).__name__}")
            logger.info(f"Decrypted {len(decrypted_json):,} bytes")

            # Normalize data keys to match entity_order format
            normalized_data = {}
            for key, value in data.items():
                key_map = {
                    # Master lists
                    'account': 'Accounts', 'accounts': 'Accounts',
                    'customer': 'Customers', 'customers': 'Customers',
                    'vendor': 'Vendors', 'vendors': 'Vendors',
                    'item': 'Items', 'items': 'Items',
                    'employee': 'Employees', 'employees': 'Employees',
                    # Configuration lists
                    'class': 'Classes', 'classes': 'Classes',
                    'department': 'Departments', 'departments': 'Departments',
                    'term': 'Terms', 'terms': 'Terms',
                    'paymentmethod': 'PaymentMethods', 'paymentmethods': 'PaymentMethods',
                    'taxcode': 'TaxCodes', 'taxcodes': 'TaxCodes',
                    'salestaxcodes': 'TaxCodes',
                    'taxrate': 'TaxRates', 'taxrates': 'TaxRates',
                    'taxagency': 'TaxAgencies', 'taxagencies': 'TaxAgencies',
                    'companycurrency': 'CompanyCurrencies', 'companycurrencies': 'CompanyCurrencies',
                    'currencies': 'CompanyCurrencies',
                    # Transactions
                    'invoice': 'Invoices', 'invoices': 'Invoices',
                    'bill': 'Bills', 'bills': 'Bills',
                    'payment': 'Payments', 'payments': 'Payments',
                    'receivepayments': 'Payments',
                    'estimate': 'Estimates', 'estimates': 'Estimates',
                    'salesreceipt': 'SalesReceipts', 'salesreceipts': 'SalesReceipts',
                    'creditmemo': 'CreditMemos', 'creditmemos': 'CreditMemos',
                    'vendorcredit': 'VendorCredits', 'vendorcredits': 'VendorCredits',
                    'billpayment': 'BillPayments', 'billpayments': 'BillPayments',
                    'purchaseorder': 'PurchaseOrders', 'purchaseorders': 'PurchaseOrders',
                    'purchase': 'Purchases', 'purchases': 'Purchases',
                    'checks': 'Purchases', 'creditcardcharges': 'Purchases',
                    'journalentry': 'JournalEntries', 'journalentries': 'JournalEntries',
                    'deposit': 'Deposits', 'deposits': 'Deposits',
                    'transfer': 'Transfers', 'transfers': 'Transfers',
                    'refundreceipt': 'RefundReceipts', 'refundreceipts': 'RefundReceipts',
                    'timeactivity': 'TimeActivities', 'timeactivities': 'TimeActivities',
                    'inventoryadjustment': 'InventoryAdjustments', 'inventoryadjustments': 'InventoryAdjustments',
                    'taxpayment': 'TaxPayments', 'taxpayments': 'TaxPayments',
                    'salestaxpayments': 'TaxPayments',
                    'attachable': 'Attachables', 'attachables': 'Attachables',
                    # New entity types
                    'salesorder': 'SalesOrders', 'salesorders': 'SalesOrders',
                    'itemreceipt': 'ItemReceipts', 'itemreceipts': 'ItemReceipts',
                    'charge': 'Charges', 'charges': 'Charges',
                    'othername': 'OtherNames', 'othernames': 'OtherNames',
                    'datedriventerm': 'DateDrivenTerms', 'datedriventerms': 'DateDrivenTerms',
                    'lead': 'Leads', 'leads': 'Leads',
                    'buildassembly': 'BuildAssemblies', 'buildassemblies': 'BuildAssemblies',
                    'inventorytransfer': 'InventoryTransfers', 'inventorytransfers': 'InventoryTransfers',
                    'dataextension': 'DataExtensions', 'dataextensions': 'DataExtensions',
                    'salesrep': 'SalesReps', 'salesreps': 'SalesReps',
                    'customermessage': 'CustomerMessages', 'customermessages': 'CustomerMessages',
                    'jobtype': 'JobTypes', 'jobtypes': 'JobTypes',
                    'vendortype': 'VendorTypes', 'vendortypes': 'VendorTypes',
                    'pricelevel': 'PriceLevels', 'pricelevels': 'PriceLevels',
                    'salestaxgroup': 'SalesTaxGroups', 'salestaxgroups': 'SalesTaxGroups',
                    'shipmethod': 'ShipMethods', 'shipmethods': 'ShipMethods',
                    'inventorysite': 'InventorySites', 'inventorysites': 'InventorySites',
                    'customertype': 'CustomerTypes', 'customertypes': 'CustomerTypes',
                }
                mapped = key_map.get(key.lower(), key)
                normalized_data[mapped] = value
            data = normalized_data

            # Step 2: OAuth refresh (10%)
            self._report_progress(10, "Authenticating with QuickBooks Online")
            
            oauth_mgr = self._init_oauth()
            access_token = oauth_mgr.get_valid_access_token()
            
            if not access_token:
                raise Exception("Failed to obtain valid access token")
            
            # Step 3: Initialize QBO client (15%)
            self._report_progress(15, "Connecting to QuickBooks Online")
            
            qbo_client = self._init_qbo_client(access_token)
            transformer = self._init_transformer()

            # Step 3b: Query existing TaxAgencies from QBO (read-only entities)
            # TaxAgency cannot be created via API — must map to existing ones
            try:
                existing_agencies = qbo_client.query_tax_agencies(
                    oauth_manager=oauth_mgr)
                for agency in existing_agencies:
                    agency_id = agency.get('Id')
                    agency_name = agency.get('DisplayName', '')
                    if agency_id and agency_name:
                        transformer.id_mapping['tax_agencies'][agency_name] = agency_id
                logger.info(
                    f"Found {len(existing_agencies)} existing TaxAgencies in QBO")
            except Exception as e:
                logger.warning(f"Could not query TaxAgencies: {e}")

            # Step 4: Migrate entities (20-85%)
            entity_id_mappings = {}  # Separate dict for ID mappings
            entity_counts = {}       # Separate dict for counts
            total_failed = 0
            total_skipped = 0

            # Entity migration order - respects dependencies (parents before children)
            # Follows data_transformer._get_transformation_order() phases:
            #   Phase 1: Configuration lists (must exist before referencing entities)
            #   Phase 2: Chart of accounts
            #   Phase 3: Master lists (customers, vendors, items)
            #   Phase 4: Opening balances
            #   Phase 5: Transactions (depend on accounts + master lists)
            #   Phase 6: Attachments (reference all other entities)
            entity_order = [
                # Phase 0: Skip-with-logging types (no QBO creation, just log)
                # These run first so their ID mappings are available if needed
                ('SalesReps', 20, 20),
                ('CustomerMessages', 20, 20),
                ('JobTypes', 20, 20),
                ('VendorTypes', 20, 20),
                ('PriceLevels', 20, 20),
                ('ShipMethods', 20, 20),
                ('DataExtensions', 20, 20),
                ('InventorySites', 20, 20),
                ('SalesTaxGroups', 20, 20),
                # Phase 1: Configuration (20-25%)
                ('CompanyCurrencies', 20, 21),
                ('TaxAgencies', 21, 22),
                ('TaxRates', 22, 22),
                ('TaxCodes', 22, 23),
                ('Terms', 23, 23),
                ('DateDrivenTerms', 23, 23),
                ('PaymentMethods', 23, 24),
                ('Classes', 24, 25),
                ('Departments', 25, 25),
                # Phase 2: Chart of Accounts (25-35%)
                ('Accounts', 25, 35),
                # Phase 3: Master Lists (35-50%)
                ('Customers', 35, 40),
                ('Leads', 40, 41),       # -> inactive Customer
                ('Vendors', 41, 45),
                ('OtherNames', 45, 46),  # -> Vendor
                ('Employees', 46, 49),
                ('Items', 49, 55),
                # Phase 4: Opening Balances (55-60%)
                ('JournalEntries', 55, 58),
                ('InventoryAdjustments', 58, 60),
                # Phase 5: Transactions (60-84%)
                ('Estimates', 60, 62),
                ('SalesOrders', 62, 63),   # -> Estimate
                ('Invoices', 63, 67),
                ('Charges', 67, 68),       # -> Invoice
                ('SalesReceipts', 68, 69),
                ('PurchaseOrders', 69, 70),
                ('Purchases', 70, 72),
                ('Bills', 72, 74),
                ('ItemReceipts', 74, 75),  # -> Bill
                ('Payments', 75, 77),
                ('BillPayments', 77, 78),
                ('Deposits', 78, 79),
                ('Transfers', 79, 80),
                ('CreditMemos', 80, 81),
                ('VendorCredits', 81, 81),
                ('RefundReceipts', 81, 82),
                ('TimeActivities', 82, 83),
                ('TaxPayments', 83, 84),
                # Phase 5b: Skip-only transactions (no QBO equivalent)
                ('BuildAssemblies', 84, 84),
                ('InventoryTransfers', 84, 84),
                # Phase 6: Attachments (84-85%)
                ('Attachables', 84, 85),
            ]

            for entity_name, start_pct, end_pct in entity_order:
                if entity_name in data and data[entity_name]:
                    self._report_progress(start_pct, f"Migrating {entity_name}")

                    # BATCH API: Use batch migration for 6-14x throughput improvement
                    # Sends up to 30 entities per HTTP request with parallel workers
                    # Falls back to sequential for TaxService entities and handles
                    # parent-child ordering via layered batch processing
                    success, failed, skipped = self._migrate_entity_batch(
                        qbo_client,
                        transformer,
                        entity_name,
                        data[entity_name],
                        entity_id_mappings,  # Pass mappings dict
                        oauth_mgr,  # Auto-refresh tokens during long migrations
                        migration_id=migration_id  # For SQLite dedup & crash recovery
                    )

                    entity_counts[entity_name] = success
                    total_failed += failed
                    total_skipped += skipped
                    logger.info(f"Migrated {success} {entity_name} ({failed} failed, {skipped} skipped)")

            # Step 5: Verify migration (85-95%)
            self._report_progress(85, "Verifying migration")

            verifier = self._init_verifier(qbo_client)
            verification_result = verifier.verify_migration(
                entities=data,
                upload_result={'successful': sum(entity_counts.values()), 'failed': total_failed},
                oauth_manager=oauth_mgr
            )

            # Step 6: Complete (100%)
            self._report_progress(100, "Migration complete")

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Collect transformer diagnostics for the caller
            transformer_stats = dict(transformer.stats)
            # Convert defaultdict to regular dict for JSON serialization
            transformer_stats['by_entity_type'] = dict(transformer_stats.get('by_entity_type', {}))

            result = {
                'success': True,
                'migration_id': migration_id,
                'company_name': company_name,
                'entities_migrated': entity_counts,  # Use counts, not mappings
                'total_failed': total_failed,
                'total_skipped': total_skipped,
                'verification': verification_result,
                'manual_review': transformer.manual_review,
                'transformer_stats': transformer_stats,
                'duration_seconds': duration,
                'completed_at': datetime.now(timezone.utc).isoformat()
            }

            if transformer.manual_review:
                logger.warning(
                    f"Migration {migration_id}: {len(transformer.manual_review)} "
                    f"entities flagged for manual review")
            if transformer.stats.get('unsupported_entities'):
                logger.warning(
                    f"Migration {migration_id}: {transformer.stats['unsupported_entities']} "
                    f"entities skipped (no transform method)")

            logger.info(f"Migration {migration_id} completed in {duration:.1f}s")
            return result
            
        except Exception as e:
            logger.exception(f"Migration {migration_id} failed: {str(e)}")
            
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            # Preserve partial progress and manual_review even on failure
            error_result = {
                'success': False,
                'migration_id': migration_id,
                'error': str(e),
                'duration_seconds': duration,
                'failed_at': datetime.now(timezone.utc).isoformat()
            }
            # Include manual_review if transformer was initialized before crash
            try:
                if transformer and hasattr(transformer, 'manual_review'):
                    error_result['manual_review'] = transformer.manual_review
                if transformer and hasattr(transformer, 'stats'):
                    ts = dict(transformer.stats)
                    ts['by_entity_type'] = dict(ts.get('by_entity_type', {}))
                    error_result['transformer_stats'] = ts
            except Exception:
                pass  # Don't let diagnostic collection mask the real error
            return error_result
    
    def _migrate_entity(
        self,
        qbo_client: 'PremiumQBOClient',
        transformer: 'QBDataTransformer',
        entity_name: str,
        source_data: List[Dict[str, Any]],
        existing_maps: Dict[str, Dict[str, str]],
        oauth_manager: Optional['OAuthManager'] = None
    ) -> Tuple[int, int, int]:
        """
        Migrate a single entity type.

        Args:
            qbo_client: Initialized QBO client
            transformer: Data transformer
            entity_name: Name of entity type
            source_data: List of source records
            existing_maps: Maps of already-migrated entities (for references)
            oauth_manager: OAuth manager for automatic token refresh (RELIABILITY FIX)

        Returns:
            Tuple of (success_count, fail_count, skipped_count)
        """
        success_count = 0
        fail_count = 0
        skipped_count = 0

        # Use class-level PLURAL_TO_SINGULAR constant (avoid duplicate definition)
        api_entity_type = self.PLURAL_TO_SINGULAR.get(entity_name, entity_name)

        for record in source_data:
            try:
                # Crash recovery: skip entities already created in a prior run
                # NOTE: Must check both PascalCase and camelCase because
                # normalize_extractor_fields() hasn't run yet at this point.
                source_id = self._extract_source_id(record)
                if source_id:
                    existing_qbo_id = qbo_client.was_entity_created(
                        api_entity_type, source_id)
                    if existing_qbo_id:
                        if entity_name not in existing_maps:
                            existing_maps[entity_name] = {}
                        existing_maps[entity_name][source_id] = existing_qbo_id
                        skipped_count += 1
                        continue

                # Transform to QBO format
                # AUDIT FIX: Use the correct transform method
                transformed = transformer.transform_entity(
                    entity_name,
                    record,
                    id_mapping=existing_maps
                )

                if not transformed:
                    skipped_count += 1
                    continue

                # RELIABILITY FIX: Pass oauth_manager for auto-refresh on token expiry
                # CRITICAL FIX: Use singular entity type for QBO API endpoint
                # Route TaxCode to TaxService endpoint (different payload/URL)
                if transformed.get('_use_tax_service'):
                    tax_code_name = transformed.pop('TaxCode', '')
                    tax_rate_details = transformed.pop('TaxRateDetails', [])
                    transformed.pop('_use_tax_service', None)
                    result = qbo_client.create_tax_service(
                        tax_code_name, tax_rate_details,
                        oauth_manager=oauth_manager)
                else:
                    result = qbo_client.create_entity(api_entity_type, transformed, oauth_manager=oauth_manager)

                if result and 'Id' in result:
                    # Track mapping for references
                    source_id = self._extract_source_id(record)
                    if source_id:
                        if entity_name not in existing_maps:
                            existing_maps[entity_name] = {}
                        existing_maps[entity_name][source_id] = result['Id']

                    success_count += 1
                else:
                    fail_count += 1

            except Exception as e:
                fail_count += 1
                logger.warning(f"Failed to migrate {entity_name} record: {str(e)}")
                continue

        return success_count, fail_count, skipped_count

    # ========================================================================
    # BATCH API MIGRATION (6-14x throughput improvement)
    # ========================================================================

    @staticmethod
    def _extract_source_id(record: Dict[str, Any]) -> Optional[str]:
        """
        Extract the QBD source ID from a record, handling both PascalCase
        (already-normalized data) and camelCase (raw C# extractor output).

        The C# extractor outputs camelCase field names (listId, txnId) but
        normalize_extractor_fields() converts them to PascalCase (ListID, TxnID).
        This helper is called BEFORE normalization, so it must check both.

        Returns:
            Source ID string, or None if no ID field found
        """
        source_id = (
            record.get('ListID') or record.get('listId') or
            record.get('TxnID') or record.get('txnId') or
            record.get('Id'))
        return str(source_id) if source_id else None

    # Entity types with parent-child hierarchies that require layered processing.
    # Parents must be created before children so QBO assigns IDs we can reference.
    PARENT_CHILD_ENTITY_TYPES = frozenset({
        'Accounts', 'Customers', 'Items', 'Classes', 'Departments',
    })

    # Reuse the same plural→singular mapping as _migrate_entity
    PLURAL_TO_SINGULAR = {
        # Configuration
        'CompanyCurrencies': 'CompanyCurrency', 'TaxAgencies': 'TaxAgency',
        'TaxRates': 'TaxRate', 'TaxCodes': 'TaxCode',
        'Terms': 'Term', 'PaymentMethods': 'PaymentMethod',
        'Classes': 'Class', 'Departments': 'Department',
        # Master lists
        'Accounts': 'Account', 'Customers': 'Customer', 'Vendors': 'Vendor',
        'Items': 'Item', 'Employees': 'Employee',
        # Transactions
        'Invoices': 'Invoice', 'Bills': 'Bill', 'Payments': 'Payment',
        'Estimates': 'Estimate', 'Deposits': 'Deposit', 'Transfers': 'Transfer',
        'JournalEntries': 'JournalEntry', 'CreditMemos': 'CreditMemo',
        'PurchaseOrders': 'PurchaseOrder', 'SalesReceipts': 'SalesReceipt',
        'BillPayments': 'BillPayment', 'VendorCredits': 'VendorCredit',
        'RefundReceipts': 'RefundReceipt', 'TimeActivities': 'TimeActivity',
        'InventoryAdjustments': 'InventoryAdjustment',
        'Purchases': 'Purchase', 'TaxPayments': 'TaxPayment',
        # Attachments
        'Attachables': 'Attachable',
    }

    def _migrate_entity_batch(
        self,
        qbo_client: 'PremiumQBOClient',
        transformer: 'QBDataTransformer',
        entity_name: str,
        source_data: List[Dict[str, Any]],
        existing_maps: Dict[str, Dict[str, str]],
        oauth_manager: Optional['OAuthManager'] = None,
        migration_id: Optional[str] = None
    ) -> Tuple[int, int, int]:
        """
        Batch-optimized migration for a single entity type.

        Uses QBO's Batch API (/batch endpoint) to send up to 30 entities per
        HTTP request, with parallel workers for concurrent batch submission.

        For entity types with parent-child hierarchies (Accounts, Customers,
        Items, Classes, Departments), processes entities in dependency layers:
        roots first, then children, then grandchildren, etc.

        TaxService entities (_use_tax_service flag) are routed individually
        through the TaxService endpoint since they can't use the batch API.

        Falls back to sequential single-entity creation if the batch contains
        only 1 entity (no benefit from batching).

        Args:
            qbo_client: Initialized QBO client
            transformer: Data transformer
            entity_name: Plural entity type name from entity_order
            source_data: List of source QBD records
            existing_maps: Maps of already-migrated entities (QBD ID → QBO ID)
            oauth_manager: OAuth manager for automatic token refresh
            migration_id: Migration run ID for SQLite dedup & crash recovery

        Returns:
            Tuple of (success_count, fail_count, skipped_count)
        """
        api_entity_type = self.PLURAL_TO_SINGULAR.get(entity_name, entity_name)

        # For very small datasets (≤1 entity), skip batch overhead
        if len(source_data) <= 1:
            return self._migrate_entity(
                qbo_client, transformer, entity_name, source_data,
                existing_maps, oauth_manager)

        success_count = 0
        fail_count = 0
        skipped_count = 0

        if entity_name in self.PARENT_CHILD_ENTITY_TYPES:
            # Process in dependency layers: roots → children → grandchildren
            layers = self._split_parent_child_layers(source_data)
            logger.info(
                f"Batch {entity_name}: {len(source_data)} records in "
                f"{len(layers)} dependency layers")

            for layer_idx, layer in enumerate(layers):
                s, f, sk = self._batch_create_layer(
                    qbo_client, transformer, entity_name, api_entity_type,
                    layer, existing_maps, oauth_manager, migration_id)
                success_count += s
                fail_count += f
                skipped_count += sk
                logger.debug(
                    f"  Layer {layer_idx}: {s} succeeded, {f} failed, "
                    f"{sk} skipped")
        else:
            # Flat entity type — batch all at once
            success_count, fail_count, skipped_count = self._batch_create_layer(
                qbo_client, transformer, entity_name, api_entity_type,
                source_data, existing_maps, oauth_manager, migration_id)

        return success_count, fail_count, skipped_count

    def _split_parent_child_layers(
        self,
        source_data: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        """
        Split records into dependency layers for parent-child entity types.

        Layer 0 contains root records (no parent reference).
        Layer 1 contains records whose parent is in layer 0.
        Layer N contains records whose parent is in layer N-1.

        If circular or missing parent references are detected, remaining
        records are placed in the current layer to avoid infinite loops.

        Args:
            source_data: List of source QBD records

        Returns:
            List of layers, each a list of records
        """
        remaining = list(source_data)
        created_ids = set()
        layers = []

        # Safety limit to prevent infinite loops from circular references
        max_depth = 50

        for _ in range(max_depth):
            if not remaining:
                break

            current_layer = []
            still_remaining = []

            for record in remaining:
                parent_id = self._get_parent_id(record)

                if parent_id is None or parent_id in created_ids:
                    current_layer.append(record)
                else:
                    still_remaining.append(record)

            if not current_layer:
                # All remaining records reference parents not yet created —
                # circular dependency or missing parents. Place them all in
                # this layer and let QBO validation catch the error.
                logger.warning(
                    f"Parent-child layering: {len(still_remaining)} records "
                    f"have unresolvable parent references. Processing anyway.")
                current_layer = still_remaining
                still_remaining = []

            # Track IDs from this layer for the next layer's parent lookups
            for record in current_layer:
                record_id = self._extract_source_id(record) or record.get('Name') or record.get('name')
                if record_id:
                    created_ids.add(str(record_id))

            layers.append(current_layer)
            remaining = still_remaining

        # Safety: if max_depth exhausted but records remain, add them as a
        # final layer rather than silently discarding them
        if remaining:
            logger.warning(
                f"Parent-child layering: max depth ({max_depth}) reached with "
                f"{len(remaining)} records remaining. Adding as final layer.")
            layers.append(remaining)

        return layers

    @staticmethod
    def _get_parent_id(record: Dict[str, Any]) -> Optional[str]:
        """
        Extract parent reference ID from a QBD record.

        Handles multiple field name formats from the C# extractor:
        - Object-style: ParentRef.ListID, ParentRef.value (dict)
        - String-style: ParentRef = "80000001-..." (direct string)
        - Flat-style PascalCase: ParentRef_ListID, ParentListID
        - Flat-style camelCase: parentRefListId (raw C# extractor output)

        Called BEFORE normalize_extractor_fields(), so must handle both
        camelCase (raw C#) and PascalCase (already-normalized) fields.

        Returns:
            Parent ID string, or None if no parent reference exists
        """
        # Object-style reference (dict)
        parent_ref = record.get('ParentRef') or record.get('parentRef')
        if isinstance(parent_ref, dict):
            pid = (
                parent_ref.get('ListID') or parent_ref.get('listId') or
                parent_ref.get('listID') or
                parent_ref.get('value') or parent_ref.get('Value') or
                parent_ref.get('FullName') or parent_ref.get('fullName'))
            if pid:
                return str(pid)

        # String-style reference (direct ID)
        if isinstance(parent_ref, str) and parent_ref:
            return parent_ref

        # Flat-style references — check both PascalCase (normalized)
        # and camelCase (raw C# extractor output like parentRefListId)
        flat_id = (
            record.get('ParentRef_ListID') or
            record.get('parentRef_ListID') or
            record.get('parentRefListId') or   # C# extractor camelCase
            record.get('ParentRef_listID') or
            record.get('ParentListID') or
            record.get('parentListID') or
            record.get('ParentRef_FullName') or
            record.get('parentRef_FullName') or
            record.get('parentRefFullName') or  # C# extractor camelCase
            record.get('ParentRefFullName'))
        if flat_id:
            return str(flat_id)

        return None

    def _batch_create_layer(
        self,
        qbo_client: 'PremiumQBOClient',
        transformer: 'QBDataTransformer',
        entity_name: str,
        api_entity_type: str,
        records: List[Dict[str, Any]],
        existing_maps: Dict[str, Dict[str, str]],
        oauth_manager: Optional['OAuthManager'] = None,
        migration_id: Optional[str] = None
    ) -> Tuple[int, int, int]:
        """
        Transform and batch-create a set of records at the same dependency level.

        Steps:
        1. Transform all records sequentially (transforms may update id_mapping)
        2. Separate TaxService entities from regular entities
        3. Process TaxService entities sequentially (can't use batch API)
        4. Batch regular entities into groups of BATCH_SIZE (30)
        5. Submit batches in parallel using ThreadPoolExecutor
        6. Collect results and update existing_maps with new ID mappings

        Args:
            qbo_client: QBO client
            transformer: Data transformer
            entity_name: Plural entity type name
            api_entity_type: Singular entity type for QBO API
            records: Source QBD records to process
            existing_maps: ID mapping dict (updated in-place)
            oauth_manager: OAuth manager for token refresh
            migration_id: Migration run ID for SQLite dedup & crash recovery

        Returns:
            Tuple of (success_count, fail_count, skipped_count)
        """
        success_count = 0
        fail_count = 0
        skipped_count = 0

        # ── Step 1: Transform all records ───────────────────────────────────
        # Must be sequential because transform_entity() updates id_mapping
        # state that subsequent transforms may depend on (e.g., sub-accounts
        # referencing parent accounts within the same type).
        transformed_pairs = []  # [(source_id, transformed_data), ...]
        tax_service_items = []  # [(source_id, tax_code_name, tax_rate_details), ...]

        for record in records:
            try:
                # Crash recovery: skip entities already created in a prior run
                # NOTE: Must check both PascalCase and camelCase because
                # normalize_extractor_fields() hasn't run yet at this point.
                source_id = self._extract_source_id(record)
                if source_id:
                    existing_qbo_id = qbo_client.was_entity_created(
                        api_entity_type, source_id)
                    if existing_qbo_id:
                        # Already migrated — restore mapping and skip
                        if entity_name not in existing_maps:
                            existing_maps[entity_name] = {}
                        existing_maps[entity_name][source_id] = existing_qbo_id
                        skipped_count += 1
                        continue

                transformed = transformer.transform_entity(
                    entity_name, record, id_mapping=existing_maps)

                if not transformed:
                    skipped_count += 1
                    continue

                if transformed.get('_use_tax_service'):
                    # TaxService entities use a special endpoint and can't be
                    # included in batch requests
                    tax_code_name = transformed.pop('TaxCode', '')
                    tax_rate_details = transformed.pop('TaxRateDetails', [])
                    transformed.pop('_use_tax_service', None)
                    tax_service_items.append(
                        (source_id, tax_code_name, tax_rate_details))
                else:
                    transformed_pairs.append((source_id, transformed))

            except Exception as e:
                fail_count += 1
                logger.warning(f"Transform failed for {entity_name}: {e}")

        # ── Step 2: Process TaxService entities sequentially ────────────────
        for source_id, tax_code_name, tax_rate_details in tax_service_items:
            try:
                result = qbo_client.create_tax_service(
                    tax_code_name, tax_rate_details,
                    oauth_manager=oauth_manager)

                if result:
                    # TaxService returns TaxCodeId (not standard 'Id')
                    tax_code_obj = result.get('TaxCode')
                    result_id = (
                        result.get('Id') or
                        result.get('TaxCodeId') or
                        (tax_code_obj.get('Id')
                         if isinstance(tax_code_obj, dict) else None))
                    if result_id:
                        if source_id:
                            if entity_name not in existing_maps:
                                existing_maps[entity_name] = {}
                            existing_maps[entity_name][source_id] = str(
                                result_id)
                        success_count += 1
                    else:
                        fail_count += 1
                else:
                    fail_count += 1

            except Exception as e:
                fail_count += 1
                logger.warning(
                    f"TaxService creation failed for '{tax_code_name}': {e}")

        # ── Step 3: Batch-create regular entities ───────────────────────────
        if not transformed_pairs:
            return success_count, fail_count, skipped_count

        # Import batch size from config
        try:
            from config import BATCH_SIZE
            batch_size = BATCH_SIZE
        except ImportError:
            batch_size = 30

        # Build batches of up to batch_size items
        batches = []
        for i in range(0, len(transformed_pairs), batch_size):
            batches.append(transformed_pairs[i:i + batch_size])

        # Determine worker count for parallel batch submission
        max_workers = min(qbo_client.max_workers, len(batches))

        if max_workers <= 1 or len(batches) <= 1:
            # Sequential processing — single batch or single worker
            for batch_idx, batch in enumerate(batches):
                mappings, batch_fails = self._send_batch_request(
                    qbo_client, api_entity_type, batch, oauth_manager,
                    migration_id, batch_idx)
                success_count += len(mappings)
                fail_count += batch_fails
                # Update existing_maps with new IDs for downstream dependencies
                for src_id, qbo_id in mappings:
                    if src_id:
                        if entity_name not in existing_maps:
                            existing_maps[entity_name] = {}
                        existing_maps[entity_name][src_id] = qbo_id
                        # FIX #13: Track created IDs for potential rollback
                        if hasattr(self, '_created_entity_ids'):
                            self._created_entity_ids[api_entity_type].append(qbo_id)
        else:
            # Parallel batch submission with ThreadPoolExecutor
            # Collect all results first, then update existing_maps (thread-safe)
            all_mappings = []

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                for batch_idx, batch in enumerate(batches):
                    future = executor.submit(
                        self._send_batch_request,
                        qbo_client, api_entity_type, batch, oauth_manager,
                        migration_id, batch_idx)
                    futures[future] = batch

                for future in as_completed(futures):
                    try:
                        mappings, batch_fails = future.result()
                        all_mappings.extend(mappings)
                        fail_count += batch_fails
                    except Exception as e:
                        failed_batch = futures[future]
                        fail_count += len(failed_batch)
                        logger.error(f"Batch worker failed: {e}")

            # Update existing_maps after all workers complete
            success_count += len(all_mappings)
            for src_id, qbo_id in all_mappings:
                if src_id:
                    if entity_name not in existing_maps:
                        existing_maps[entity_name] = {}
                    existing_maps[entity_name][src_id] = qbo_id
                    # FIX #13: Track created IDs for potential rollback
                    if hasattr(self, '_created_entity_ids'):
                        self._created_entity_ids[api_entity_type].append(qbo_id)

        return success_count, fail_count, skipped_count

    def _send_batch_request(
        self,
        qbo_client: 'PremiumQBOClient',
        api_entity_type: str,
        batch_items: List[Tuple[Optional[str], Dict[str, Any]]],
        oauth_manager: Optional['OAuthManager'] = None,
        migration_id: Optional[str] = None,
        batch_idx: int = 0
    ) -> Tuple[List[Tuple[Optional[str], str]], int]:
        """
        Send a single batch request to the QBO Batch API endpoint.

        Constructs a BatchItemRequest with up to 30 create operations,
        sends it via POST /batch, and parses the BatchItemResponse to
        correlate results back to source IDs via bId.

        Also records each successful creation in the SQLite state database
        for crash recovery and deduplication.

        Args:
            qbo_client: QBO client
            api_entity_type: Singular entity type (e.g., 'Account', 'Invoice')
            batch_items: List of (source_id, transformed_entity_data) tuples
            oauth_manager: OAuth manager for token refresh
            migration_id: Migration run ID for SQLite tracking
            batch_idx: Index of this batch within the layer (for idempotency)

        Returns:
            Tuple of:
            - success_mappings: List of (source_id, qbo_id) for successful items
            - fail_count: Number of failed items in this batch
        """
        # Enforce the 40 batch requests/minute rate limit
        qbo_client._enforce_batch_rate_limit()

        success_mappings = []
        fail_count = 0

        # Build the BatchItemRequest payload
        batch_data = {"BatchItemRequest": []}
        bid_to_source = {}  # bId → source_id for response correlation

        for j, (source_id, entity_data) in enumerate(batch_items):
            bid = f"bid_{j}"
            bid_to_source[bid] = source_id
            batch_data["BatchItemRequest"].append({
                "bId": bid,
                "operation": "create",
                api_entity_type: entity_data,
            })

        if not batch_data["BatchItemRequest"]:
            return success_mappings, fail_count

        # Idempotency key for crash recovery (matches _process_single_batch format)
        idempotency_key = (
            f"batch_{api_entity_type}_{batch_idx}_{migration_id}"
            if migration_id else None)

        try:
            response = qbo_client._make_request(
                "POST", "batch", batch_data,
                oauth_manager=oauth_manager,
                idempotency_key=idempotency_key)

            batch_responses = response.get("BatchItemResponse", [])

            if not batch_responses:
                # QBO returned empty response — treat all items as failed
                logger.error(
                    f"Empty BatchItemResponse for {api_entity_type} batch "
                    f"({len(batch_items)} items)")
                return success_mappings, len(batch_items)

            for batch_item in batch_responses:
                bid = batch_item.get("bId", "")
                source_id = bid_to_source.get(bid)

                if batch_item.get(api_entity_type):
                    # Success — extract created entity
                    created = batch_item[api_entity_type]
                    qbo_id = created.get('Id')
                    sync_token = created.get('SyncToken', '0')

                    if qbo_id:
                        success_mappings.append((source_id, qbo_id))
                        # Record in SQLite for crash recovery / dedup
                        qbo_client.record_created(
                            api_entity_type,
                            source_id or f"batch_{bid}",
                            qbo_id,
                            migration_id,
                            sync_token)
                    else:
                        fail_count += 1

                elif batch_item.get("Fault"):
                    # Individual item failure within the batch
                    fail_count += 1
                    fault = batch_item["Fault"]
                    errors = fault.get("Error", [{}])
                    error_msg = (errors[0].get("Message", "Unknown error")
                                 if errors else "Unknown error")
                    error_detail = (errors[0].get("Detail", "")
                                    if errors else "")
                    logger.warning(
                        f"Batch item {bid} ({api_entity_type}) failed: "
                        f"{error_msg}"
                        + (f" - {error_detail}" if error_detail else ""))
                else:
                    # Unexpected response format
                    fail_count += 1
                    logger.warning(
                        f"Batch item {bid} ({api_entity_type}): "
                        f"unexpected response format")

            # If QBO returned fewer responses than items sent, count
            # the missing items as failures so counts stay consistent
            accounted = len(success_mappings) + fail_count
            unaccounted = len(batch_items) - accounted
            if unaccounted > 0:
                fail_count += unaccounted
                logger.warning(
                    f"Batch response for {api_entity_type} missing "
                    f"{unaccounted} of {len(batch_items)} items")

        except Exception as e:
            # Entire batch request failed — fall back to sequential creates
            logger.error(
                f"Batch request failed for {api_entity_type} "
                f"({len(batch_items)} items): {e} — retrying individually")
            for source_id, entity_data in batch_items:
                try:
                    result = qbo_client.create_entity(
                        api_entity_type, entity_data,
                        oauth_manager=oauth_manager)
                    if result and 'Id' in result:
                        qbo_id = result['Id']
                        success_mappings.append((source_id, qbo_id))
                        qbo_client.record_created(
                            api_entity_type,
                            source_id or f"fallback_{len(success_mappings)}",
                            qbo_id, migration_id,
                            result.get('SyncToken', '0'))
                    else:
                        fail_count += 1
                except Exception as individual_err:
                    fail_count += 1
                    logger.warning(
                        f"Individual create also failed for {api_entity_type} "
                        f"({source_id}): {individual_err}")

        return success_mappings, fail_count

    def run_migration_from_s3(
        self,
        s3_uri: str,
        aws_region: str = 'us-east-1'
    ) -> Dict[str, Any]:
        """
        Run migration from S3-stored data.
        
        Args:
            s3_uri: S3 URI (s3://bucket/key)
            aws_region: AWS region
            
        Returns:
            Migration result dict
        """
        import boto3

        # Parse S3 URI (case-insensitive prefix check)
        if not s3_uri.lower().startswith('s3://'):
            raise ValueError(f"Invalid S3 URI format (must start with s3://): {s3_uri}")
        parts = s3_uri[5:].split('/', 1)  # Skip 's3://' regardless of case
        bucket = parts[0]
        if not bucket:
            raise ValueError(f"Invalid S3 URI - empty bucket name: {s3_uri}")
        if len(parts) < 2 or not parts[1]:
            raise ValueError(f"Invalid S3 URI - missing object key: {s3_uri}")
        key = parts[1]

        s3 = boto3.client('s3', region_name=aws_region)

        # Download encrypted data
        self._report_progress(2, "Downloading data from S3")

        response = s3.get_object(Bucket=bucket, Key=key)
        encrypted_data = response['Body'].read()

        # Get company name from the data file's S3 metadata
        data_response = s3.head_object(Bucket=bucket, Key=key)
        company_name = data_response.get('Metadata', {}).get('company-name', 'Unknown')

        # Get encryption metadata — use endswith so keys like
        # 'migrations/123/encrypted_data.bin' work but stray substrings
        # like 'encrypted_data.bin.bak' don't
        if not key.endswith('encrypted_data.bin'):
            raise ValueError(f"S3 key does not follow expected pattern (must end with 'encrypted_data.bin'): {key}")
        metadata_key = key[:-len('encrypted_data.bin')] + 'encryption_metadata.json'
        response = s3.get_object(Bucket=bucket, Key=metadata_key)
        encryption_metadata = json.loads(response['Body'].read().decode('utf-8'))

        return self.run_migration(encrypted_data, encryption_metadata, company_name)

    def rollback_migration(
        self,
        qbo_client: Optional['PremiumQBOClient'] = None,
        oauth_manager: Optional['OAuthManager'] = None
    ) -> Dict[str, Any]:
        """
        FIX #13: Rollback a failed migration by deleting created entities.

        This method should be called when a migration fails partway through
        to clean up orphaned records in the QBO company.

        Note: QBO does not support true deletion for all entity types.
        Some entities (like Accounts) can only be made inactive.

        Args:
            qbo_client: QBO client (uses cached client if not provided)
            oauth_manager: OAuth manager for token refresh

        Returns:
            Dict with rollback results:
            {
                'success': bool,
                'deleted': {'Account': 5, 'Customer': 10, ...},
                'failed': {'Invoice': 2, ...},
                'errors': [...]
            }
        """
        if not hasattr(self, '_created_entity_ids') or not self._created_entity_ids:
            logger.info("No entities to rollback - _created_entity_ids is empty")
            return {
                'success': True,
                'deleted': {},
                'failed': {},
                'errors': [],
                'message': 'No entities to rollback'
            }

        if qbo_client is None:
            if self._qbo_client is None:
                logger.error("Cannot rollback - no QBO client available")
                return {
                    'success': False,
                    'deleted': {},
                    'failed': {},
                    'errors': ['No QBO client available for rollback']
                }
            qbo_client = self._qbo_client

        if oauth_manager is None:
            oauth_manager = self._oauth_manager

        logger.warning("Starting migration rollback...")
        deleted_counts: Dict[str, int] = {}
        failed_counts: Dict[str, int] = {}
        errors: List[str] = []

        # Delete in reverse dependency order (transactions before master lists)
        # This prevents foreign key violations
        rollback_order = [
            # Transactions first (they reference master data)
            'Attachable', 'TaxPayment', 'InventoryAdjustment', 'TimeActivity',
            'RefundReceipt', 'VendorCredit', 'CreditMemo', 'JournalEntry',
            'Transfer', 'Deposit', 'BillPayment', 'Payment', 'Bill',
            'Purchase', 'PurchaseOrder', 'SalesReceipt', 'Invoice', 'Estimate',
            # Master lists next
            'Item', 'Employee', 'Vendor', 'Customer',
            # Configuration last (accounts often can't be deleted, only deactivated)
            'Department', 'Class', 'PaymentMethod', 'Term',
            'TaxCode', 'TaxRate', 'TaxAgency', 'CompanyCurrency', 'Account'
        ]

        for entity_type in rollback_order:
            if entity_type not in self._created_entity_ids:
                continue

            entity_ids = self._created_entity_ids[entity_type]
            if not entity_ids:
                continue

            deleted_counts[entity_type] = 0
            failed_counts[entity_type] = 0

            logger.info(f"Rolling back {len(entity_ids)} {entity_type} entities...")

            for qbo_id in reversed(entity_ids):  # Delete in reverse creation order
                try:
                    # Try to delete the entity
                    success = qbo_client.delete_entity(
                        entity_type, qbo_id, oauth_manager=oauth_manager)

                    if success:
                        deleted_counts[entity_type] += 1
                    else:
                        # Some entities can't be deleted, try to deactivate
                        try:
                            qbo_client.update_entity(
                                entity_type, qbo_id,
                                {'Active': False},
                                oauth_manager=oauth_manager)
                            deleted_counts[entity_type] += 1
                            logger.info(f"Deactivated {entity_type} {qbo_id} (delete not supported)")
                        except Exception:
                            failed_counts[entity_type] += 1

                except Exception as e:
                    failed_counts[entity_type] += 1
                    error_msg = f"Failed to delete {entity_type} {qbo_id}: {str(e)}"
                    errors.append(error_msg)
                    logger.warning(error_msg)

        # Summary
        total_deleted = sum(deleted_counts.values())
        total_failed = sum(failed_counts.values())

        logger.info(f"Rollback complete: {total_deleted} deleted, {total_failed} failed")

        return {
            'success': total_failed == 0,
            'deleted': deleted_counts,
            'failed': failed_counts,
            'errors': errors,
            'summary': f"Deleted {total_deleted} entities, {total_failed} failures"
        }


# CLI entry point for standalone execution
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Run QB Migration')
    parser.add_argument('--migration-id', required=True)
    parser.add_argument('--encrypted-data', required=True)
    parser.add_argument('--metadata', required=True)
    parser.add_argument('--credentials', required=True)
    parser.add_argument('--server-url', required=True)
    # SECURITY FIX: Read webhook secret from environment variable instead of CLI arg.
    # CLI arguments are visible in process listings (ps aux, /proc/*/cmdline).
    parser.add_argument('--webhook-secret', required=False,
                        help='DEPRECATED: Use QBM_WEBHOOK_SECRET env var instead')
    
    args = parser.parse_args()

    # SECURITY FIX: Validate file paths before opening to prevent path traversal
    # when CLI arguments come from automated systems or web interfaces
    def _validate_cli_path(file_path: str, description: str) -> str:
        """Validate CLI file path is safe to read."""
        real_path = os.path.realpath(file_path)
        # Reject paths containing traversal sequences
        if '..' in os.path.normpath(file_path):
            raise ValueError(f"Path traversal detected in {description}: {file_path}")
        # Ensure file exists and is a regular file (not a symlink to sensitive files)
        if not os.path.isfile(real_path):
            raise ValueError(f"{description} file not found: {file_path}")
        # Reject system files
        sensitive_prefixes = ['/etc/', '/proc/', '/sys/', '/dev/']
        if any(real_path.startswith(p) for p in sensitive_prefixes):
            raise ValueError(f"{description} path points to system directory: {real_path}")
        return real_path

    credentials_path = _validate_cli_path(args.credentials, 'credentials')
    metadata_path = _validate_cli_path(args.metadata, 'metadata')
    encrypted_data_path = _validate_cli_path(args.encrypted_data, 'encrypted-data')

    # Load credentials
    with open(credentials_path, 'r') as f:
        creds = json.load(f)

    # Load metadata
    with open(metadata_path, 'r') as f:
        metadata = json.load(f)

    # Load encrypted data
    with open(encrypted_data_path, 'rb') as f:
        encrypted_data = f.read()
    
    # Create orchestrator
    orchestrator = MigrationOrchestrator(
        qbo_client_id=creds['client_id'],
        qbo_client_secret=creds['client_secret'],
        qbo_refresh_token=creds['refresh_token'],
        realm_id=creds.get('realm_id', ''),
        qbo_environment=creds.get('environment', 'sandbox')
    )
    
    # Run migration
    result = orchestrator.run_migration(encrypted_data, metadata)
    
    # Report result to server via webhook
    import requests
    import hmac
    import hashlib
    from datetime import datetime

    # SECURITY FIX: Read webhook secret from env var (preferred) or CLI arg (deprecated)
    webhook_secret = os.environ.get('QBM_WEBHOOK_SECRET') or args.webhook_secret
    if not webhook_secret:
        logger.error("No webhook secret provided. Set QBM_WEBHOOK_SECRET env var.")
        sys.exit(2)

    # SECURITY FIX: Align signature algorithm with server expectations
    # Server expects: HMAC-SHA256(migration_id:timestamp)
    webhook_timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    message = f"{args.migration_id}:{webhook_timestamp}"

    signature = hmac.new(
        webhook_secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Generate unique webhook ID for idempotency
    webhook_id = str(uuid.uuid4())

    endpoint = 'migration-completed' if result['success'] else 'migration-failed'

    # RELIABILITY FIX: Report result to server via webhook with exponential backoff
    max_retries = 5
    base_delay = 2  # seconds

    webhook_url = f"{args.server_url}/api/webhooks/{endpoint}"
    webhook_headers = {
        'X-Migration-Id': args.migration_id,
        'X-Webhook-Signature': signature,
        'X-Webhook-Timestamp': webhook_timestamp,
        'X-Webhook-Id': webhook_id
    }

    for attempt in range(max_retries):
        try:
            response = requests.post(
                webhook_url,
                json=result,
                headers=webhook_headers,
                timeout=30
            )
            response.raise_for_status()
            logger.info(f"Webhook delivered successfully on attempt {attempt + 1}")
            break  # Success - exit retry loop

        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                # Calculate exponential backoff: 2s, 4s, 8s, 16s
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Webhook attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                logger.error(f"Webhook failed after {max_retries} attempts: {e}")
                # Don't raise - allow migration to continue even if webhook fails
    
    sys.exit(0 if result['success'] else 1)
