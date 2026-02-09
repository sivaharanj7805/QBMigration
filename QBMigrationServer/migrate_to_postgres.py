"""
Database Migration Script
Migrates from SQLite to PostgreSQL and updates schema
"""

import logging
import os

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

from app import create_app, db  # noqa: E402


def migrate_database():
    """Migrate database schema"""

    # SECURITY FIX: Safety check to prevent accidental production data loss
    db_url = os.getenv("DATABASE_URL", "")
    flask_env = os.getenv("FLASK_ENV", "development")

    if "production" in db_url.lower() or flask_env == "production":
        logger.error("REFUSING to run drop_all() against a production database.")
        logger.error("Set FLASK_ENV=development and use a non-production DATABASE_URL.")
        return

    confirm = os.getenv("CONFIRM_DB_RESET", "")
    if confirm != "yes":
        logger.error("This will DROP ALL TABLES. Set CONFIRM_DB_RESET=yes to proceed.")
        return

    app = create_app()

    with app.app_context():
        logger.info("Creating database tables...")

        # Drop all tables (if migrating)
        db.drop_all()

        # Create all tables
        db.create_all()

        logger.info("Database migration completed successfully!")
        # SECURITY FIX: Do not log full database URI (contains credentials)
        logger.info("Database migration applied to configured database.")


if __name__ == "__main__":
    migrate_database()
