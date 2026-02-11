"""Add migration_items table for per-entity tracking

AUDIT FIX MUST-03: Entity-level tracking was previously only in SQLite
inside the QBMigrationService process. If the EC2 instance dies, per-entity
status is lost. This migration adds a PostgreSQL-backed migration_items table
for durable, queryable per-entity status.

Revision ID: 002_add_migration_items
Revises: 001_drop_legacy_mfa_columns
Create Date: 2026-02-11
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "002_add_migration_items"
down_revision = "001_drop_legacy_mfa_columns"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "migration_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "migration_id",
            sa.String(36),
            sa.ForeignKey("migrations.migration_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("source_name", sa.String(500)),
        sa.Column("destination_id", sa.String(100)),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text()),
        sa.Column("error_code", sa.String(20)),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("batch_id", sa.String(50)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    )

    # Deduplication index
    op.create_index(
        "idx_migitem_dedup",
        "migration_items",
        ["migration_id", "entity_type", "source_id"],
        unique=True,
    )
    # Status query index
    op.create_index(
        "idx_migitem_migration_status",
        "migration_items",
        ["migration_id", "status"],
    )
    # Entity type query index
    op.create_index(
        "idx_migitem_migration_type",
        "migration_items",
        ["migration_id", "entity_type"],
    )
    # Batch query index
    op.create_index("idx_migitem_batch", "migration_items", ["batch_id"])


def downgrade():
    op.drop_index("idx_migitem_batch", table_name="migration_items")
    op.drop_index("idx_migitem_migration_type", table_name="migration_items")
    op.drop_index("idx_migitem_migration_status", table_name="migration_items")
    op.drop_index("idx_migitem_dedup", table_name="migration_items")
    op.drop_table("migration_items")
