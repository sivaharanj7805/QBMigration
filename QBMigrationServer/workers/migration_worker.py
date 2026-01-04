from celery import Celery
from models.database import db
from models.migration import Migration
from datetime import datetime, timedelta
import os
import sys
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'QBMigrationService'))

from encryption import EncryptionManager
from data_retention import DataRetentionManager
from audit_logger import AuditLogger

# Initialize Celery
celery = Celery('migration_worker')

def init_celery(app):
    """Initialize Celery with Flask app"""
    celery.conf.update(app.config)
    
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
    return celery


@celery.task(bind=True, max_retries=3)
def process_migration(self, migration_id):
    """
    Background task to process migration
    
    Args:
        migration_id: Database ID of migration record
    """
    
    from app import app  # Import here to avoid circular dependency
    
    with app.app_context():
        migration = Migration.query.get(migration_id)
        
        if not migration:
            raise ValueError(f"Migration {migration_id} not found")
        
        logger = AuditLogger()
        retention_mgr = DataRetentionManager()
        
        try:
            # Mark as started
            migration.mark_started()
            migration.update_progress(5, "Decrypting data")
            
            # Step 1: Decrypt data
            with open(migration.encrypted_file_path, 'r') as f:
                encrypted_data = f.read()
            
            decrypted_json = EncryptionManager.decrypt_string(encrypted_data)
            data = json.loads(decrypted_json)
            
            logger.log_encryption(
                migration.migration_id,
                "decrypt_complete",
                file_size=len(decrypted_json)
            )
            
            # Update migration with data counts
            migration.company_name = data.get('CompanyName', 'Unknown')
            migration.customers_count = len(data.get('Customers', []))
            migration.vendors_count = len(data.get('Vendors', []))
            migration.accounts_count = len(data.get('Accounts', []))
            migration.items_count = len(data.get('Items', []))
            migration.invoices_count = len(data.get('Invoices', []))
            db.session.commit()
            
            migration.update_progress(10, "Initializing QuickBooks Online connection")
            
            # Step 2: Import migration logic from main.py
            from oauth_manager import OAuthManager
            from qbo_client import QBOClient
            from data_transformer import DataTransformer
            from verifier import MigrationVerifier
            from config import CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN
            
            # Step 3: Refresh OAuth token
            oauth_mgr = OAuthManager(CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN)
            access_token = oauth_mgr.get_access_token()
            
            logger.log_oauth_refresh(success=True)
            
            migration.update_progress(15, "Connected to QuickBooks Online")
            
            # Step 4: Initialize QBO client
            client = QBOClient()
            client.headers["Authorization"] = f"Bearer {access_token}"
            
            transformer = DataTransformer()
            
            # Step 5: Migrate customers
            migration.update_progress(20, "Migrating customers")
            
            from main import migrate_customers
            customer_map = migrate_customers(client, transformer, data['Customers'])
            migration.customers_migrated = len(customer_map)
            db.session.commit()
            
            logger.log_data_operation(
                "CREATE",
                "Customer",
                len(customer_map),
                migration.migration_id
            )
            
            # Step 6: Migrate vendors
            migration.update_progress(35, "Migrating vendors")
            
            from main import migrate_vendors
            vendor_map = migrate_vendors(client, transformer, data['Vendors'])
            migration.vendors_migrated = len(vendor_map)
            db.session.commit()
            
            logger.log_data_operation(
                "CREATE",
                "Vendor",
                len(vendor_map),
                migration.migration_id
            )
            
            # Step 7: Migrate accounts
            migration.update_progress(50, "Migrating chart of accounts")
            
            from main import migrate_accounts
            account_map = migrate_accounts(client, transformer, data['Accounts'])
            migration.accounts_migrated = len(account_map)
            db.session.commit()
            
            logger.log_data_operation(
                "CREATE",
                "Account",
                len(account_map),
                migration.migration_id
            )
            
            # Step 8: Migrate items
            migration.update_progress(65, "Migrating items")
            
            from main import migrate_items
            item_map = migrate_items(client, transformer, data['Items'], account_map)
            migration.items_migrated = len(item_map)
            db.session.commit()
            
            logger.log_data_operation(
                "CREATE",
                "Item",
                len(item_map),
                migration.migration_id
            )
            
            # Step 9: Migrate invoices
            migration.update_progress(80, "Migrating invoices")
            
            from main import migrate_invoices
            migrate_invoices(client, transformer, data['Invoices'], customer_map, item_map)
            migration.invoices_migrated = len(data['Invoices'])
            db.session.commit()
            
            logger.log_data_operation(
                "CREATE",
                "Invoice",
                len(data['Invoices']),
                migration.migration_id
            )
            
            # Step 10: Verify migration
            migration.update_progress(90, "Verifying migration")
            
            verifier = MigrationVerifier(client)
            verifier.verify_customers(migration.customers_count)
            verifier.verify_vendors(migration.vendors_count)
            verifier.verify_accounts(migration.accounts_count)
            verifier.verify_items(migration.items_count)
            verifier.verify_invoices(migration.invoices_count)
            
            # Save verification report
            output_dir = os.path.join(
                os.path.dirname(__file__),
                '..',
                '..',
                'data',
                'migration_results'
            )
            os.makedirs(output_dir, exist_ok=True)
            
            report_path = os.path.join(
                output_dir,
                f"verification_{migration.migration_id}.json"
            )
            
            verifier.save_report(report_path)
            migration.verification_report_path = report_path
            db.session.commit()
            
            # Step 11: Schedule deletion
            migration.update_progress(95, "Scheduling data deletion")
            
            files_to_delete = [
                migration.encrypted_file_path,
                report_path
            ]
            
            retention_mgr.schedule_deletion(
                migration.migration_id,
                files_to_delete,
                delay_hours=app.config['DATA_RETENTION_HOURS']
            )
            
            # Step 12: Complete
            migration.update_progress(100, "Migration complete")
            migration.mark_completed()
            
            logger.log_migration_complete(
                migration.migration_id,
                success=True,
                duration_seconds=(datetime.utcnow() - migration.started_at).total_seconds()
            )
            
            # TODO: Send completion email to user
            
            return {
                'success': True,
                'migration_id': migration.migration_id
            }
            
        except Exception as e:
            # Migration failed
            error_message = str(e)
            migration.mark_failed(error_message)
            
            logger.log_migration_complete(
                migration.migration_id,
                success=False,
                duration_seconds=(datetime.utcnow() - migration.started_at).total_seconds() if migration.started_at else 0
            )
            
            # Retry if not max retries
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e, countdown=60)  # Retry in 60 seconds
            
            # TODO: Send failure email to user
            
            raise