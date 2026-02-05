import logging
from datetime import datetime, timedelta, timezone

from models.migration import Migration
from utils.aws_manager import AWSMigrationManager

logger = logging.getLogger(__name__)


class CleanupScheduler:
    """Automatically cleanup orphaned AWS resources"""

    def __init__(self, app):
        self.app = app
        self.aws_manager = None
        self.enabled = app.config.get("AUTO_CLEANUP_ENABLED", True)

        if self.enabled:
            logger.info("Cleanup scheduler initialized")
        else:
            logger.info("Cleanup scheduler disabled by configuration")

    def run_cleanup(self):
        """Run cleanup check - called by scheduler"""

        if not self.enabled:
            return

        try:
            with self.app.app_context():
                self._initialize_aws_manager()

                logger.info("Starting cleanup check...")

                # Find migrations that need cleanup
                migrations_to_clean = self._find_migrations_needing_cleanup()

                if not migrations_to_clean:
                    logger.info("No migrations need cleanup")
                    return

                logger.info(
                    f"Found {len(migrations_to_clean)} migrations needing cleanup"
                )

                # Cleanup each migration
                for migration in migrations_to_clean:
                    self._cleanup_migration(migration)

                logger.info("Cleanup check completed")

        except Exception as e:
            logger.exception(f"Cleanup check failed: {str(e)}")

    def _initialize_aws_manager(self):
        """Initialize AWS manager if not already done"""
        if not self.aws_manager:
            region = self.app.config.get("AWS_REGION", "us-east-1")
            self.aws_manager = AWSMigrationManager(region=region)

    def _find_migrations_needing_cleanup(self):
        """
        Find migrations that need cleanup

        Returns:
            list: List of Migration objects
        """
        try:
            # Migrations that are completed/failed but not cleaned up
            completed_not_cleaned = Migration.query.filter(
                Migration.status.in_(["completed", "failed"]),
                Migration.cleanup_completed.is_(False),
            ).all()

            # Migrations that are stuck (processing > 6 hours)
            timeout_hours = self.app.config.get("ORPHANED_INSTANCE_TIMEOUT_HOURS", 6)
            stuck_cutoff = datetime.now(timezone.utc) - timedelta(hours=timeout_hours)

            stuck_migrations = Migration.query.filter(
                Migration.status == "processing",
                Migration.started_at < stuck_cutoff,
                Migration.cleanup_completed.is_(False),
            ).all()

            # Expired migrations
            expired_migrations = Migration.query.filter(
                Migration.expires_at < datetime.now(timezone.utc),
                Migration.cleanup_completed.is_(False),
            ).all()

            # Combine and deduplicate
            all_migrations = set(
                completed_not_cleaned + stuck_migrations + expired_migrations
            )

            return list(all_migrations)

        except Exception as e:
            logger.exception(f"Failed to find migrations needing cleanup: {str(e)}")
            return []

    def _cleanup_migration(self, migration):
        """
        Cleanup a specific migration

        Args:
            migration: Migration object
        """
        try:
            logger.info(
                f"Cleaning up migration {migration.migration_id} (status: {migration.status})"
            )

            # Mark as cleanup started
            migration.mark_cleanup_started()

            # Cleanup AWS resources
            cleanup_results = self.aws_manager.cleanup_migration(
                migration_id=migration.migration_id,
                instance_id=migration.aws_instance_id,
            )

            # Update migration based on results
            if cleanup_results.get("instance_terminated"):
                migration.mark_ec2_terminated()

            if cleanup_results.get("s3_deleted"):
                migration.mark_s3_deleted()

            # Mark cleanup as completed if all successful
            if all(cleanup_results.values()):
                migration.mark_cleanup_completed()
                logger.info(f"Cleanup completed for migration {migration.migration_id}")
            else:
                logger.warning(
                    f"Partial cleanup for migration {migration.migration_id}: {cleanup_results}"
                )

        except Exception as e:
            logger.exception(
                f"Failed to cleanup migration {migration.migration_id}: {str(e)}"
            )


def init_cleanup_scheduler(app):
    """
    Initialize cleanup scheduler

    Args:
        app: Flask application instance

    Returns:
        BackgroundScheduler instance or None
    """

    if not app.config.get("AUTO_CLEANUP_ENABLED", True):
        logger.info("Auto-cleanup disabled by configuration")
        return None

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        cleanup_scheduler = CleanupScheduler(app)

        # Create scheduler
        scheduler = BackgroundScheduler()

        # Schedule cleanup checks
        interval_minutes = app.config.get("CLEANUP_CHECK_INTERVAL_MINUTES", 15)

        scheduler.add_job(
            func=cleanup_scheduler.run_cleanup,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id="migration_cleanup",
            name="Migration cleanup job",
            replace_existing=True,
        )

        # Start scheduler
        scheduler.start()

        logger.info(f"Cleanup scheduler started (interval: {interval_minutes} minutes)")

        # Run initial cleanup
        cleanup_scheduler.run_cleanup()

        return scheduler

    except ImportError:
        logger.warning("APScheduler not installed, auto-cleanup disabled")
        return None
    except Exception as e:
        logger.exception(f"Failed to initialize cleanup scheduler: {str(e)}")
        return None
