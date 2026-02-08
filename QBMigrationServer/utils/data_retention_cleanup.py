"""
FIX #45: Zero-Persistence Data Retention Cleanup Utility

This utility strips sensitive PII and financial data from migrations older than 24 hours,
maintaining only metadata (hashes, counts, status) for forensic audit purposes.

Usage:
    # As a CLI command:
    python -m utils.data_retention_cleanup

    # As a scheduled cron job (run daily):
    0 2 * * * cd /path/to/QBMigrationServer && python -m utils.data_retention_cleanup

    # Programmatically:
    from utils.data_retention_cleanup import cleanup_old_migration_data
    result = cleanup_old_migration_data(retention_hours=24)
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from models import db
from models.migration import Migration

logger = logging.getLogger(__name__)


def cleanup_old_migration_data(retention_hours=24, dry_run=False):
    """
    Strip sensitive data from migrations older than retention_hours.

    Args:
        retention_hours (int): Number of hours to retain full data (default: 24)
        dry_run (bool): If True, only report what would be cleaned without making changes

    Returns:
        dict: {
            'success': bool,
            'migrations_cleaned': int,
            'errors': list,
            'dry_run': bool
        }
    """
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
    errors = []
    cleaned_count = 0

    try:
        # Find migrations older than cutoff that have sensitive data
        migrations_to_clean = Migration.query.filter(
            db.or_(
                Migration.created_at < cutoff_time, Migration.completed_at < cutoff_time
            ),
            db.or_(
                Migration.trial_balance_data.isnot(None),
                Migration.live_status_data.isnot(None),
            ),
        ).all()

        logger.info(
            f"Found {len(migrations_to_clean)} migrations older than {retention_hours}h with sensitive data"
        )

        for migration in migrations_to_clean:
            try:
                # Check if data is already stripped (parse JSON, don't substring-match)
                already_stripped = False
                for field_data in [
                    migration.trial_balance_data,
                    migration.live_status_data,
                ]:
                    if field_data:
                        try:
                            parsed = json.loads(field_data)
                            if isinstance(parsed, dict) and "stripped_at" in parsed:
                                already_stripped = True
                                break
                        except (json.JSONDecodeError, TypeError):
                            pass
                if already_stripped:
                    continue

                if dry_run:
                    logger.info(
                        f"[DRY RUN] Would strip data from migration {migration.migration_id}"
                    )
                else:
                    migration.strip_sensitive_data()
                    db.session.add(migration)
                    logger.info(
                        f"Stripped sensitive data from migration"
                        f" {migration.migration_id}"
                        f" (created: {migration.created_at})"
                    )

                cleaned_count += 1

                # Periodic commit every 100 records to avoid losing all
                # progress if a later record fails. This ensures earlier
                # successful cleanups are persisted even on partial failure.
                if not dry_run and cleaned_count % 100 == 0:
                    db.session.commit()
                    logger.info(f"Periodic commit: cleaned {cleaned_count} migrations so far")

            except Exception as e:
                error_msg = f"Failed to strip data from migration {migration.migration_id}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue

        if not dry_run:
            db.session.commit()
            logger.info(f"Successfully cleaned {cleaned_count} migrations (final commit)")
        else:
            logger.info(f"[DRY RUN] Would clean {cleaned_count} migrations")

        return {
            "success": True,
            "migrations_cleaned": cleaned_count,
            "errors": errors,
            "dry_run": dry_run,
            "cutoff_time": cutoff_time.isoformat(),
        }

    except Exception as e:
        db.session.rollback()
        error_msg = f"Fatal error during cleanup: {str(e)}"
        logger.exception(error_msg)
        return {
            "success": False,
            "migrations_cleaned": cleaned_count,
            "errors": errors + [error_msg],
            "dry_run": dry_run,
        }


def cleanup_s3_temp_files(retention_hours=24, dry_run=False):
    """
    Clean up temporary S3 files from incomplete/failed migrations older than retention_hours.

    Args:
        retention_hours (int): Number of hours to retain temp files (default: 24)
        dry_run (bool): If True, only report what would be deleted without making changes

    Returns:
        dict: {
            'success': bool,
            'files_deleted': int,
            'bytes_freed': int,
            'errors': list,
            'dry_run': bool
        }
    """
    import os

    import boto3
    from botocore.exceptions import ClientError

    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
    errors = []
    deleted_count = 0
    bytes_freed = 0

    try:
        # Get S3 bucket from environment
        bucket_name = os.getenv("S3_BUCKET_NAME")
        if not bucket_name:
            return {
                "success": False,
                "files_deleted": 0,
                "bytes_freed": 0,
                "errors": ["S3_BUCKET_NAME not configured"],
                "dry_run": dry_run,
            }

        s3 = boto3.client("s3")

        # List objects in uploads/ prefix (temporary upload location)
        paginator = s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket_name, Prefix="uploads/")

        for page in pages:
            if "Contents" not in page:
                continue

            for obj in page["Contents"]:
                # Check if object is older than cutoff
                # CRIT-02 FIX: Keep timezone-aware datetime from S3 (UTC) to
                # compare against timezone-aware cutoff_time. Stripping tzinfo
                # caused TypeError: can't compare offset-naive and offset-aware.
                if obj["LastModified"] < cutoff_time:
                    key = obj["Key"]
                    size = obj["Size"]

                    if dry_run:
                        logger.info(
                            f"[DRY RUN] Would delete S3 object: {key} ({size} bytes)"
                        )
                    else:
                        try:
                            s3.delete_object(Bucket=bucket_name, Key=key)
                            logger.info(f"Deleted S3 object: {key} ({size} bytes)")
                        except ClientError as e:
                            error_msg = f"Failed to delete {key}: {str(e)}"
                            logger.error(error_msg)
                            errors.append(error_msg)
                            continue

                    deleted_count += 1
                    bytes_freed += size

        if not dry_run:
            logger.info(
                f"Successfully deleted {deleted_count} S3 objects, freed {bytes_freed} bytes"
            )
        else:
            logger.info(
                f"[DRY RUN] Would delete {deleted_count} S3 objects, free {bytes_freed} bytes"
            )

        return {
            "success": True,
            "files_deleted": deleted_count,
            "bytes_freed": bytes_freed,
            "errors": errors,
            "dry_run": dry_run,
            "cutoff_time": cutoff_time.isoformat(),
        }

    except Exception as e:
        error_msg = f"Fatal error during S3 cleanup: {str(e)}"
        logger.exception(error_msg)
        return {
            "success": False,
            "files_deleted": deleted_count,
            "bytes_freed": bytes_freed,
            "errors": errors + [error_msg],
            "dry_run": dry_run,
        }


def run_full_cleanup(retention_hours=24, dry_run=False):
    """
    Run both database and S3 cleanup operations.

    Args:
        retention_hours (int): Number of hours to retain full data (default: 24)
        dry_run (bool): If True, only report what would be cleaned without making changes

    Returns:
        dict: Combined results from both cleanup operations
    """
    logger.info(
        f"Starting full cleanup (retention: {retention_hours}h, dry_run: {dry_run})"
    )

    db_result = cleanup_old_migration_data(
        retention_hours=retention_hours, dry_run=dry_run
    )
    s3_result = cleanup_s3_temp_files(retention_hours=retention_hours, dry_run=dry_run)

    return {
        "success": db_result["success"] and s3_result["success"],
        "database_cleanup": db_result,
        "s3_cleanup": s3_result,
        "summary": {
            "migrations_cleaned": db_result["migrations_cleaned"],
            "s3_files_deleted": s3_result["files_deleted"],
            "s3_bytes_freed": s3_result["bytes_freed"],
            "total_errors": len(db_result["errors"]) + len(s3_result["errors"]),
        },
    }


if __name__ == "__main__":
    """
    CLI entry point for running cleanup as a scheduled job.

    Environment variables:
        DATA_RETENTION_HOURS: Number of hours to retain full data (default: 24)
        DRY_RUN: Set to '1' or 'true' for dry run mode (default: false)
    """
    import os
    import sys

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("/var/log/qb-migration/cleanup.log", mode="a"),
        ],
    )

    # Read configuration from environment
    retention_hours = int(os.getenv("DATA_RETENTION_HOURS", "24"))
    dry_run = os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes")

    # Create Flask app context for database access
    from app import create_app

    app = create_app()

    with app.app_context():
        logger.info("=" * 80)
        logger.info("Zero-Persistence Cleanup Job Starting")
        logger.info(f"Retention: {retention_hours} hours | Dry Run: {dry_run}")
        logger.info("=" * 80)

        result = run_full_cleanup(retention_hours=retention_hours, dry_run=dry_run)

        logger.info("=" * 80)
        logger.info(f"Cleanup Complete - Success: {result['success']}")
        logger.info(f"Migrations Cleaned: {result['summary']['migrations_cleaned']}")
        logger.info(f"S3 Files Deleted: {result['summary']['s3_files_deleted']}")
        logger.info(f"S3 Bytes Freed: {result['summary']['s3_bytes_freed']}")
        logger.info(f"Total Errors: {result['summary']['total_errors']}")
        logger.info("=" * 80)

        # Print JSON result for programmatic consumption
        logger.info(json.dumps(result, indent=2))

        # Exit with appropriate code
        sys.exit(0 if result["success"] else 1)
