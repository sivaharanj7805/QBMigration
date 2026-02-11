"""
DeadLetterWebhook Model — Durable dead letter queue for failed webhooks.

AUDIT FIX MUST-06: Previously, failed webhooks were only logged with a
DEAD_LETTER: prefix in application logs. If a webhook handler crashes on a
legitimate event, the event is lost unless someone greps logs. This model
provides a queryable, replayable dead letter queue backed by PostgreSQL.
"""

import logging
from datetime import datetime, timezone

from models.database import db

logger = logging.getLogger(__name__)


class DeadLetterWebhook(db.Model):
    """Stores failed webhook events for manual review and replay."""

    __tablename__ = "dead_letter_webhooks"

    __table_args__ = (
        db.Index("idx_dlq_status", "status"),
        db.Index("idx_dlq_source_created", "source", "created_at"),
        db.Index("idx_dlq_migration", "migration_id"),
    )

    id = db.Column(db.Integer, primary_key=True)

    # Source identification
    source = db.Column(db.String(50), nullable=False)  # "stripe", "migration", "qbo"
    event_type = db.Column(
        db.String(100), nullable=False
    )  # e.g., "checkout.session.completed"
    event_id = db.Column(db.String(200))  # External event ID for dedup

    # Linked migration (if applicable)
    migration_id = db.Column(db.String(36), index=True)

    # Payload (stored for replay)
    payload = db.Column(
        db.Text, nullable=False
    )  # JSON string of the original webhook body
    headers = db.Column(db.Text)  # JSON string of relevant headers

    # Error details
    error_message = db.Column(db.Text, nullable=False)
    error_traceback = db.Column(db.Text)

    # Processing status
    status = db.Column(
        db.String(20), nullable=False, default="failed"
    )  # failed | replayed | resolved | ignored

    # Retry tracking
    retry_count = db.Column(db.Integer, default=0, nullable=False)
    last_retry_at = db.Column(db.DateTime(timezone=True))
    resolved_by = db.Column(db.String(100))  # Admin user who resolved it
    resolved_at = db.Column(db.DateTime(timezone=True))

    # Timestamps
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    @classmethod
    def enqueue(
        cls,
        source: str,
        event_type: str,
        payload: str,
        error_message: str,
        event_id: str = None,
        migration_id: str = None,
        headers: str = None,
        error_traceback: str = None,
    ) -> "DeadLetterWebhook":
        """Add a failed webhook event to the dead letter queue."""
        entry = cls(
            source=source,
            event_type=event_type,
            event_id=event_id,
            migration_id=migration_id,
            payload=payload,
            headers=headers,
            error_message=str(error_message)[:2000],
            error_traceback=str(error_traceback)[:5000] if error_traceback else None,
            status="failed",
        )
        db.session.add(entry)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.error(
                f"Failed to enqueue dead letter: source={source} event_type={event_type}"
            )
        return entry

    def mark_resolved(self, resolved_by: str = "system") -> None:
        """Mark this DLQ entry as resolved."""
        self.status = "resolved"
        self.resolved_by = resolved_by
        self.resolved_at = datetime.now(timezone.utc)
        db.session.add(self)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "event_type": self.event_type,
            "event_id": self.event_id,
            "migration_id": self.migration_id,
            "error_message": self.error_message,
            "status": self.status,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_by": self.resolved_by,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }
