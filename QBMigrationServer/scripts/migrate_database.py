#!/usr/bin/env python3
"""
Database Migration Script for ForensicBridge
============================================
Run this script on EC2 to add missing columns to the database.

Usage:
    cd ~/QBMigration/QBMigrationServer
    source venv/bin/activate
    python scripts/migrate_database.py
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError

def get_database_url():
    """Get database URL from environment"""
    url = os.getenv('DATABASE_URL')
    if not url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)
    return url

def run_migration(engine, sql, description):
    """Run a single migration SQL statement"""
    try:
        with engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
        print(f"  ✓ {description}")
        return True
    except ProgrammingError as e:
        if "already exists" in str(e) or "duplicate column" in str(e).lower():
            print(f"  → {description} (already exists, skipping)")
            return True
        else:
            print(f"  ✗ {description}: {str(e)}")
            return False
    except Exception as e:
        print(f"  ✗ {description}: {str(e)}")
        return False

def main():
    print("=" * 60)
    print("ForensicBridge Database Migration")
    print("=" * 60)
    print()
    
    # Connect to database
    database_url = get_database_url()
    print(f"Connecting to database...")
    
    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("  ✓ Database connection successful")
    except OperationalError as e:
        print(f"  ✗ Failed to connect to database: {str(e)}")
        sys.exit(1)
    
    print()
    print("Running migrations...")
    print()
    
    # =========================================================================
    # USERS TABLE MIGRATIONS
    # =========================================================================
    print("─" * 40)
    print("Users Table Migrations")
    print("─" * 40)
    
    users_migrations = [
        (
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS qbo_access_token TEXT;",
            "Add qbo_access_token column"
        ),
        (
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS qbo_refresh_token TEXT;",
            "Add qbo_refresh_token column"
        ),
        (
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS qbo_realm_id VARCHAR(50);",
            "Add qbo_realm_id column"
        ),
        (
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS qbo_token_expires_at TIMESTAMP;",
            "Add qbo_token_expires_at column"
        ),
        (
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS qbo_connected_at TIMESTAMP;",
            "Add qbo_connected_at column"
        ),
    ]
    
    users_success = 0
    for sql, desc in users_migrations:
        if run_migration(engine, sql, desc):
            users_success += 1
    
    print(f"\nUsers table: {users_success}/{len(users_migrations)} migrations successful")
    
    # =========================================================================
    # MIGRATIONS TABLE MIGRATIONS
    # =========================================================================
    print()
    print("─" * 40)
    print("Migrations Table Migrations")
    print("─" * 40)
    
    migrations_migrations = [
        (
            "ALTER TABLE migrations ADD COLUMN IF NOT EXISTS destination VARCHAR(50) DEFAULT 'qbo';",
            "Add destination column"
        ),
        (
            "ALTER TABLE migrations ADD COLUMN IF NOT EXISTS caseware_bundle_path TEXT;",
            "Add caseware_bundle_path column"
        ),
        (
            "ALTER TABLE migrations ADD COLUMN IF NOT EXISTS caseware_bundle_ready BOOLEAN DEFAULT FALSE;",
            "Add caseware_bundle_ready column"
        ),
    ]
    
    migrations_success = 0
    for sql, desc in migrations_migrations:
        if run_migration(engine, sql, desc):
            migrations_success += 1
    
    print(f"\nMigrations table: {migrations_success}/{len(migrations_migrations)} migrations successful")
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    print()
    print("=" * 60)
    total = len(users_migrations) + len(migrations_migrations)
    success = users_success + migrations_success
    
    if success == total:
        print("✓ ALL MIGRATIONS COMPLETED SUCCESSFULLY")
        print()
        print("Next steps:")
        print("  1. Restart the ForensicBridge service:")
        print("     sudo systemctl restart forensicbridge")
        print()
        print("  2. Verify the service is running:")
        print("     sudo systemctl status forensicbridge")
        print()
        print("  3. Check the logs for any errors:")
        print("     sudo journalctl -u forensicbridge -n 20 --no-pager")
    else:
        print(f"⚠ {success}/{total} migrations completed")
        print("Some migrations failed. Check the error messages above.")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
