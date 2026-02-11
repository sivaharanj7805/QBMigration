"""Add team_invites and dead_letter_webhooks tables

Creates proper schema for team invitations (replacing legacy auto_migrate DDL)
and the dead letter queue for failed webhook events.

Revision ID: 003_add_team_invites_dlq
Revises: 002_add_migration_items
Create Date: 2026-02-11
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "003_add_team_invites_dlq"
down_revision = "002_add_migration_items"
branch_labels = None
depends_on = None


def upgrade():
    # -----------------------------------------------------------------------
    # team_invites
    # -----------------------------------------------------------------------
    op.create_table(
        "team_invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), server_default="member"),
        sa.Column("invite_token", sa.String(64), unique=True),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column(
            "accepted_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "idx_team_invite_status_expires",
        "team_invites",
        ["status", "expires_at"],
    )
    op.create_index(
        "idx_team_invite_owner_status",
        "team_invites",
        ["owner_user_id", "status"],
    )

    # -----------------------------------------------------------------------
    # dead_letter_webhooks
    # -----------------------------------------------------------------------
    op.create_table(
        "dead_letter_webhooks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("event_id", sa.String(200)),
        sa.Column("migration_id", sa.String(36)),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("headers", sa.Text()),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("error_traceback", sa.Text()),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="failed",
        ),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_retry_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by", sa.String(100)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_dlq_status", "dead_letter_webhooks", ["status"])
    op.create_index(
        "idx_dlq_source_created",
        "dead_letter_webhooks",
        ["source", "created_at"],
    )
    op.create_index("idx_dlq_migration", "dead_letter_webhooks", ["migration_id"])


def downgrade():
    op.drop_index("idx_dlq_migration", table_name="dead_letter_webhooks")
    op.drop_index("idx_dlq_source_created", table_name="dead_letter_webhooks")
    op.drop_index("idx_dlq_status", table_name="dead_letter_webhooks")
    op.drop_table("dead_letter_webhooks")

    op.drop_index("idx_team_invite_owner_status", table_name="team_invites")
    op.drop_index("idx_team_invite_status_expires", table_name="team_invites")
    op.drop_table("team_invites")
