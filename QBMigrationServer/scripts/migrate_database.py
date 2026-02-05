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

import logging
import os
import sys

logger = logging.getLogger(__name__)


# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import OperationalError, ProgrammingError  # noqa: E402


def get_database_url():
    """Get database URL from environment"""
    url = os.getenv("DATABASE_URL")
    if not url:
        logger.info("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)
    return url


def run_migration(engine, sql, description):
    """Run a single migration SQL statement"""
    try:
        with engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
        logger.info(f"  ✓ {description}")
        return True
    except ProgrammingError as e:
        if "already exists" in str(e) or "duplicate column" in str(e).lower():
            logger.info(f"  → {description} (already exists, skipping)")
            return True
        else:
            logger.info(f"  ✗ {description}: {str(e)}")
            return False
    except Exception as e:
        logger.info(f"  ✗ {description}: {str(e)}")
        return False


def main():
    logger.info("=" * 60)
    logger.info("ForensicBridge Database Migration")
    logger.info("=" * 60)
    logger.info()

    # Connect to database
    database_url = get_database_url()
    logger.info("Connecting to database...")

    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("  ✓ Database connection successful")
    except OperationalError as e:
        logger.info(f"  ✗ Failed to connect to database: {str(e)}")
        sys.exit(1)

    logger.info()
    logger.info("Running migrations...")
    logger.info()

    # =========================================================================
    # USERS TABLE MIGRATIONS
    # =========================================================================
    logger.info("─" * 40)
    logger.info("Users Table Migrations")
    logger.info("─" * 40)

    users_migrations = [
        (
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS qbo_access_token TEXT;",
            "Add qbo_access_token column",
        ),
        (
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS qbo_refresh_token TEXT;",
            "Add qbo_refresh_token column",
        ),
        (
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS qbo_realm_id VARCHAR(50);",
            "Add qbo_realm_id column",
        ),
        (
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS qbo_token_expires_at TIMESTAMP;",
            "Add qbo_token_expires_at column",
        ),
        (
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS qbo_connected_at TIMESTAMP;",
            "Add qbo_connected_at column",
        ),
    ]

    users_success = 0
    for sql, desc in users_migrations:
        if run_migration(engine, sql, desc):
            users_success += 1

    logger.info(
        f"\nUsers table: {users_success}/{len(users_migrations)} migrations successful"
    )

    # =========================================================================
    # MIGRATIONS TABLE MIGRATIONS
    # =========================================================================
    logger.info()
    logger.info("─" * 40)
    logger.info("Migrations Table Migrations")
    logger.info("─" * 40)

    migrations_migrations = [
        (
            "ALTER TABLE migrations ADD COLUMN IF NOT EXISTS destination VARCHAR(50) DEFAULT 'qbo';",
            "Add destination column",
        ),
        (
            "ALTER TABLE migrations ADD COLUMN IF NOT EXISTS caseware_bundle_path TEXT;",
            "Add caseware_bundle_path column",
        ),
        (
            "ALTER TABLE migrations ADD COLUMN IF NOT EXISTS caseware_bundle_ready BOOLEAN DEFAULT FALSE;",
            "Add caseware_bundle_ready column",
        ),
    ]

    migrations_success = 0
    for sql, desc in migrations_migrations:
        if run_migration(engine, sql, desc):
            migrations_success += 1

    logger.info(
        f"\nMigrations table: {migrations_success}/{len(migrations_migrations)} migrations successful"
    )

    # =========================================================================
    # SUMMARY
    # =========================================================================
    logger.info()
    logger.info("=" * 60)
    total = len(users_migrations) + len(migrations_migrations)
    success = users_success + migrations_success

    if success == total:
        logger.info("✓ ALL MIGRATIONS COMPLETED SUCCESSFULLY")
        logger.info()
        logger.info("Next steps:")
        logger.info("  1. Restart the ForensicBridge service:")
        logger.info("     sudo systemctl restart forensicbridge")
        logger.info()
        logger.info("  2. Verify the service is running:")
        logger.info("     sudo systemctl status forensicbridge")
        logger.info()
        logger.info("  3. Check the logs for any errors:")
        logger.info("     sudo journalctl -u forensicbridge -n 20 --no-pager")
    else:
        logger.info(f"⚠ {success}/{total} migrations completed")
        logger.info("Some migrations failed. Check the error messages above.")

    logger.info("=" * 60)


if __name__ == "__main__":
    main()
