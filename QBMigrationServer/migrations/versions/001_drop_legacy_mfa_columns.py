"""Drop legacy unencrypted MFA columns (CRIT-04 fix)

These columns stored TOTP secrets and backup codes in plaintext.
Data should already be migrated to _mfa_secret_encrypted and
_backup_codes_encrypted via User.migrate_all_legacy_mfa().

Run User.migrate_all_legacy_mfa() BEFORE applying this migration.

Revision ID: 001_drop_legacy_mfa
Revises:
Create Date: 2026-02-11
"""

import sqlalchemy as sa
from alembic import op

revision = "001_drop_legacy_mfa"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Verify all legacy data has been migrated before dropping columns
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM users "
            "WHERE (mfa_secret IS NOT NULL AND mfa_secret_encrypted IS NULL) "
            "OR (backup_codes IS NOT NULL AND backup_codes_encrypted IS NULL)"
        )
    )
    unmigrated_count = result.scalar()
    if unmigrated_count > 0:
        raise RuntimeError(
            f"Cannot drop legacy MFA columns: {unmigrated_count} user(s) still have "
            "unmigrated data. Run User.migrate_all_legacy_mfa() first."
        )

    op.drop_column("users", "mfa_secret")
    op.drop_column("users", "backup_codes")


def downgrade():
    op.add_column("users", sa.Column("mfa_secret", sa.String(32), nullable=True))
    op.add_column("users", sa.Column("backup_codes", sa.Text(), nullable=True))
