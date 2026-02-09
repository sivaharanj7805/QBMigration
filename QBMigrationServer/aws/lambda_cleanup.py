"""
AWS Lambda Function: QB Migration Cleanup
Triggered by CloudWatch Events every 15 minutes
Cleans up orphaned EC2 instances and S3 files
"""

import logging
import os
from datetime import datetime, timedelta, timezone

import boto3

# Initialize AWS clients
ec2 = boto3.client("ec2")
s3 = boto3.client("s3")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuration
S3_BUCKET = os.environ.get("S3_BUCKET", "qb-migration-temp-files")
ORPHANED_TIMEOUT_HOURS = int(os.environ.get("ORPHANED_TIMEOUT_HOURS", "6"))
S3_FILE_TTL_HOURS = int(os.environ.get("S3_FILE_TTL_HOURS", "24"))


def lambda_handler(event, context):
    """
    Lambda entry point

    Args:
        event: CloudWatch event
        context: Lambda context

    Returns:
        dict: Execution results
    """

    logger.info("Starting QB Migration cleanup check...")

    results = {"instances_terminated": 0, "s3_files_deleted": 0, "errors": []}

    try:
        # Cleanup orphaned EC2 instances
        instances_terminated = cleanup_orphaned_instances()
        results["instances_terminated"] = instances_terminated

        # Cleanup old S3 files
        files_deleted = cleanup_old_s3_files()
        results["s3_files_deleted"] = files_deleted

        logger.info(f"Cleanup completed: {results}")

        return {"statusCode": 200, "body": results}

    except Exception as e:
        logger.exception(f"Cleanup failed: {str(e)}")
        results["errors"].append(str(e))

        return {"statusCode": 500, "body": results}


def cleanup_orphaned_instances():
    """
    Find and terminate orphaned QB migration EC2 instances

    Returns:
        int: Number of instances terminated
    """

    terminated_count = 0

    try:
        # Find all QB migration instances
        response = ec2.describe_instances(
            Filters=[
                {"Name": "tag:Purpose", "Values": ["ephemeral-migration"]},
                {"Name": "tag:AutoTerminate", "Values": ["true"]},
                {"Name": "instance-state-name", "Values": ["running", "pending"]},
            ]
        )

        cutoff_time = datetime.now(timezone.utc) - timedelta(
            hours=ORPHANED_TIMEOUT_HOURS
        )

        for reservation in response["Reservations"]:
            for instance in reservation["Instances"]:
                instance_id = instance["InstanceId"]
                # CRIT-02 FIX: Keep timezone-aware datetime from AWS
                launch_time = instance["LaunchTime"]

                # Check if instance is too old
                if launch_time < cutoff_time:
                    logger.info(
                        f"Terminating orphaned instance: {instance_id}"
                        f" (running for"
                        f" {(datetime.now(timezone.utc) - launch_time).total_seconds() / 3600:.1f}"
                        f" hours)"
                    )

                    try:
                        ec2.terminate_instances(InstanceIds=[instance_id])
                        terminated_count += 1
                    except Exception as e:
                        logger.error(f"Failed to terminate {instance_id}: {str(e)}")

        logger.info(f"Terminated {terminated_count} orphaned instances")
        return terminated_count

    except Exception as e:
        logger.exception(f"Failed to cleanup orphaned instances: {str(e)}")
        return terminated_count


def cleanup_old_s3_files():
    """
    Delete S3 files older than TTL

    Returns:
        int: Number of files deleted
    """

    deleted_count = 0

    try:
        # List all objects in migrations folder
        paginator = s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=S3_BUCKET, Prefix="migrations/")

        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=S3_FILE_TTL_HOURS)

        for page in pages:
            if "Contents" not in page:
                continue

            for obj in page["Contents"]:
                key = obj["Key"]
                # CRIT-02 FIX: Keep timezone-aware datetime from AWS
                last_modified = obj["LastModified"]

                # Check if file is too old
                if last_modified < cutoff_time:
                    logger.info(
                        f"Deleting old S3 file: {key}"
                        f" (age: {(datetime.now(timezone.utc) - last_modified).total_seconds() / 3600:.1f}"
                        f" hours)"
                    )

                    try:
                        s3.delete_object(Bucket=S3_BUCKET, Key=key)
                        deleted_count += 1
                    except Exception as e:
                        logger.error(f"Failed to delete {key}: {str(e)}")

        logger.info(f"Deleted {deleted_count} old S3 files")
        return deleted_count

    except Exception as e:
        logger.exception(f"Failed to cleanup old S3 files: {str(e)}")
        return deleted_count
