"""
Database initialization script for ForensicBridge
Run this script to create/update all database tables including user accounts.

Usage:
    python init_database.py
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)


# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def init_database():
    """Initialize database with all tables"""
    logger.info("=" * 60)
    logger.info("ForensicBridge Database Initialization")
    logger.info("=" * 60)

    # Import Flask app and database
    from app import create_app
    from models.database import db

    app = create_app()

    with app.app_context():
        # Import all models so SQLAlchemy knows about them
        from models.license import License
        from models.migration import Migration
        from models.user import User

        logger.info("\n1. Creating all database tables...")
        db.create_all()
        logger.info("   [OK] Tables created successfully")

        # Add any missing columns
        logger.info("\n2. Checking for missing columns...")
        from sqlalchemy import inspect, text

        inspector = inspect(db.engine)
        existing_columns = [col["name"] for col in inspector.get_columns("users")]

        # Columns we need for tier system
        tier_columns = {
            "subscription_tier": "VARCHAR(50) DEFAULT NULL",
            "migrations_purchased": "INTEGER DEFAULT 0",
            "migrations_used": "INTEGER DEFAULT 0",
            "tier_purchased_at": "TIMESTAMP DEFAULT NULL",
        }

        with db.engine.connect() as conn:
            for col_name, col_type in tier_columns.items():
                if col_name not in existing_columns:
                    try:
                        conn.execute(
                            text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                        )
                        conn.commit()
                        logger.info(f"   [OK] Added column: {col_name}")
                    except Exception as e:
                        if "already exists" in str(e):
                            logger.info(f"   [--] Column exists: {col_name}")
                        else:
                            logger.info(f"   [ERR] Error adding {col_name}: {e}")
                else:
                    logger.info(f"   [--] Column exists: {col_name}")

        # Verify tables exist
        logger.info("\n3. Verifying tables...")
        tables = inspector.get_table_names()
        required_tables = ["users", "migrations", "licenses"]
        for table in required_tables:
            if table in tables:
                logger.info(f"   [OK] Table exists: {table}")
            else:
                logger.info(f"   [ERR] Missing table: {table}")

        # Show user count
        logger.info("\n4. Current database stats:")
        try:
            user_count = User.query.count()
            migration_count = Migration.query.count()
            logger.info(f"   - Users: {user_count}")
            logger.info(f"   - Migrations: {migration_count}")
        except Exception as e:
            logger.info(f"   - Error getting stats: {e}")

        logger.info("\n" + "=" * 60)
        logger.info("Database initialization complete!")
        logger.info("=" * 60)
        logger.info("\nYou can now:")
        logger.info("  1. Start the Flask server: python run.py")
        logger.info("  2. Register a new account at http://localhost:3000/register")
        logger.info("  3. Login at http://localhost:3000/login")


if __name__ == "__main__":
    init_database()
