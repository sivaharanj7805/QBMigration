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
        
        logging.basicConfig(level=log_level)
        
        # Will be initialized lazily
        self._encryption_manager = None
        self._oauth_manager = None
        self._qbo_client = None
        self._transformer = None
        self._verifier = None
    
    def _report_progress(self, percent: int, message: str) -> None:
        """Report progress to callback"""
        logger.info(f"[{percent}%] {message}")
        self.progress_callback(percent, message)

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
        company_name: str = "Unknown"
    ) -> Dict[str, Any]:
        """
        Run the complete migration process.
        
        Args:
            encrypted_data: AES-256-GCM encrypted data from QBDesktopReader
            encryption_metadata: Dict with iv, tag, algorithm, etc.
            company_name: Company name for logging
            
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
        """
        start_time = datetime.now(timezone.utc)
        migration_id = f"mig_{uuid.uuid4().hex[:16]}"
        
        logger.info(f"Starting migration {migration_id} for {company_name}")
        
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
                # Phase 1: Configuration (20-25%)
                ('CompanyCurrencies', 20, 21),
                ('TaxAgencies', 21, 22),
                ('TaxRates', 22, 22),
                ('TaxCodes', 22, 23),
                ('Terms', 23, 23),
                ('PaymentMethods', 23, 24),
                ('Classes', 24, 25),
                ('Departments', 25, 25),
                # Phase 2: Chart of Accounts (25-35%)
                ('Accounts', 25, 35),
                # Phase 3: Master Lists (35-50%)
                ('Customers', 35, 42),
                ('Vendors', 42, 47),
                ('Employees', 47, 49),
                ('Items', 49, 55),
                # Phase 4: Opening Balances (55-60%)
                ('JournalEntries', 55, 58),
                ('InventoryAdjustments', 58, 60),
                # Phase 5: Transactions (60-82%)
                ('Estimates', 60, 62),
                ('Invoices', 62, 67),
                ('SalesReceipts', 67, 69),
                ('PurchaseOrders', 69, 70),
                ('Purchases', 70, 72),
                ('Bills', 72, 75),
                ('Payments', 75, 77),
                ('BillPayments', 77, 78),
                ('Deposits', 78, 79),
                ('Transfers', 79, 80),
                ('CreditMemos', 80, 81),
                ('VendorCredits', 81, 81),
                ('RefundReceipts', 81, 82),
                ('TimeActivities', 82, 83),
                ('TaxPayments', 83, 84),
                # Phase 6: Attachments (84-85%)
                ('Attachables', 84, 85),
            ]

            for entity_name, start_pct, end_pct in entity_order:
                if entity_name in data and data[entity_name]:
                    self._report_progress(start_pct, f"Migrating {entity_name}")

                    # Use batch API for performance (30 entities/request, parallel workers)
                    success, failed, skipped = self._migrate_entity_batch(
                        qbo_client,
                        transformer,
                        entity_name,
                        data[entity_name],
                        entity_id_mappings,
                        oauth_mgr,
                        migration_id
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

            result = {
                'success': True,
                'migration_id': migration_id,
                'company_name': company_name,
                'entities_migrated': entity_counts,  # Use counts, not mappings
                'verification': verification_result,
                'duration_seconds': duration,
                'completed_at': datetime.now(timezone.utc).isoformat()
            }
            
            logger.info(f"Migration {migration_id} completed in {duration:.1f}s")
            return result
            
        except Exception as e:
            logger.exception(f"Migration {migration_id} failed: {str(e)}")
            
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            return {
                'success': False,
                'migration_id': migration_id,
                'error': str(e),
                'duration_seconds': duration,
                'failed_at': datetime.now(timezone.utc).isoformat()
            }
    
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

        # CRITICAL FIX: QBO API endpoints are singular (e.g., 'account', not 'accounts')
        # entity_name comes from entity_order as plural ('Accounts', 'Customers', etc.)
        # but create_entity() uses entity_type.lower() as the API endpoint
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
        api_entity_type = PLURAL_TO_SINGULAR.get(entity_name, entity_name)

        for record in source_data:
            try:
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
                    source_id = record.get('ListID') or record.get('TxnID') or record.get('Id')
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

    def _migrate_entity_batch(
        self,
        qbo_client: 'PremiumQBOClient',
        transformer: 'QBDataTransformer',
        entity_name: str,
        source_data: List[Dict[str, Any]],
        existing_maps: Dict[str, Dict[str, str]],
        oauth_manager: Optional['OAuthManager'] = None,
        migration_id: str = None
    ) -> Tuple[int, int, int]:
        """
        Migrate an entity type using batch API (30 entities per request, parallel workers).

        Flow:
        1. Transform all records, collecting (source_id, transformed) pairs
        2. Separate TaxService entities from regular batch-eligible entities
        3. For parent-child types (Account, Customer, Class, Department),
           process in hierarchy levels: roots first, then children
        4. Batch-create regular entities via batch_create_parallel
        5. Handle TaxService entities individually (different endpoint)
        6. Capture QBO IDs from responses and update existing_maps

        Args:
            qbo_client: Initialized QBO client
            transformer: Data transformer
            entity_name: Plural entity name (e.g., 'Customers', 'Invoices')
            source_data: List of raw QB Desktop records
            existing_maps: ID mapping dict, updated in-place with new mappings
            oauth_manager: OAuth manager for automatic token refresh
            migration_id: Migration ID for tracking

        Returns:
            Tuple of (success_count, fail_count, skipped_count)
        """
        success_count = 0
        fail_count = 0
        skipped_count = 0

        # Plural → Singular mapping for QBO API endpoints
        PLURAL_TO_SINGULAR = {
            'CompanyCurrencies': 'CompanyCurrency', 'TaxAgencies': 'TaxAgency',
            'TaxRates': 'TaxRate', 'TaxCodes': 'TaxCode',
            'Terms': 'Term', 'PaymentMethods': 'PaymentMethod',
            'Classes': 'Class', 'Departments': 'Department',
            'Accounts': 'Account', 'Customers': 'Customer', 'Vendors': 'Vendor',
            'Items': 'Item', 'Employees': 'Employee',
            'Invoices': 'Invoice', 'Bills': 'Bill', 'Payments': 'Payment',
            'Estimates': 'Estimate', 'Deposits': 'Deposit', 'Transfers': 'Transfer',
            'JournalEntries': 'JournalEntry', 'CreditMemos': 'CreditMemo',
            'PurchaseOrders': 'PurchaseOrder', 'SalesReceipts': 'SalesReceipt',
            'BillPayments': 'BillPayment', 'VendorCredits': 'VendorCredit',
            'RefundReceipts': 'RefundReceipt', 'TimeActivities': 'TimeActivity',
            'InventoryAdjustments': 'InventoryAdjustment',
            'Purchases': 'Purchase', 'TaxPayments': 'TaxPayment',
            'Attachables': 'Attachable',
        }
        api_entity_type = PLURAL_TO_SINGULAR.get(entity_name, entity_name)

        # Entity types with parent-child hierarchies (ParentRef within same type)
        PARENT_CHILD_TYPES = {'Accounts', 'Customers', 'Classes', 'Departments'}

        # ------------------------------------------------------------------
        # Phase 1: Transform all records, collecting (source_id, raw, transformed)
        # ------------------------------------------------------------------
        all_items = []  # List of (source_id, raw_record, transformed_dict)
        tax_service_items = []  # List of (source_id, transformed_dict)

        for record in source_data:
            try:
                transformed = transformer.transform_entity(
                    entity_name, record, id_mapping=existing_maps
                )

                if not transformed:
                    skipped_count += 1
                    continue

                source_id = (
                    record.get('ListID') or record.get('TxnID')
                    or record.get('Id') or record.get('Name')
                )

                if transformed.get('_use_tax_service'):
                    tax_service_items.append((source_id, transformed))
                else:
                    all_items.append((source_id, record, transformed))

            except Exception as e:
                skipped_count += 1
                logger.warning(f"Transform failed for {entity_name} record: {e}")

        # ------------------------------------------------------------------
        # Phase 2: Batch-create regular entities
        # ------------------------------------------------------------------
        if all_items:
            if entity_name in PARENT_CHILD_TYPES:
                # Process in hierarchy levels to preserve parent-child relationships
                s, f = self._batch_create_hierarchical(
                    qbo_client, api_entity_type, entity_name,
                    all_items, existing_maps, oauth_manager, migration_id,
                    transformer=transformer
                )
            else:
                # Flat batch — all entities are independent
                s, f = self._batch_create_flat(
                    qbo_client, api_entity_type, entity_name,
                    all_items, existing_maps, oauth_manager, migration_id
                )
            success_count += s
            fail_count += f

        # ------------------------------------------------------------------
        # Phase 3: Handle TaxService entities individually (special endpoint)
        # ------------------------------------------------------------------
        for source_id, transformed in tax_service_items:
            try:
                tax_code_name = transformed.pop('TaxCode', '')
                tax_rate_details = transformed.pop('TaxRateDetails', [])
                transformed.pop('_use_tax_service', None)

                result = qbo_client.create_tax_service(
                    tax_code_name, tax_rate_details,
                    oauth_manager=oauth_manager
                )

                # TaxService returns TaxCodeId in response
                tc_id = None
                if isinstance(result, dict):
                    tc_id = result.get('TaxCodeId') or result.get('Id')
                    # Some QBO versions nest under TaxCode key
                    if not tc_id and 'TaxCode' in result:
                        tc_id = result['TaxCode'].get('Id')

                if tc_id and source_id:
                    if entity_name not in existing_maps:
                        existing_maps[entity_name] = {}
                    existing_maps[entity_name][source_id] = str(tc_id)

                success_count += 1

            except Exception as e:
                fail_count += 1
                logger.warning(f"TaxService create failed for {entity_name}: {e}")

        return success_count, fail_count, skipped_count

    def _batch_create_flat(
        self,
        qbo_client: 'PremiumQBOClient',
        api_entity_type: str,
        entity_name: str,
        items: List[Tuple[str, Dict, Dict]],
        existing_maps: Dict[str, Dict[str, str]],
        oauth_manager: Optional['OAuthManager'],
        migration_id: str
    ) -> Tuple[int, int]:
        """
        Batch-create entities that have no internal parent-child relationships.

        Args:
            items: List of (source_id, raw_record, transformed_entity) tuples

        Returns:
            (success_count, fail_count)
        """
        source_ids = [item[0] for item in items]
        entities = [item[2] for item in items]

        result = qbo_client.batch_create_parallel(
            entities=entities,
            entity_type=api_entity_type,
            oauth_manager=oauth_manager,
            migration_id=migration_id or '',
            source_ids=source_ids
        )

        # Update in-memory ID mappings for subsequent entity types
        id_mappings = result.get('id_mappings', {})
        if id_mappings:
            if entity_name not in existing_maps:
                existing_maps[entity_name] = {}
            existing_maps[entity_name].update(id_mappings)

        return result.get('succeeded_count', 0), len(result.get('failed', []))

    def _batch_create_hierarchical(
        self,
        qbo_client: 'PremiumQBOClient',
        api_entity_type: str,
        entity_name: str,
        items: List[Tuple[str, Dict, Dict]],
        existing_maps: Dict[str, Dict[str, str]],
        oauth_manager: Optional['OAuthManager'],
        migration_id: str,
        transformer: Optional['QBDataTransformer'] = None
    ) -> Tuple[int, int]:
        """
        Batch-create entities with parent-child hierarchies in levels.

        Entities are sorted into levels by their ParentRef depth:
          Level 0: root entities (no ParentRef)
          Level 1: children of level-0 entities
          Level 2: children of level-1 entities
          ...

        Each level is batch-created, IDs captured, and then the next level's
        transforms are updated with parent IDs before creating.

        This preserves parent-child relationships while still using batch API.
        """
        total_success = 0
        total_fail = 0

        # Build source_id → (raw_record, transformed) lookup
        items_by_source_id = {}
        for source_id, raw_record, transformed in items:
            items_by_source_id[source_id or id(raw_record)] = (source_id, raw_record, transformed)

        # Separate into roots (no ParentRef) and children
        roots = []
        children_by_parent = {}  # parent_source_id → list of items

        for source_id, raw_record, transformed in items:
            parent_ref = raw_record.get('ParentRef')
            if not parent_ref:
                roots.append((source_id, raw_record, transformed))
            else:
                parent_id = str(parent_ref)
                if parent_id not in children_by_parent:
                    children_by_parent[parent_id] = []
                children_by_parent[parent_id].append((source_id, raw_record, transformed))

        # Process level by level using BFS
        current_level = roots

        # Also include "orphans" — children whose parents aren't in this batch
        # (parent was in a previous migration or doesn't exist)
        known_ids = {item[0] for item in items if item[0]}
        for parent_id, children in list(children_by_parent.items()):
            if parent_id not in known_ids:
                # Parent not in this batch — treat children as roots
                current_level.extend(children)
                del children_by_parent[parent_id]

        level_num = 0
        while current_level:
            logger.info(
                f"  {entity_name} hierarchy level {level_num}: "
                f"{len(current_level)} entities"
            )

            # For levels > 0, re-transform to pick up parent QBO IDs
            if level_num > 0 and transformer:
                retransformed = []
                for source_id, raw_record, old_transformed in current_level:
                    try:
                        transformed = transformer.transform_entity(
                            entity_name, raw_record, id_mapping=existing_maps
                        )
                        if transformed:
                            retransformed.append((source_id, raw_record, transformed))
                        else:
                            total_fail += 1
                    except Exception as e:
                        total_fail += 1
                        logger.warning(f"Re-transform failed for {entity_name}: {e}")
                current_level = retransformed

            if current_level:
                s, f = self._batch_create_flat(
                    qbo_client, api_entity_type, entity_name,
                    current_level, existing_maps, oauth_manager, migration_id
                )
                total_success += s
                total_fail += f

            # Collect next level: children of entities we just created
            next_level = []
            for source_id, _, _ in current_level:
                if source_id and source_id in children_by_parent:
                    next_level.extend(children_by_parent[source_id])

            current_level = next_level
            level_num += 1

        return total_success, total_fail

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

        # Get encryption metadata
        if 'encrypted_data.bin' not in key:
            raise ValueError(f"S3 key does not follow expected pattern (expected 'encrypted_data.bin' in key): {key}")
        metadata_key = key.replace('encrypted_data.bin', 'encryption_metadata.json')
        response = s3.get_object(Bucket=bucket, Key=metadata_key)
        encryption_metadata = json.loads(response['Body'].read().decode('utf-8'))

        return self.run_migration(encrypted_data, encryption_metadata, company_name)


# CLI entry point for standalone execution
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Run QB Migration')
    parser.add_argument('--migration-id', required=True)
    parser.add_argument('--encrypted-data', required=True)
    parser.add_argument('--metadata', required=True)
    parser.add_argument('--credentials', required=True)
    parser.add_argument('--server-url', required=True)
    parser.add_argument('--webhook-secret', required=True)
    
    args = parser.parse_args()
    
    # Load credentials
    with open(args.credentials, 'r') as f:
        creds = json.load(f)
    
    # Load metadata
    with open(args.metadata, 'r') as f:
        metadata = json.load(f)
    
    # Load encrypted data
    with open(args.encrypted_data, 'rb') as f:
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

    # SECURITY FIX: Align signature algorithm with server expectations
    # Server expects: HMAC-SHA256(migration_id:timestamp)
    webhook_timestamp = datetime.now(timezone.utc).isoformat() + 'Z'
    message = f"{args.migration_id}:{webhook_timestamp}"

    signature = hmac.new(
        args.webhook_secret.encode('utf-8'),
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
