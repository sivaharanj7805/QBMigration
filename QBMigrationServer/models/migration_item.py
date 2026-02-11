"""
MigrationItem Model — Per-entity tracking for granular retry and forensics.

AUDIT FIX MUST-03: Entity-level tracking was previously only in SQLite inside the
QBMigrationService process. If the EC2 instance dies, per-entity status is lost.
This PostgreSQL-backed model provides durable, queryable per-entity status that
survives instance termination and enables granular retry from the dashboard.
"""

import logging
from datetime import datetime, timezone

from models.database import db

logger = logging.getLogger(__name__)


class MigrationItem(db.Model):
    """Tracks individual entity migration status within a migration job."""

    __tablename__ = "migration_items"

    __table_args__ = (
        # Deduplication: same source entity can't be tracked twice per migration
        db.Index(
            "idx_migitem_dedup",
            "migration_id",
            "entity_type",
            "source_id",
            unique=True,
        ),
        # Query: "show me all failed items for this migration"
        db.Index("idx_migitem_migration_status", "migration_id", "status"),
        # Query: "how many items per entity type for this migration?"
        db.Index("idx_migitem_migration_type", "migration_id", "entity_type"),
        # Query: "show me all items processed in this batch"
        db.Index("idx_migitem_batch", "batch_id"),
    )

    id = db.Column(db.Integer, primary_key=True)

    # Link to parent Migration (CASCADE: delete items when migration deleted)
    migration_id = db.Column(
        db.String(36),
        db.ForeignKey("migrations.migration_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Entity identification
    entity_type = db.Column(
        db.String(50), nullable=False
    )  # Customer, Vendor, Invoice, Bill, Account, etc.
    source_id = db.Column(
        db.String(100), nullable=False
    )  # ListID/TxnID from QBD
    source_name = db.Column(
        db.String(500)
    )  # Display name for UI (e.g., "Acme Corp", "INV-1001")

    # Destination (QBO) identification
    destination_id = db.Column(db.String(100))  # QBO entity ID after creation

    # Status tracking
    status = db.Column(
        db.String(20),
        nullable=False,
        default="pending",
    )  # pending | success | failed | skipped | retrying

    # Error details (for failed items)
    error_message = db.Column(db.Text)
    error_code = db.Column(db.String(20))  # QBO error code (e.g., "6000", "5010")

    # Retry tracking
    retry_count = db.Column(db.Integer, default=0, nullable=False)
    max_retries = db.Column(db.Integer, default=3, nullable=False)

    # Batch tracking (which batch request this item was in)
    batch_id = db.Column(db.String(50))  # bId from QBO Batch API

    # Timestamps
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    processed_at = db.Column(db.DateTime(timezone=True))

    def mark_success(self, destination_id: str) -> None:
        """Mark this item as successfully migrated."""
        self.status = "success"
        self.destination_id = destination_id
        self.processed_at = datetime.now(timezone.utc)
        db.session.add(self)

    def mark_failed(self, error_message: str, error_code: str = None) -> None:
        """Mark this item as failed with error details."""
        self.status = "failed"
        self.error_message = error_message
        self.error_code = error_code
        self.processed_at = datetime.now(timezone.utc)
        db.session.add(self)

    def mark_skipped(self, reason: str) -> None:
        """Mark this item as skipped (e.g., already exists in QBO)."""
        self.status = "skipped"
        self.error_message = reason
        self.processed_at = datetime.now(timezone.utc)
        db.session.add(self)

    def mark_retrying(self) -> None:
        """Increment retry count and set status to retrying."""
        self.retry_count += 1
        self.status = "retrying"
        db.session.add(self)

    def to_dict(self) -> dict:
        """Serialize for API response."""
        return {
            "id": self.id,
            "migration_id": self.migration_id,
            "entity_type": self.entity_type,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "destination_id": self.destination_id,
            "status": self.status,
            "error_message": self.error_message,
            "error_code": self.error_code,
            "retry_count": self.retry_count,
            "batch_id": self.batch_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }

    @staticmethod
    def get_summary(migration_id: str) -> dict:
        """Get entity counts by type and status for a migration."""
        from sqlalchemy import func

        rows = (
            db.session.query(
                MigrationItem.entity_type,
                MigrationItem.status,
                func.count(MigrationItem.id),
            )
            .filter_by(migration_id=migration_id)
            .group_by(MigrationItem.entity_type, MigrationItem.status)
            .all()
        )

        summary = {}
        for entity_type, status, count in rows:
            if entity_type not in summary:
                summary[entity_type] = {"total": 0, "success": 0, "failed": 0, "skipped": 0, "pending": 0}
            summary[entity_type][status] = summary[entity_type].get(status, 0) + count
            summary[entity_type]["total"] += count

        return summary
