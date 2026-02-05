from sqlalchemy import create_engine, text
import os
import logging

logger = logging.getLogger(__name__)


db_url = os.getenv(
    "DATABASE_URL",
    "postgresql://qbmigration:TestPass123@localhost:5432/qbmigration_dev",
)
engine = create_engine(db_url)

with engine.connect() as conn:
    try:
        conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN stripe_payment_intent VARCHAR(255) DEFAULT NULL"
            )
        )
        conn.commit()
        logger.info("Added stripe_payment_intent column")
    except Exception as e:
        if "already exists" in str(e):
            logger.info("stripe_payment_intent column already exists")
        else:
            logger.info(f"Error: {e}")
