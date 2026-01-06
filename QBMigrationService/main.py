import json
import os
from datetime import datetime
from qbo_client import QBOClient
from data_transformer import DataTransformer
from verifier import MigrationVerifier
from encryption import EncryptionManager
from oauth_manager import OAuthManager
from audit_logger import AuditLogger
from data_retention import DataRetentionManager
from security import SecurityManager
from config import *

def secure_migration(encrypted_data_string, migration_id):
    """
    Enhanced secure migration with:
    - Pre-migration scan
    - Production guard
    - Permission verification
    - Migration memos
    - Persistent ID mapping
    - Comprehensive error handling
    """
    
    print("=" * 80)
    print("  QuickBooks SECURE Migration")
    print("=" * 80)
    
    # Validate production access
    try:
        validate_production_access()
    except Exception as e:
        print(f"\n{str(e)}")
        return {
            "success": False,
            "error": "Production guard blocked migration"
        }
    
    # Initialize security components
    logger = AuditLogger(encrypt_logs=ENCRYPT_LOGS)
    retention_mgr = DataRetentionManager(retention_hours=DATA_RETENTION_HOURS)
    
    start_time = datetime.now()
    
    try:
        # STEP 1: Decrypt data
        print(f"\n[1/9] Decrypting data (Migration ID: {migration_id})...")
        logger.log_encryption(migration_id, "decrypt_start")
        
        decrypted_json = EncryptionManager.decrypt_string(encrypted_data_string)
        data = json.loads(decrypted_json)
        
        # CRITICAL: Clear decrypted buffer from memory
        EncryptionManager.secure_zero_memory(decrypted_json.encode())
        
        logger.log_encryption(
            migration_id,
            "decrypt_complete",
            file_size=len(decrypted_json)
        )
        
        company_name = data.get("CompanyName", "Unknown")
        data_counts = {
            "customers": len(data.get("Customers", [])),
            "vendors": len(data.get("Vendors", [])),
            "accounts": len(data.get("Accounts", [])),
            "items": len(data.get("Items", [])),
            "invoices": len(data.get("Invoices", []))
        }
        
        logger.log_migration_start(migration_id, company_name, data_counts)
        
        print(f"✓ Data decrypted")
        print(f"  Company: {company_name}")
        print(f"  Customers: {data_counts['customers']}")
        print(f"  Vendors: {data_counts['vendors']}")
        print(f"  Accounts: {data_counts['accounts']}")
        print(f"  Items: {data_counts['items']}")
        print(f"  Invoices: {data_counts['invoices']}")
        
        # STEP 2: Pre-migration scan
        print(f"\n[2/9] Running pre-migration scan...")
        scan_result = SecurityManager.pre_migration_scan(data)
        
        if not scan_result['should_proceed']:
            logger.log_security_event("MIGRATION_BLOCKED", {
                "migration_id": migration_id,
                "reason": "Pre-migration scan failed",
                "errors": scan_result['errors']
            })
            
            return {
                "success": False,
                "migration_id": migration_id,
                "error": "Pre-migration scan failed",
                "scan_errors": scan_result['errors'],
                "scan_warnings": scan_result['warnings']
            }
        
        # STEP 3: Refresh OAuth token and verify permissions
        print("\n[3/9] Refreshing OAuth token...")
        oauth_mgr = OAuthManager(CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN)
        
        try:
            access_token = oauth_mgr.get_access_token()
            logger.log_oauth_refresh(success=True)
            print("✓ OAuth token refreshed")
            
            # Verify permissions
            has_required_scopes = oauth_mgr.verify_scopes()
            if not has_required_scopes:
                raise Exception("OAuth token does not have required permissions")
            
        except Exception as e:
            logger.log_oauth_refresh(success=False, error=str(e))
            raise
        
        # Get company info
        company_info = oauth_mgr.get_company_info()
        
        # STEP 4: Initialize QBO client
        print("\n[4/9] Initializing QuickBooks Online client...")
        client = QBOClient(access_token=access_token)
        print("✓ Client initialized")
        
        # STEP 5: Check QBO plan recommendation
        print("\n[5/9] Checking QBO plan requirements...")
        class_count = len(data.get("Classes", []))
        item_count = len(data.get("Items", []))
        user_count = 1  # Would come from QBD data
        
        recommended_plan = get_qbo_plan_recommendation(
            class_count, 
            item_count, 
            user_count
        )
        
        print(f"  Recommended QBO plan: {recommended_plan}")
        if class_count > 0:
            print(f"  (File uses {class_count} classes, requires Plus or Advanced)")
        
        # STEP 6: Migrate data
        print("\n[6/9] Migrating data...")
        transformer = DataTransformer()
        
        # Create persistent ID mapping file
        mapping_file = os.path.join(OUTPUT_DIR, f"id_mappings_{migration_id}.json")
        
        # Migrate in correct order
        customer_map = migrate_customers(client, transformer, data.get("Customers", []), oauth_mgr)
        logger.log_data_operation("CREATE", "Customer", len(customer_map), migration_id)
        save_mapping(mapping_file, "customers", customer_map)
        
        vendor_map = migrate_vendors(client, transformer, data.get("Vendors", []), oauth_mgr)
        logger.log_data_operation("CREATE", "Vendor", len(vendor_map), migration_id)
        save_mapping(mapping_file, "vendors", vendor_map)
        
        account_map = migrate_accounts(client, transformer, data.get("Accounts", []), oauth_mgr)
        logger.log_data_operation("CREATE", "Account", len(account_map), migration_id)
        save_mapping(mapping_file, "accounts", account_map)
        
        item_map = migrate_items(client, transformer, data.get("Items", []), account_map, oauth_mgr)
        logger.log_data_operation("CREATE", "Item", len(item_map), migration_id)
        save_mapping(mapping_file, "items", item_map)
        
        migrate_invoices(
            client, 
            transformer, 
            data.get("Invoices", []), 
            customer_map, 
            item_map,
            oauth_mgr,
            add_memo=ADD_MIGRATION_MEMO
        )
        logger.log_data_operation("CREATE", "Invoice", len(data.get("Invoices", [])), migration_id)
        
        print("✓ Migration complete")
        
        # STEP 7: Verify
        print("\n[7/9] Verifying migration...")
        verifier = MigrationVerifier(client)
        
        verifier.verify_customers(len(data.get("Customers", [])))
        verifier.verify_vendors(len(data.get("Vendors", [])))
        verifier.verify_accounts(len(data.get("Accounts", [])))
        verifier.verify_items(len(data.get("Items", [])))
        verifier.verify_invoices(len(data.get("Invoices", [])))
        
        # Additional verification
        verifier.audit_invoice_math(sample_size=5)
        verifier.audit_duplicate_doc_numbers()
        verifier.detect_ghost_accounts()
        
        # STEP 8: Save results
        print("\n[8/9] Saving results...")
        
        # Verification report
        report_file = os.path.join(OUTPUT_DIR, f"verification_{migration_id}.json")
        verifier.save_report(report_file)
        
        print(f"✓ Results saved")
        
        # STEP 9: Schedule deletion
        print("\n[9/9] Scheduling secure deletion...")
        
        files_to_delete = [mapping_file, report_file]
        retention_mgr.schedule_deletion(migration_id, files_to_delete)
        
        # Log completion
        duration = (datetime.now() - start_time).total_seconds()
        logger.log_migration_complete(migration_id, success=True, duration_seconds=duration)
        
        print("\n" + "=" * 80)
        print("  SECURE MIGRATION COMPLETE")
        print("=" * 80)
        print(f"\nMigration ID: {migration_id}")
        print(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
        print(f"Data will be auto-deleted in {DATA_RETENTION_HOURS} hour(s)")
        print(f"\nVerification report: {report_file}")
        print(f"ID mappings: {mapping_file}")
        
        return {
            "success": True,
            "migration_id": migration_id,
            "duration_seconds": duration,
            "auto_delete_hours": DATA_RETENTION_HOURS,
            "verification_report": report_file,
            "id_mappings": mapping_file,
            "migrated_counts": {
                "customers": len(customer_map),
                "vendors": len(vendor_map),
                "accounts": len(account_map),
                "items": len(item_map),
                "invoices": len(data.get("Invoices", []))
            },
            "scan_warnings": scan_result.get('warnings', []),
            "recommended_qbo_plan": recommended_plan
        }
        
    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        logger.log_migration_complete(migration_id, success=False, duration_seconds=duration)
        
        print(f"\n❌ MIGRATION FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            "success": False,
            "migration_id": migration_id,
            "error": str(e),
            "duration_seconds": duration
        }


def save_mapping(mapping_file, entity_type, mapping_dict):
    """Save ID mapping incrementally"""
    if os.path.exists(mapping_file):
        with open(mapping_file, 'r') as f:
            all_mappings = json.load(f)
    else:
        all_mappings = {}
    
    all_mappings[entity_type] = mapping_dict
    
    with open(mapping_file, 'w') as f:
        json.dump(all_mappings, f, indent=2)


def migrate_customers(client, transformer, customers, oauth_mgr=None):
    """Migrate customers with resume capability"""
    print(f"\n  Migrating {len(customers)} customers...")
    customer_map = {}
    
    for i, qbd_customer in enumerate(customers):
        qbd_id = qbd_customer.get("ListID") or qbd_customer.get("Name")
        
        # Check if already created (resume capability)
        existing_qbo_id = client.was_entity_created("Customer", qbd_id)
        if existing_qbo_id:
            customer_map[qbd_id] = existing_qbo_id
            continue
        
        try:
            qbo_customer = transformer.transform_customer(qbd_customer)
            response = client.create_customer(qbo_customer, oauth_mgr)
            
            qbo_id = response["Customer"]["Id"]
            customer_map[qbd_id] = qbo_id
            
            # Record for resume
            client.record_created("Customer", qbd_id, qbo_id)
            
            if (i + 1) % 10 == 0:
                print(f"    {i + 1}/{len(customers)} customers migrated...")
                
        except Exception as e:
            print(f"    Error creating customer {qbd_customer.get('Name')}: {str(e)[:100]}")
    
    print(f"  ✓ {len(customer_map)} customers migrated")
    return customer_map


def migrate_vendors(client, transformer, vendors, oauth_mgr=None):
    """Migrate vendors"""
    print(f"\n  Migrating {len(vendors)} vendors...")
    vendor_map = {}
    
    for i, qbd_vendor in enumerate(vendors):
        qbd_id = qbd_vendor.get("ListID") or qbd_vendor.get("Name")
        
        existing_qbo_id = client.was_entity_created("Vendor", qbd_id)
        if existing_qbo_id:
            vendor_map[qbd_id] = existing_qbo_id
            continue
        
        try:
            qbo_vendor = transformer.transform_vendor(qbd_vendor)
            response = client.create_vendor(qbo_vendor, oauth_mgr)
            
            qbo_id = response["Vendor"]["Id"]
            vendor_map[qbd_id] = qbo_id
            
            client.record_created("Vendor", qbd_id, qbo_id)
            
            if (i + 1) % 10 == 0:
                print(f"    {i + 1}/{len(vendors)} vendors migrated...")
                
        except Exception as e:
            print(f"    Error creating vendor {qbd_vendor.get('Name')}: {str(e)[:100]}")
    
    print(f"  ✓ {len(vendor_map)} vendors migrated")
    return vendor_map


def migrate_accounts(client, transformer, accounts, oauth_mgr=None):
    """Migrate accounts"""
    print(f"\n  Migrating {len(accounts)} accounts...")
    account_map = {}
    
    for i, qbd_account in enumerate(accounts):
        qbd_id = qbd_account.get("ListID") or qbd_account.get("Name")
        
        existing_qbo_id = client.was_entity_created("Account", qbd_id)
        if existing_qbo_id:
            account_map[qbd_id] = existing_qbo_id
            continue
        
        try:
            qbo_account = transformer.transform_account(qbd_account)
            response = client.create_account(qbo_account, oauth_mgr)
            
            qbo_id = response["Account"]["Id"]
            account_map[qbd_id] = qbo_id
            
            client.record_created("Account", qbd_id, qbo_id)
            
            if (i + 1) % 10 == 0:
                print(f"    {i + 1}/{len(accounts)} accounts migrated...")
                
        except Exception as e:
            print(f"    Error creating account {qbd_account.get('Name')}: {str(e)[:100]}")
    
    print(f"  ✓ {len(account_map)} accounts migrated")
    return account_map


def migrate_items(client, transformer, items, account_map, oauth_mgr=None):
    """Migrate items"""
    print(f"\n  Migrating {len(items)} items...")
    item_map = {}
    
    # Find default income account
    income_account_id = next((v for k, v in account_map.items() if "income" in k.lower()), None)
    
    for i, qbd_item in enumerate(items):
        qbd_id = qbd_item.get("ListID") or qbd_item.get("Name")
        
        existing_qbo_id = client.was_entity_created("Item", qbd_id)
        if existing_qbo_id:
            item_map[qbd_id] = existing_qbo_id
            continue
        
        try:
            qbo_item = transformer.transform_item(qbd_item, income_account_id)
            response = client.create_item(qbo_item, oauth_mgr)
            
            qbo_id = response["Item"]["Id"]
            item_map[qbd_id] = qbo_id
            
            client.record_created("Item", qbd_id, qbo_id)
            
            if (i + 1) % 10 == 0:
                print(f"    {i + 1}/{len(items)} items migrated...")
                
        except Exception as e:
            print(f"    Error creating item {qbd_item.get('Name')}: {str(e)[:100]}")
    
    print(f"  ✓ {len(item_map)} items migrated")
    return item_map


def migrate_invoices(client, transformer, invoices, customer_map, item_map, oauth_mgr=None, add_memo=True):
    """Migrate invoices with migration memo"""
    print(f"\n  Migrating {len(invoices)} invoices...")
    success_count = 0
    
    for i, qbd_invoice in enumerate(invoices):
        qbd_id = qbd_invoice.get("TxnID") or qbd_invoice.get("RefNumber")
        
        existing_qbo_id = client.was_entity_created("Invoice", qbd_id)
        if existing_qbo_id:
            success_count += 1
            continue
        
        try:
            qbo_invoice = transformer.transform_invoice(qbd_invoice, customer_map, item_map)
            
            # Add migration memo
            if add_memo:
                migration_date = datetime.now().strftime("%Y-%m-%d")
                memo = MIGRATION_MEMO_TEMPLATE.format(
                    date=migration_date,
                    app_name=APP_NAME
                )
                qbo_invoice["CustomerMemo"] = {"value": memo}
            
            response = client.create_invoice(qbo_invoice, oauth_mgr)
            
            qbo_id = response["Invoice"]["Id"]
            client.record_created("Invoice", qbd_id, qbo_id)
            
            success_count += 1
            
            if (i + 1) % 10 == 0:
                print(f"    {i + 1}/{len(invoices)} invoices migrated...")
                
        except Exception as e:
            print(f"    Error creating invoice {qbd_invoice.get('RefNumber')}: {str(e)[:100]}")
    
    print(f"  ✓ {success_count} invoices migrated")
    return success_count


if __name__ == "__main__":
    # Test with sample encrypted data
    migration_id = SecurityManager.generate_session_id()
    
    # For testing, load from previous extraction
    if os.path.exists(INPUT_FILE):
        with open(INPUT_FILE, 'r') as f:
            data = json.load(f)
        
        # Encrypt it
        json_string = json.dumps(data)
        encrypted = EncryptionManager.encrypt_data(json_string.encode())
        
        # Format as C# client would (GCM mode)
        encrypted_string = f"{encrypted['iv']}:{encrypted['tag']}:{encrypted['ciphertext']}:{encrypted['key']}"
        
        # Run secure migration
        result = secure_migration(encrypted_string, migration_id)
        
        print("\n" + json.dumps(result, indent=2))
    else:
        print(f"❌ Test data file not found: {INPUT_FILE}")
        print("Please run the Desktop Extractor first to generate test data.")