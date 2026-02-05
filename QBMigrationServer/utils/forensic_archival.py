"""
Forensic Archival Service (Cold Storage Strategy)
=================================================
Implements 7-year legal retention for audit metadata using S3 Glacier.

While lambda_cleanup.py deletes actual financial data after 24 hours,
this service preserves:
- Migration metadata (what was migrated, when, by whom)
- Audit trail logs
- Verification reports

This satisfies legal retention requirements without storing sensitive data.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Canadian data residency
REQUIRED_REGION = "ca-central-1"

# Retention periods
STANDARD_RETENTION_DAYS = 90  # Active storage
GLACIER_RETENTION_YEARS = 7  # Legal retention
GLACIER_RETENTION_DAYS = 7 * 365


class ForensicArchivalService:
    """
    Manages forensic archival to S3 Glacier for legal retention.

    Key principle: Archive METADATA, not DATA
    - Migration records: who, what, when
    - Hash verification logs
    - Entity count summaries
    - Audit trail

    Does NOT archive:
    - Actual financial data
    - Customer/vendor lists
    - Transaction details
    """

    def __init__(self, s3_client=None, bucket_name: str = None):
        self.s3 = s3_client or boto3.client("s3", region_name=REQUIRED_REGION)
        self.bucket_name = bucket_name
        self.archive_prefix = "forensic-archive/"
        self.glacier_storage_class = "GLACIER_IR"  # Glacier Instant Retrieval

    def archive_migration_metadata(self, migration_id: str, metadata: dict) -> dict:
        """
        Archive migration metadata to Glacier for 7-year retention.

        Args:
            migration_id: Unique migration ID
            metadata: Migration metadata (no financial data!)
                - migration_id
                - user_id
                - company_name (sanitized)
                - entity_counts
                - file_hashes
                - timestamps
                - status
        """
        # Validate no sensitive data
        sanitized = self._sanitize_metadata(metadata)

        # Create archive record
        archive_record = {
            "migration_id": migration_id,
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "retention_until": (
                datetime.now(timezone.utc) + timedelta(days=GLACIER_RETENTION_DAYS)
            ).isoformat(),
            "retention_years": GLACIER_RETENTION_YEARS,
            "metadata": sanitized,
        }

        key = f"{self.archive_prefix}migrations/{migration_id}/metadata.json"
        body = json.dumps(archive_record, indent=2, default=str).encode("utf-8")

        try:
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=body,
                StorageClass=self.glacier_storage_class,
                ContentType="application/json",
                Metadata={
                    "retention-years": str(GLACIER_RETENTION_YEARS),
                    "archive-type": "migration-metadata",
                },
            )

            logger.info(f"Archived metadata for migration {migration_id} to Glacier")

            return {
                "success": True,
                "migration_id": migration_id,
                "archive_key": key,
                "storage_class": self.glacier_storage_class,
                "retention_until": archive_record["retention_until"],
            }

        except ClientError as e:
            logger.error(f"Failed to archive metadata: {str(e)}")
            return {"error": str(e)}

    def archive_audit_log(self, migration_id: str, audit_entries: List[dict]) -> dict:
        """
        Archive audit trail entries to Glacier.

        Args:
            migration_id: Migration ID
            audit_entries: List of audit log entries
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        key = f"{self.archive_prefix}audit-logs/{migration_id}/{timestamp}.json"

        archive_record = {
            "migration_id": migration_id,
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "entry_count": len(audit_entries),
            "entries": audit_entries,
        }

        body = json.dumps(archive_record, indent=2, default=str).encode("utf-8")

        try:
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=body,
                StorageClass=self.glacier_storage_class,
                ContentType="application/json",
            )

            logger.info(
                f"Archived {len(audit_entries)} audit entries for {migration_id}"
            )
            return {"success": True, "archive_key": key}

        except ClientError as e:
            logger.error(f"Failed to archive audit log: {str(e)}")
            return {"error": str(e)}

    def archive_verification_report(self, migration_id: str, report: dict) -> dict:
        """
        Archive hash verification report to Glacier.
        This provides mathematical proof of data integrity.
        """
        key = f"{self.archive_prefix}verification/{migration_id}/report.json"

        archive_record = {
            "migration_id": migration_id,
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "report_type": "hash_verification",
            "report": report,
        }

        body = json.dumps(archive_record, indent=2, default=str).encode("utf-8")

        try:
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=body,
                StorageClass=self.glacier_storage_class,
                ContentType="application/json",
            )

            return {"success": True, "archive_key": key}

        except ClientError as e:
            return {"error": str(e)}

    def configure_lifecycle_rules(self) -> dict:
        """
        Configure S3 lifecycle rules for archival:
        1. Standard storage for 90 days
        2. Transition to Glacier after 90 days
        3. Never delete (legal hold)
        """
        lifecycle_config = {
            "Rules": [
                {
                    "ID": "ForensicArchive-To-Glacier",
                    "Filter": {"Prefix": self.archive_prefix},
                    "Status": "Enabled",
                    "Transitions": [
                        {"Days": STANDARD_RETENTION_DAYS, "StorageClass": "GLACIER"}
                    ],
                    # No Expiration - never delete archived data
                },
                {
                    "ID": "TempFiles-Cleanup",
                    "Filter": {"Prefix": "migrations/"},  # Active migration data
                    "Status": "Enabled",
                    "Expiration": {"Days": 1},  # Delete after 24 hours
                },
            ]
        }

        try:
            self.s3.put_bucket_lifecycle_configuration(
                Bucket=self.bucket_name, LifecycleConfiguration=lifecycle_config
            )

            logger.info(f"Configured lifecycle rules on bucket {self.bucket_name}")

            return {
                "success": True,
                "rules": [
                    {
                        "name": "ForensicArchive-To-Glacier",
                        "action": f"Transition to Glacier after {STANDARD_RETENTION_DAYS} days",
                        "prefix": self.archive_prefix,
                    },
                    {
                        "name": "TempFiles-Cleanup",
                        "action": "Delete after 1 day",
                        "prefix": "migrations/",
                    },
                ],
            }

        except ClientError as e:
            logger.error(f"Failed to configure lifecycle: {str(e)}")
            return {"error": str(e)}

    def restore_from_glacier(self, key: str, restore_days: int = 7) -> dict:
        """
        Initiate restore of an archived object from Glacier.

        Args:
            key: S3 object key
            restore_days: Number of days to keep restored copy
        """
        try:
            self.s3.restore_object(
                Bucket=self.bucket_name,
                Key=key,
                RestoreRequest={
                    "Days": restore_days,
                    "GlacierJobParameters": {
                        "Tier": "Expedited"  # 1-5 minute retrieval
                    },
                },
            )

            logger.info(f"Initiated Glacier restore for {key}")

            return {
                "success": True,
                "key": key,
                "restore_days": restore_days,
                "expected_time": "1-5 minutes (Expedited)",
                "message": "Restore initiated. Check status with get_restore_status()",
            }

        except ClientError as e:
            if "RestoreAlreadyInProgress" in str(e):
                return {"success": True, "message": "Restore already in progress"}
            return {"error": str(e)}

    def get_restore_status(self, key: str) -> dict:
        """
        Check the restore status of a Glacier object.
        """
        try:
            response = self.s3.head_object(Bucket=self.bucket_name, Key=key)

            restore_status = response.get("Restore", "")
            storage_class = response.get("StorageClass", "STANDARD")

            if 'ongoing-request="true"' in restore_status:
                return {
                    "key": key,
                    "storage_class": storage_class,
                    "restore_status": "in_progress",
                }
            elif 'ongoing-request="false"' in restore_status:
                return {
                    "key": key,
                    "storage_class": storage_class,
                    "restore_status": "completed",
                    "message": "Object is accessible",
                }
            else:
                return {
                    "key": key,
                    "storage_class": storage_class,
                    "restore_status": (
                        "not_started"
                        if storage_class in ["GLACIER", "DEEP_ARCHIVE"]
                        else "not_required"
                    ),
                }

        except ClientError as e:
            return {"error": str(e)}

    def list_archived_migrations(
        self, prefix: str = None, limit: int = 100
    ) -> List[dict]:
        """
        List archived migration metadata.
        """
        search_prefix = prefix or f"{self.archive_prefix}migrations/"

        try:
            paginator = self.s3.get_paginator("list_objects_v2")
            pages = paginator.paginate(
                Bucket=self.bucket_name, Prefix=search_prefix, MaxKeys=limit
            )

            archives = []
            for page in pages:
                for obj in page.get("Contents", []):
                    archives.append(
                        {
                            "key": obj["Key"],
                            "size_bytes": obj["Size"],
                            "last_modified": obj["LastModified"].isoformat(),
                            "storage_class": obj.get("StorageClass", "STANDARD"),
                        }
                    )
                    if len(archives) >= limit:
                        break

            return archives

        except ClientError as e:
            logger.error(f"Failed to list archives: {str(e)}")
            return []

    def _sanitize_metadata(self, metadata: dict) -> dict:
        """
        Remove any potentially sensitive fields from metadata.
        Only keep audit-relevant information.
        """
        # Fields to preserve
        safe_fields = {
            "migration_id",
            "user_id",
            "company_id",
            "company_name",
            "started_at",
            "completed_at",
            "status",
            "error_code",
            "entity_counts",
            "file_hashes",
            "total_records",
            "qbo_company_id",
            "migration_type",
            "retry_count",
            "duration_seconds",
            "aws_instance_id",
            "aws_region",
        }

        # Fields to explicitly exclude
        sensitive_fields = {
            "access_token",
            "refresh_token",
            "password",
            "secret",
            "email",
            "phone",
            "address",
            "ssn",
            "sin",
            "tax_id",
            "bank_account",
            "credit_card",
            "api_key",
        }

        sanitized = {}

        for key, value in metadata.items():
            key_lower = key.lower()

            # Skip sensitive fields
            if any(s in key_lower for s in sensitive_fields):
                continue

            # Keep safe fields
            if key in safe_fields:
                sanitized[key] = value
            # Keep simple summary fields
            elif isinstance(value, (int, float, bool, str)) and len(str(value)) < 200:
                sanitized[key] = value

        return sanitized

    def get_archive_summary(self) -> dict:
        """
        Get summary of archived data for reporting.
        """
        try:
            # Count objects in archive
            paginator = self.s3.get_paginator("list_objects_v2")

            total_objects = 0
            total_size = 0
            by_type: dict[str, int] = {}

            for page in paginator.paginate(
                Bucket=self.bucket_name, Prefix=self.archive_prefix
            ):
                for obj in page.get("Contents", []):
                    total_objects += 1
                    total_size += obj["Size"]

                    # Categorize by path
                    parts = obj["Key"].split("/")
                    if len(parts) > 1:
                        category = parts[1]
                        by_type[category] = by_type.get(category, 0) + 1

            return {
                "total_objects": total_objects,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "by_type": by_type,
                "retention_policy": f"{GLACIER_RETENTION_YEARS} years",
                "storage_class": self.glacier_storage_class,
            }

        except ClientError as e:
            return {"error": str(e)}
