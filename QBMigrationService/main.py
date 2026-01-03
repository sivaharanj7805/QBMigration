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
    """Main secure migration function"""
    
    print("=" * 80)
    print("  QuickBooks SECURE Migration")
    print("=" * 80)
    
    # Initialize security components
    logger = AuditLogger()
    retention_mgr = DataRetentionManager(retention_hours=DATA_RETENTION_HOURS)
    
    start_time = datetime.now()
    
    try:
        # STEP 1: Decrypt data
        print(f"\n[1/7] Decrypting data (Migration ID: {migration_id})...")
        logger.log_encryption(migration_id, "decrypt_start")
        
        decrypted_json = EncryptionManager.decrypt_string(encrypted_data_string)
        data = json.loads(decrypted_json)
        
        logger.log_encryption(
            migration_id,
            "decrypt_complete",
            file_size=len(decrypted_json)
        )
        
        logger.log_migration_start(
            migration_id,
            data.get("CompanyName", "Unknown"),
            {
                "customers": len(data["Customers"]),
                "vendors": len(data["Vendors"]),
                "accounts": len(data["Accounts"]),
                "items": len(data["Items"]),
                "invoices": len(data["Invoices"])
            }
        )
        
        print(f"✓ Data decrypted")
        print(f"  Company: {data.get('CompanyName')}")
        
        # STEP 2: Refresh OAuth token
        print("\n[2/7] Refreshing OAuth token...")
        oauth_mgr = OAuthManager(CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN)
        
        try:
            access_token = oauth_mgr.get_access_token()
            logger.log_oauth_refresh(success=True)
            print("✓ OAuth token refreshed")
        except Exception as e:
            logger.log_oauth_refresh(success=False, error=str(e))
            raise
        
        # STEP 3: Initialize QBO client with fresh token
        print("\n[3/7] Initializing QuickBooks Online client...")
        client = QBOClient()
        client.headers["Authorization"] = f"Bearer {access_token}"
        print("✓ Client initialized")
        
        # STEP 4: Migrate data
        print("\n[4/7] Migrating data...")
        transformer = DataTransformer()
        
        # Import functions from previous main.py
        from main import (
            migrate_customers,
            migrate_vendors,
            migrate_accounts,
            migrate_items,
            migrate_invoices
        )
        
        customer_map = migrate_customers(client, transformer, data["Customers"])
        logger.log_data_operation("CREATE", "Customer", len(customer_map), migration_id)
        
        vendor_map = migrate_vendors(client, transformer, data["Vendors"])
        logger.log_data_operation("CREATE", "Vendor", len(vendor_map), migration_id)
        
        account_map = migrate_accounts(client, transformer, data["Accounts"])
        logger.log_data_operation("CREATE", "Account", len(account_map), migration_id)
        
        item_map = migrate_items(client, transformer, data["Items"], account_map)
        logger.log_data_operation("CREATE", "Item", len(item_map), migration_id)
        
        migrate_invoices(client, transformer, data["Invoices"], customer_map, item_map)
        logger.log_data_operation("CREATE", "Invoice", len(data["Invoices"]), migration_id)
        
        print("✓ Migration complete")
        
        # STEP 5: Verify
        print("\n[5/7] Verifying migration...")
        verifier = MigrationVerifier(client)
        
        verifier.verify_customers(len(data["Customers"]))
        verifier.verify_vendors(len(data["Vendors"]))
        verifier.verify_accounts(len(data["Accounts"]))
        verifier.verify_items(len(data["Items"]))
        verifier.verify_invoices(len(data["Invoices"]))
        
        # STEP 6: Save results
        print("\n[6/7] Saving results...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # ID mappings
        mappings = {
            "customers": customer_map,
            "vendors": vendor_map,
            "accounts": account_map,
            "items": item_map
        }
        
        mapping_file = os.path.join(OUTPUT_DIR, f"id_mappings_{migration_id}.json")
        with open(mapping_file, 'w') as f:
            json.dump(mappings, f, indent=2)
        
        # Verification report
        report_file = os.path.join(OUTPUT_DIR, f"verification_{migration_id}.json")
        verifier.save_report(report_file)
        
        print(f"✓ Results saved")
        
        # STEP 7: Schedule deletion
        print("\n[7/7] Scheduling secure deletion...")
        
        files_to_delete = [mapping_file, report_file]
        retention_mgr.schedule_deletion(migration_id, files_to_delete)
        
        # Log completion
        duration = (datetime.now() - start_time).total_seconds()
        logger.log_migration_complete(migration_id, success=True, duration_seconds=duration)
        
        print("\n" + "=" * 80)
        print("  SECURE MIGRATION COMPLETE")
        print("=" * 80)
        print(f"\nMigration ID: {migration_id}")
        print(f"Duration: {duration:.1f} seconds")
        print(f"Data will be auto-deleted in {DATA_RETENTION_HOURS} hour(s)")
        
        return {
            "success": True,
            "migration_id": migration_id,
            "duration_seconds": duration,
            "auto_delete_hours": DATA_RETENTION_HOURS
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
            "error": str(e)
        }

if __name__ == "__main__":
    # Test with sample encrypted data
    # In production, this comes from API endpoint
    
    migration_id = SecurityManager.generate_session_id()
    
    # For testing, load from previous extraction
    with open(INPUT_FILE, 'r') as f:
        data = json.load(f)
    
    # Encrypt it
    json_string = json.dumps(data)
    encrypted = EncryptionManager.encrypt_data(json_string.encode())
    
    # Format as C# client would
    encrypted_string = f"{encrypted['iv']}:{encrypted['tag']}:{encrypted['ciphertext']}:{encrypted['key']}"
    
    # Run secure migration
    result = secure_migration(encrypted_string, migration_id)
    
    print("\n" + json.dumps(result, indent=2))