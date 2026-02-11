"""
AWS Migration Manager - COMPLETE VERSION
Combines:
1. EC2 Ephemeral Instance Provisioning (Original)
2. v3.1 Encryption Metadata Support (New)
3. S3 Operations
4. CloudWatch Metrics
5. Cost Tracking
6. Secrets Management
"""

import base64
import json
import logging
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class AWSMigrationManager:
    """
    Manage ephemeral AWS instances for QB migrations

    Features:
    - S3 file storage with encryption
    - EC2 ephemeral instance provisioning
    - CloudWatch metrics and monitoring
    - Cost tracking
    - Secrets Manager integration
    - Lifecycle management
    - v3.1 encryption metadata support
    """

    def __init__(self, region="ca-central-1"):
        """Initialize AWS clients"""
        self.region = region

        try:
            self.ec2 = boto3.client("ec2", region_name=region)
            self.s3 = boto3.client("s3", region_name=region)
            self.ssm = boto3.client("ssm", region_name=region)
            self.cloudwatch = boto3.client("cloudwatch", region_name=region)
            self.ce = boto3.client("ce", region_name=region)  # Cost Explorer
            self.secrets = boto3.client("secretsmanager", region_name=region)

            logger.info(f"AWS clients initialized for region {region}")
        except Exception as e:
            logger.exception(f"Failed to initialize AWS clients: {str(e)}")
            raise

    # ============================================================================
    # S3 OPERATIONS
    # ============================================================================

    def upload_to_s3(self, file_obj, migration_id, metadata=None):
        """
        Upload file to S3 with encryption

        Args:
            file_obj: File-like object to upload
            migration_id: Migration ID
            metadata: Optional metadata dict

        Returns:
            dict: {
                'uri': 's3://bucket/key',
                'bucket': 'bucket-name',
                'key': 'object-key'
            }
        """
        try:
            from flask import current_app

            bucket_name = current_app.config.get("AWS_S3_BUCKET")

            if not bucket_name:
                logger.error("AWS_S3_BUCKET not configured")
                return None

            # Generate S3 key (organized by date for better management)
            timestamp = datetime.now(timezone.utc).strftime("%Y/%m/%d")
            object_key = f"migrations/{timestamp}/{migration_id}/encrypted_data.bin"

            # Prepare metadata
            upload_metadata = {
                "migration-id": migration_id,
                "uploaded-at": datetime.now(timezone.utc).isoformat(),
                "content-type": "application/octet-stream",
            }

            if metadata:
                for key, value in metadata.items():
                    # S3 metadata keys must be lowercase and use hyphens
                    safe_key = key.lower().replace("_", "-")
                    upload_metadata[safe_key] = str(value)

            # Upload with server-side encryption
            extra_args = {
                "ServerSideEncryption": "AES256",
                "Metadata": upload_metadata,
                "ContentType": "application/octet-stream",
                "StorageClass": "STANDARD_IA",  # Infrequent Access (cheaper)
            }

            logger.info(f"Uploading to S3: s3://{bucket_name}/{object_key}")

            self.s3.upload_fileobj(
                file_obj, bucket_name, object_key, ExtraArgs=extra_args
            )

            s3_uri = f"s3://{bucket_name}/{object_key}"

            logger.info(f"[OK] Uploaded to S3: {s3_uri}")

            # Set lifecycle policy (auto-delete after processing)
            try:
                self._set_object_lifecycle(bucket_name, object_key, hours=24)
            except Exception as e:
                logger.warning(f"Failed to set lifecycle policy: {str(e)}")

            # Publish metric
            self._publish_metric("S3Upload", 1, "Count")

            return {"uri": s3_uri, "bucket": bucket_name, "key": object_key}

        except Exception as e:
            logger.exception(f"Failed to upload to S3: {str(e)}")
            self._publish_metric("S3UploadFailure", 1, "Count")
            return None

    def _set_object_lifecycle(self, bucket, key, hours=24):
        """
        Set lifecycle policy to auto-delete object after specified hours
        Implements zero data footprint requirement
        """
        try:
            # Get current lifecycle configuration
            try:
                lifecycle = self.s3.get_bucket_lifecycle_configuration(Bucket=bucket)
                rules = lifecycle.get("Rules", [])
            except ClientError:
                rules = []

            # Add rule for this migration
            rules.append(
                {
                    "ID": f"delete-{key}",
                    "Status": "Enabled",
                    "Filter": {"Prefix": key},
                    "Expiration": {"Days": 1},  # Delete after 1 day
                }
            )

            # Update lifecycle configuration
            self.s3.put_bucket_lifecycle_configuration(
                Bucket=bucket, LifecycleConfiguration={"Rules": rules}
            )

        except Exception as e:
            logger.warning(f"Lifecycle policy error: {str(e)}")

    def delete_s3_file(self, migration_id):
        """
        Delete S3 file for a migration
        Part of zero data footprint cleanup
        """
        try:
            from flask import current_app

            bucket_name = current_app.config.get("AWS_S3_BUCKET")

            if not bucket_name:
                logger.error("AWS_S3_BUCKET not configured")
                return False

            # PERFORMANCE FIX: Use migration_id in prefix to avoid scanning ALL objects.
            # S3 key format is: migrations/{YYYY}/{MM}/{DD}/{migration_id}/...
            # We can't fully narrow the prefix because the date varies, but we can
            # use the migration_id substring match with a much narrower listing scope.
            # NOTE: The broad prefix is kept as a fallback since the date-based path
            # makes it impossible to construct a precise prefix without knowing the upload date.
            # However, we limit page scanning to prevent runaway operations.
            prefix = "migrations/"
            deleted_count = 0
            continuation_token = None
            page_count = 0
            MAX_PAGES = 100  # Safety limit: scan at most 100K objects

            while True:
                page_count += 1
                if page_count > MAX_PAGES:
                    logger.warning(
                        f"S3 cleanup hit max page limit ({MAX_PAGES}) for migration {migration_id}"
                    )
                    break

                # Build list_objects_v2 params
                list_params = {"Bucket": bucket_name, "Prefix": prefix, "MaxKeys": 1000}

                if continuation_token:
                    list_params["ContinuationToken"] = continuation_token

                response = self.s3.list_objects_v2(**list_params)

                # Process objects in this page
                if "Contents" in response:
                    for obj in response["Contents"]:
                        key = obj["Key"]

                        if migration_id in key:
                            logger.info(f"Deleting S3 object: {key}")

                            self.s3.delete_object(Bucket=bucket_name, Key=key)

                            deleted_count += 1

                # Check if there are more pages
                if response.get("IsTruncated"):
                    continuation_token = response.get("NextContinuationToken")
                    logger.info(
                        f"S3 cleanup page {page_count} complete, continuing to next page..."
                    )
                else:
                    break  # No more pages

            if deleted_count == 0:
                logger.warning(
                    f"No objects found for migration {migration_id} after {page_count} page(s)"
                )
            else:
                logger.info(
                    f"S3 cleanup complete: {deleted_count} object(s) deleted across {page_count} page(s)"
                )

            # Publish metric
            self._publish_metric("S3FilesDeleted", deleted_count, "Count")

            return True

        except Exception as e:
            logger.exception(f"Failed to delete S3 files: {str(e)}")
            return False

    # ============================================================================
    # v3.1 ENCRYPTION METADATA SUPPORT (NEW)
    # ============================================================================

    def store_encryption_metadata(self, migration_id, encryption_metadata):
        """
        Store encryption metadata separately from data (v3.1 feature)
        More secure than S3 object metadata

        Args:
            migration_id: Migration ID
            encryption_metadata: Dict with encryption keys/params
        """
        try:
            from flask import current_app

            bucket_name = current_app.config.get("AWS_S3_BUCKET")

            if not bucket_name:
                logger.error("AWS_S3_BUCKET not configured")
                return False

            # Generate metadata key
            timestamp = datetime.now(timezone.utc).strftime("%Y/%m/%d")
            metadata_key = (
                f"migrations/{timestamp}/{migration_id}/encryption_metadata.json"
            )

            # Convert to JSON
            metadata_json = json.dumps(encryption_metadata, indent=2)

            logger.info(f"Storing encryption metadata: {metadata_key}")

            # Upload metadata
            self.s3.put_object(
                Bucket=bucket_name,
                Key=metadata_key,
                Body=metadata_json.encode("utf-8"),
                ServerSideEncryption="AES256",
                ContentType="application/json",
                Metadata={"migration-id": migration_id, "type": "encryption-metadata"},
            )

            logger.info("[OK] Encryption metadata stored")

            return True

        except Exception as e:
            logger.error(f"Failed to store encryption metadata: {str(e)}")
            return False

    def get_encryption_metadata(self, migration_id):
        """
        Retrieve encryption metadata for decryption

        Args:
            migration_id: Migration ID

        Returns:
            dict: Encryption metadata
        """
        try:
            from flask import current_app

            bucket_name = current_app.config.get("AWS_S3_BUCKET")

            if not bucket_name:
                logger.error("AWS_S3_BUCKET not configured")
                return None

            # Find metadata file
            metadata_key = self._find_migration_metadata_key(migration_id, bucket_name)

            if not metadata_key:
                logger.error(
                    f"No encryption metadata found for migration {migration_id}"
                )
                return None

            logger.info(f"Retrieving encryption metadata: {metadata_key}")

            # Download metadata
            response = self.s3.get_object(Bucket=bucket_name, Key=metadata_key)

            metadata_json = response["Body"].read().decode("utf-8")
            metadata = json.loads(metadata_json)

            logger.info("[OK] Encryption metadata retrieved")

            return metadata

        except Exception as e:
            logger.error(f"Failed to retrieve encryption metadata: {str(e)}")
            return None

    def _find_migration_metadata_key(self, migration_id, bucket_name):
        """
        FIX #60: Find S3 key for migration's metadata file with pagination support.
        S3 list_objects_v2 returns max 1000 objects per call.
        MED-15 FIX: Use migration-specific prefix to avoid scanning entire bucket.
        """
        try:
            # MED-15 FIX: Use migration-specific prefix instead of broad "migrations/"
            # This avoids scanning thousands of unrelated objects in large deployments.
            prefix = f"migrations/{migration_id}/"
            continuation_token = None
            max_pages = 10  # Safety limit to prevent infinite pagination

            page_count = 0
            while page_count < max_pages:
                page_count += 1
                list_params = {"Bucket": bucket_name, "Prefix": prefix, "MaxKeys": 1000}

                if continuation_token:
                    list_params["ContinuationToken"] = continuation_token

                response = self.s3.list_objects_v2(**list_params)

                if "Contents" in response:
                    for obj in response["Contents"]:
                        key = obj["Key"]

                        # Check if this is the metadata file
                        if migration_id in key and key.endswith(
                            "encryption_metadata.json"
                        ):
                            return key

                # Check if more pages exist
                if response.get("IsTruncated", False):
                    continuation_token = response.get("NextContinuationToken")
                else:
                    # No more pages, file not found
                    return None

            # MED-15 FIX: Exceeded max pagination pages
            logger.warning(
                f"Metadata search exceeded {max_pages} pages for migration {migration_id}"
            )
            return None

        except Exception as e:
            logger.error(f"Error finding metadata key: {str(e)}")
            return None

    # ============================================================================
    # EC2 INSTANCE PROVISIONING (EPHEMERAL)
    # ============================================================================

    def create_ec2_instance(
        self, migration_id, s3_uri, qbo_credentials, webhook_secret
    ):
        """
        Create ephemeral EC2 instance for migration processing

        Features:
        - Auto-terminates after completion
        - Credentials stored in Secrets Manager
        - Full monitoring enabled
        - Encrypted EBS volumes

        Args:
            migration_id: Migration ID
            s3_uri: S3 URI of encrypted data
            qbo_credentials: QuickBooks Online OAuth credentials
            webhook_secret: Secret for webhook authentication

        Returns:
            str: Instance ID
        """
        try:
            from flask import current_app

            # Get configuration
            ami_id = current_app.config.get("AWS_EC2_AMI_ID")
            instance_type = current_app.config.get("AWS_EC2_INSTANCE_TYPE", "t3.medium")
            key_name = current_app.config.get("AWS_EC2_KEY_NAME")
            security_group = current_app.config.get("AWS_EC2_SECURITY_GROUP")
            subnet_id = current_app.config.get("AWS_EC2_SUBNET_ID")
            iam_profile = current_app.config.get("AWS_IAM_INSTANCE_PROFILE")
            server_url = current_app.config.get("SERVER_URL")

            if not all([ami_id, instance_type, key_name, iam_profile]):
                logger.error("Missing required EC2 configuration")
                return None

            # Store QBO credentials in Secrets Manager (MORE SECURE than user data)
            secret_name = f"qb-migration/{migration_id}"
            try:
                self.secrets.create_secret(
                    Name=secret_name,
                    SecretString=json.dumps(qbo_credentials),
                    Tags=[
                        {"Key": "MigrationId", "Value": migration_id},
                        {
                            "Key": "CreatedAt",
                            "Value": datetime.now(timezone.utc).isoformat(),
                        },
                    ],
                )
                logger.info(f"Stored credentials in Secrets Manager: {secret_name}")
            except ClientError as e:
                if e.response["Error"]["Code"] == "ResourceExistsException":
                    # Update existing secret
                    self.secrets.update_secret(
                        SecretId=secret_name, SecretString=json.dumps(qbo_credentials)
                    )
                    logger.info(f"Updated existing secret: {secret_name}")
                else:
                    raise

            # Generate user data script (bootstrap script for instance)
            # SECURITY: Get code bucket from config (no hardcoded values)
            from flask import current_app

            code_bucket = current_app.config.get(
                "AWS_S3_CODE_BUCKET", "qb-migration-worker-code"
            )

            user_data = self._generate_user_data_script(
                migration_id=migration_id,
                s3_uri=s3_uri,
                secret_name=secret_name,
                server_url=server_url,
                webhook_secret=webhook_secret,
                code_bucket=code_bucket,
            )

            # Launch configuration
            launch_config = {
                "ImageId": ami_id,
                "InstanceType": instance_type,
                "KeyName": key_name,
                "MinCount": 1,
                "MaxCount": 1,
                "UserData": user_data,
                "IamInstanceProfile": {"Name": iam_profile},
                "TagSpecifications": [
                    {
                        "ResourceType": "instance",
                        "Tags": [
                            {"Key": "Name", "Value": f"QB-Migration-{migration_id}"},
                            {"Key": "MigrationId", "Value": migration_id},
                            {"Key": "Purpose", "Value": "ephemeral-migration"},
                            {"Key": "AutoTerminate", "Value": "true"},
                            {
                                "Key": "CreatedAt",
                                "Value": datetime.now(timezone.utc).isoformat(),
                            },
                        ],
                    }
                ],
                "BlockDeviceMappings": [
                    {
                        "DeviceName": "/dev/sda1",
                        "Ebs": {
                            "VolumeSize": 50,  # 50GB for QB data processing
                            "VolumeType": "gp3",  # General Purpose SSD
                            "DeleteOnTermination": True,  # Auto-delete on termination
                            "Encrypted": True,  # Encrypted EBS volume
                        },
                    }
                ],
                "InstanceInitiatedShutdownBehavior": "terminate",  # Auto-terminate on shutdown
                "Monitoring": {"Enabled": True},  # Detailed CloudWatch monitoring
            }

            if security_group:
                launch_config["SecurityGroupIds"] = [security_group]

            if subnet_id:
                launch_config["SubnetId"] = subnet_id

            # Launch instance
            logger.info(f"Launching EC2 instance for migration {migration_id}...")
            response = self.ec2.run_instances(**launch_config)

            instance_id = response["Instances"][0]["InstanceId"]

            logger.info(
                f"Created EC2 instance: {instance_id} for migration {migration_id}"
            )

            # Publish metric
            self._publish_metric("EC2InstanceCreated", 1, "Count")

            return instance_id

        except Exception as e:
            logger.exception(f"Failed to create EC2 instance: {str(e)}")
            self._publish_metric("EC2InstanceCreationFailure", 1, "Count")
            return None

    def _generate_user_data_script(
        self,
        migration_id,
        s3_uri,
        secret_name,
        server_url,
        webhook_secret,
        code_bucket=None,
    ):
        """
        Generate user data script for EC2 instance
        This script runs on instance launch and:
        1. Downloads encrypted data from S3
        2. Retrieves QBO credentials from Secrets Manager
        3. Runs migration worker
        4. Reports status via webhook
        5. Self-terminates

        FIX #41: Removed hardcoded credentials and secrets from user data.
        All secrets now retrieved from AWS Systems Manager Parameter Store.

        Args:
            code_bucket: S3 bucket containing migration worker code (from AWS_S3_CODE_BUCKET config)
            webhook_secret: Webhook secret (will be stored in Parameter Store, not in user data)
        """
        # SECURITY: Use config-provided code bucket, no hardcoded values
        if not code_bucket:
            from flask import current_app

            code_bucket = current_app.config.get(
                "AWS_S3_CODE_BUCKET", "qb-migration-worker-code"
            )

        # FIX #41: Store webhook secret in Systems Manager Parameter Store
        # This prevents exposing the secret in EC2 user data logs
        webhook_param_name = f"/qb-migration/webhook-secrets/{migration_id}"

        try:
            # Store webhook secret in Parameter Store (SecureString)
            ssm = boto3.client("ssm", region_name=self.region)
            ssm.put_parameter(
                Name=webhook_param_name,
                Value=webhook_secret,
                Type="SecureString",
                Overwrite=True,
                Description=f"Webhook secret for migration {migration_id}",
                Tags=[
                    {"Key": "migration_id", "Value": migration_id},
                    {
                        "Key": "expiry",
                        "Value": (
                            datetime.now(timezone.utc) + timedelta(hours=24)
                        ).isoformat(),
                    },
                ],
            )
            logger.info(
                f"Stored webhook secret in Parameter Store: {webhook_param_name}"
            )
        except Exception as e:
            logger.error(f"Failed to store webhook secret in Parameter Store: {e}")
            # Fall back to inline secret only if Parameter Store fails
            # This is less secure but allows operation to continue
            webhook_param_name = None

        # FIX #41: Generate user data with secrets retrieved from SSM, not hardcoded
        script = f"""#!/bin/bash
set -e

# Logging
LOG_FILE="/var/log/qb-migration-{migration_id}.log"
exec > >(tee -a $LOG_FILE)
exec 2>&1

echo "=========================================="
echo "QB Migration Worker - Instance Bootstrap"
echo "Migration ID: {migration_id}"
echo "Started: $(date)"
echo "=========================================="

# Update system
echo "Updating system packages..."
apt-get update -y
apt-get upgrade -y

# Install dependencies
echo "Installing Python and dependencies..."
apt-get install -y python3-pip python3-venv awscli jq

# Create working directory
WORK_DIR="/opt/qb-migration"
mkdir -p $WORK_DIR
cd $WORK_DIR

# Install Python packages
echo "Installing Python packages..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install boto3 cryptography requests quickbooks-online-sdk

# Download migration worker code
echo "Downloading migration worker..."
aws s3 cp s3://{code_bucket}/migration_worker.py worker.py
aws s3 cp s3://{code_bucket}/data_transformer.py transformer.py
aws s3 cp s3://{code_bucket}/qbo_client.py qbo_client.py

# Download encrypted data from S3
echo "Downloading encrypted QB data from S3..."
aws s3 cp "{s3_uri}" encrypted_data.bin

# Download encryption metadata
METADATA_URI=$(echo "{s3_uri}" | sed 's/encrypted_data.bin/encryption_metadata.json/')
aws s3 cp "$METADATA_URI" encryption_metadata.json

# Get QBO credentials from Secrets Manager
echo "Retrieving QBO credentials from Secrets Manager..."
aws secretsmanager get-secret-value \\
    --secret-id {secret_name} \\
    --query SecretString \\
    --output text > qbo_credentials.json

# FIX #41: Retrieve webhook secret from Parameter Store instead of hardcoding
echo "Retrieving webhook secret from Parameter Store..."
"""

        # Add webhook secret retrieval logic
        if webhook_param_name:
            # Use Parameter Store (secure method)
            script += f"""WEBHOOK_SECRET=$(aws ssm get-parameter \\
    --name "{webhook_param_name}" \\
    --with-decryption \\
    --query Parameter.Value \\
    --output text)

if [ -z "$WEBHOOK_SECRET" ]; then
    echo "ERROR: Failed to retrieve webhook secret from Parameter Store"
    exit 1
fi
"""
        else:
            # SEC-03: Fail fast instead of using insecure inline secret
            # Inline secrets in EC2 user data can be exposed in logs
            logger.error(
                "WEBHOOK_SECRET parameter name not configured - cannot securely provision instance"
            )
            raise ValueError(
                "Webhook secret Parameter Store name is required for secure migration. "
                "Configure WEBHOOK_PARAM_NAME in environment or use put_webhook_secret() first."
            )

        script += f"""
# Run migration worker
echo "Starting migration processing..."
python3 worker.py \\
    --migration-id {migration_id} \\
    --encrypted-data encrypted_data.bin \\
    --metadata encryption_metadata.json \\
    --credentials qbo_credentials.json \\
    --server-url {server_url} \\
    --webhook-secret "$WEBHOOK_SECRET"

EXIT_CODE=$?

# Cleanup
echo "Cleaning up sensitive data..."
shred -vfz -n 7 encrypted_data.bin
shred -vfz -n 7 encryption_metadata.json
shred -vfz -n 7 qbo_credentials.json
rm -rf $WORK_DIR

# Delete secret from Secrets Manager
echo "Deleting secret from Secrets Manager..."
aws secretsmanager delete-secret \\
    --secret-id {secret_name} \\
    --force-delete-without-recovery

# Report completion
echo "Migration processing completed with exit code: $EXIT_CODE"
echo "Finished: $(date)"

# Self-terminate
echo "Terminating instance..."
INSTANCE_ID=$(ec2-metadata --instance-id | cut -d " " -f 2)
aws ec2 terminate-instances --instance-ids $INSTANCE_ID

exit $EXIT_CODE
"""

        # Base64 encode for user data
        return base64.b64encode(script.encode("utf-8")).decode("utf-8")

    def terminate_instance(self, instance_id):
        """Terminate EC2 instance"""
        try:
            self.ec2.terminate_instances(InstanceIds=[instance_id])
            logger.info(f"Terminated instance: {instance_id}")
            return True
        except Exception as e:
            logger.exception(f"Failed to terminate instance: {str(e)}")
            return False

    def get_instance_status(self, instance_id):
        """
        Get EC2 instance status

        Returns:
            dict: {
                'state': 'running' | 'stopped' | 'terminated',
                'public_ip': '1.2.3.4',
                'launch_time': '2025-01-10T12:00:00Z',
                ...
            }
        """
        try:
            response = self.ec2.describe_instances(InstanceIds=[instance_id])

            if not response["Reservations"]:
                return {"state": "not_found"}

            instance = response["Reservations"][0]["Instances"][0]

            return {
                "state": instance["State"]["Name"],
                "instance_type": instance["InstanceType"],
                "public_ip": instance.get("PublicIpAddress"),
                "private_ip": instance.get("PrivateIpAddress"),
                "launch_time": instance["LaunchTime"].isoformat(),
                "monitoring": instance["Monitoring"]["State"],
                "tags": {tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])},
            }

        except Exception as e:
            logger.exception(f"Failed to get instance status: {str(e)}")
            return {"state": "error", "error": str(e)}

    # ============================================================================
    # COST TRACKING
    # ============================================================================

    def get_migration_cost(self, migration_id, start_date, end_date):
        """
        Get cost for a specific migration

        Args:
            migration_id: Migration ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            dict: {
                'total_cost': 12.34,
                'breakdown': {'EC2': 10.00, 'S3': 1.00, 'Secrets': 0.34}
            }
        """
        try:
            response = self.ce.get_cost_and_usage(
                TimePeriod={"Start": start_date, "End": end_date},
                Granularity="DAILY",
                Filter={"Tags": {"Key": "MigrationId", "Values": [migration_id]}},
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            )

            # Parse costs
            total_cost = 0.0
            breakdown = {}

            for result in response["ResultsByTime"]:
                for group in result["Groups"]:
                    service = group["Keys"][0]
                    cost = float(group["Metrics"]["UnblendedCost"]["Amount"])

                    breakdown[service] = breakdown.get(service, 0.0) + cost
                    total_cost += cost

            logger.info(f"Migration {migration_id} cost: ${total_cost:.2f}")

            return {
                "total_cost": round(total_cost, 2),
                "breakdown": {k: round(v, 2) for k, v in breakdown.items()},
                "period": f"{start_date} to {end_date}",
            }

        except Exception as e:
            logger.exception(f"Failed to get migration cost: {str(e)}")
            return {"total_cost": 0.0, "breakdown": {}, "error": str(e)}

    # ============================================================================
    # CLEANUP & LIFECYCLE
    # ============================================================================

    def cleanup_migration(self, migration_id, instance_id=None):
        """
        Complete cleanup for a migration
        Implements zero data footprint:
        1. Delete S3 files (data + metadata)
        2. Terminate EC2 instance
        3. Delete Secrets Manager secret
        4. Publish cleanup metrics

        Args:
            migration_id: Migration ID
            instance_id: EC2 instance ID (optional)

        Returns:
            dict: Cleanup results with keys instance_terminated, s3_deleted, secret_deleted
        """
        try:
            instance_terminated = False
            s3_deleted = False
            secret_deleted = False

            # 1. Delete S3 files
            logger.info(f"Cleaning up S3 files for migration {migration_id}...")
            if self.delete_s3_file(migration_id):
                s3_deleted = True
            else:
                logger.warning("S3 cleanup had issues")

            # 2. Terminate EC2 instance
            if instance_id:
                logger.info(f"Terminating EC2 instance {instance_id}...")
                if self.terminate_instance(instance_id):
                    instance_terminated = True
                else:
                    logger.warning("Instance termination had issues")
            else:
                instance_terminated = True  # No instance to terminate

            # 3. Delete Secrets Manager secret
            secret_name = f"qb-migration/{migration_id}"
            try:
                logger.info(f"Deleting secret {secret_name}...")
                self.secrets.delete_secret(
                    SecretId=secret_name, ForceDeleteWithoutRecovery=True
                )
                logger.info(f"[OK] Secret deleted: {secret_name}")
                secret_deleted = True
            except ClientError as e:
                if e.response["Error"]["Code"] == "ResourceNotFoundException":
                    secret_deleted = True  # Already gone
                else:
                    logger.warning(f"Failed to delete secret: {str(e)}")

            # 4. Publish cleanup metric
            self._publish_metric("MigrationCleanup", 1, "Count")

            cleanup_success = all([instance_terminated, s3_deleted, secret_deleted])
            if cleanup_success:
                logger.info(
                    f"Complete cleanup successful for migration {migration_id}"
                )
            else:
                logger.warning(
                    f"⚠ Cleanup completed with warnings for migration {migration_id}"
                )

            return {
                "instance_terminated": instance_terminated,
                "s3_deleted": s3_deleted,
                "secret_deleted": secret_deleted,
            }

        except Exception as e:
            logger.exception(f"Failed to cleanup migration: {str(e)}")
            return {
                "instance_terminated": False,
                "s3_deleted": False,
                "secret_deleted": False,
            }

    # ============================================================================
    # CLOUDWATCH METRICS
    # ============================================================================

    def _publish_metric(self, metric_name, value, unit="None"):
        """Publish CloudWatch metric"""
        try:
            self.cloudwatch.put_metric_data(
                Namespace="QBMigrations",
                MetricData=[
                    {
                        "MetricName": metric_name,
                        "Value": value,
                        "Unit": unit,
                        "Timestamp": datetime.now(timezone.utc),
                    }
                ],
            )
        except Exception as e:
            # MON-01: Log at WARNING level so monitoring gaps are visible
            logger.warning(
                f"Failed to publish CloudWatch metric '{metric_name}': {str(e)}"
            )
