import logging
import os

from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise EnvironmentError(
        "DATABASE_URL environment variable is required. "
        "Example: postgresql://user:pass@host:5432/dbname"
    )
engine = create_engine(db_url)

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'users'
        AND column_name IN (
            'subscription_tier', 'migrations_purchased',
            'migrations_used', 'stripe_customer_id',
            'tier_purchased_at'
        )
        ORDER BY column_name
    """))
    logger.info("Tier columns in users table:")
    for row in result:
        logger.info(f"  - {row[0]}: {row[1]}")
