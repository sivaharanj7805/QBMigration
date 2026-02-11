"""
Tests for utils/aws_manager.py — AWSMigrationManager

Covers:
- S3 upload/delete operations with mocked boto3
- EC2 instance provisioning and lifecycle
- Encryption metadata storage/retrieval
- Cost tracking
- Cleanup orchestration
- Edge cases: missing config, boto3 failures, pagination limits
"""

import base64
import json
import os
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import MagicMock, call, patch

import pytest

# Ensure testing environment
os.environ["FLASK_ENV"] = "testing"


# ---------------------------------------------------------------------------
# Helpers to build a mock AWSMigrationManager without real AWS credentials
# ---------------------------------------------------------------------------


def _make_manager():
    """Create an AWSMigrationManager with all boto3 clients mocked."""
    with patch("utils.aws_manager.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        from utils.aws_manager import AWSMigrationManager

        mgr = AWSMigrationManager(region="us-east-1")

        # Replace clients with individually trackable mocks
        mgr.ec2 = MagicMock()
        mgr.s3 = MagicMock()
        mgr.ssm = MagicMock()
        mgr.cloudwatch = MagicMock()
        mgr.ce = MagicMock()
        mgr.secrets = MagicMock()

        return mgr


# ---------------------------------------------------------------------------
# S3 OPERATIONS
# ---------------------------------------------------------------------------


class TestS3Upload:
    """Tests for upload_to_s3."""

    def test_upload_success(self, app):
        """Upload returns S3 URI dict on success."""
        mgr = _make_manager()

        with app.app_context():
            app.config["AWS_S3_BUCKET"] = "test-bucket"
            result = mgr.upload_to_s3(BytesIO(b"data"), "mig-001")

        assert result is not None
        assert result["bucket"] == "test-bucket"
        assert "mig-001" in result["key"]
        assert result["uri"].startswith("s3://test-bucket/")
        mgr.s3.upload_fileobj.assert_called_once()

    def test_upload_missing_bucket(self, app):
        """Upload returns None when AWS_S3_BUCKET not configured."""
        mgr = _make_manager()

        with app.app_context():
            app.config["AWS_S3_BUCKET"] = ""
            result = mgr.upload_to_s3(BytesIO(b"data"), "mig-001")

        assert result is None
        mgr.s3.upload_fileobj.assert_not_called()

    def test_upload_with_metadata(self, app):
        """Custom metadata is included in upload."""
        mgr = _make_manager()

        with app.app_context():
            app.config["AWS_S3_BUCKET"] = "test-bucket"
            result = mgr.upload_to_s3(
                BytesIO(b"data"),
                "mig-002",
                metadata={"entity_count": "500", "source_type": "QBD"},
            )

        assert result is not None
        call_args = mgr.s3.upload_fileobj.call_args
        extra_args = call_args[1].get("ExtraArgs") or call_args[0][3]
        assert "entity-count" in extra_args["Metadata"]

    def test_upload_exception_returns_none(self, app):
        """S3 upload exception returns None and publishes failure metric."""
        mgr = _make_manager()
        mgr.s3.upload_fileobj.side_effect = Exception("network error")

        with app.app_context():
            app.config["AWS_S3_BUCKET"] = "test-bucket"
            result = mgr.upload_to_s3(BytesIO(b"data"), "mig-003")

        assert result is None


class TestS3Delete:
    """Tests for delete_s3_file."""

    def test_delete_success(self, app):
        """Deletes matching objects and returns True."""
        mgr = _make_manager()
        mgr.s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "migrations/2026/01/01/mig-001/encrypted_data.bin"},
                {"Key": "migrations/2026/01/01/mig-001/encryption_metadata.json"},
            ],
            "IsTruncated": False,
        }

        with app.app_context():
            app.config["AWS_S3_BUCKET"] = "test-bucket"
            result = mgr.delete_s3_file("mig-001")

        assert result is True
        assert mgr.s3.delete_object.call_count == 2

    def test_delete_no_matching_objects(self, app):
        """No matching objects: still returns True, logs warning."""
        mgr = _make_manager()
        mgr.s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "migrations/2026/01/01/mig-999/data.bin"}],
            "IsTruncated": False,
        }

        with app.app_context():
            app.config["AWS_S3_BUCKET"] = "test-bucket"
            result = mgr.delete_s3_file("mig-001")

        assert result is True
        mgr.s3.delete_object.assert_not_called()

    def test_delete_respects_max_pages(self, app):
        """Pagination stops at MAX_PAGES safety limit."""
        mgr = _make_manager()
        # Always return truncated to simulate infinite pages
        mgr.s3.list_objects_v2.return_value = {
            "Contents": [],
            "IsTruncated": True,
            "NextContinuationToken": "token",
        }

        with app.app_context():
            app.config["AWS_S3_BUCKET"] = "test-bucket"
            result = mgr.delete_s3_file("mig-001")

        assert result is True
        # Should stop at MAX_PAGES (100)
        assert mgr.s3.list_objects_v2.call_count == 100

    def test_delete_missing_bucket(self, app):
        """Missing bucket config returns False."""
        mgr = _make_manager()

        with app.app_context():
            app.config["AWS_S3_BUCKET"] = ""
            result = mgr.delete_s3_file("mig-001")

        assert result is False


# ---------------------------------------------------------------------------
# ENCRYPTION METADATA
# ---------------------------------------------------------------------------


class TestEncryptionMetadata:
    """Tests for store/get encryption metadata."""

    def test_store_metadata_success(self, app):
        """Stores JSON metadata to S3 with encryption."""
        mgr = _make_manager()

        with app.app_context():
            app.config["AWS_S3_BUCKET"] = "test-bucket"
            result = mgr.store_encryption_metadata(
                "mig-001", {"key": "value", "algorithm": "AES-256"}
            )

        assert result is True
        call_args = mgr.s3.put_object.call_args
        assert call_args[1]["ServerSideEncryption"] == "AES256"
        body = json.loads(call_args[1]["Body"].decode("utf-8"))
        assert body["algorithm"] == "AES-256"

    def test_store_metadata_missing_bucket(self, app):
        """Returns False when bucket not configured."""
        mgr = _make_manager()

        with app.app_context():
            app.config["AWS_S3_BUCKET"] = ""
            result = mgr.store_encryption_metadata("mig-001", {})

        assert result is False

    def test_get_metadata_success(self, app):
        """Retrieves and parses encryption metadata."""
        mgr = _make_manager()
        metadata = {"algorithm": "AES-256-GCM", "key_id": "test-key"}

        # Mock _find_migration_metadata_key
        with patch.object(
            mgr,
            "_find_migration_metadata_key",
            return_value="migrations/mig-001/encryption_metadata.json",
        ):
            mock_body = MagicMock()
            mock_body.read.return_value = json.dumps(metadata).encode("utf-8")
            mgr.s3.get_object.return_value = {"Body": mock_body}

            with app.app_context():
                app.config["AWS_S3_BUCKET"] = "test-bucket"
                result = mgr.get_encryption_metadata("mig-001")

        assert result == metadata

    def test_get_metadata_not_found(self, app):
        """Returns None when metadata key not found."""
        mgr = _make_manager()

        with patch.object(mgr, "_find_migration_metadata_key", return_value=None):
            with app.app_context():
                app.config["AWS_S3_BUCKET"] = "test-bucket"
                result = mgr.get_encryption_metadata("mig-001")

        assert result is None


class TestFindMigrationMetadataKey:
    """Tests for _find_migration_metadata_key with MED-15 pagination fix."""

    def test_finds_metadata_key(self, app):
        """Finds the metadata key in first page."""
        mgr = _make_manager()
        mgr.s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "migrations/mig-001/encryption_metadata.json"},
            ],
            "IsTruncated": False,
        }

        result = mgr._find_migration_metadata_key("mig-001", "test-bucket")
        assert result == "migrations/mig-001/encryption_metadata.json"

    def test_returns_none_when_not_found(self, app):
        """Returns None when metadata file doesn't exist."""
        mgr = _make_manager()
        mgr.s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "migrations/mig-001/data.bin"}],
            "IsTruncated": False,
        }

        result = mgr._find_migration_metadata_key("mig-001", "test-bucket")
        assert result is None

    def test_respects_max_pages_limit(self, app):
        """Stops at max_pages (10) to prevent runaway pagination."""
        mgr = _make_manager()
        mgr.s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "migrations/mig-001/data.bin"}],
            "IsTruncated": True,
            "NextContinuationToken": "token",
        }

        result = mgr._find_migration_metadata_key("mig-001", "test-bucket")
        assert result is None
        assert mgr.s3.list_objects_v2.call_count == 10

    def test_uses_migration_specific_prefix(self, app):
        """MED-15 FIX: Uses migration-specific prefix, not broad 'migrations/'."""
        mgr = _make_manager()
        mgr.s3.list_objects_v2.return_value = {
            "Contents": [],
            "IsTruncated": False,
        }

        mgr._find_migration_metadata_key("mig-001", "test-bucket")
        call_args = mgr.s3.list_objects_v2.call_args
        assert call_args[1]["Prefix"] == "migrations/mig-001/"


# ---------------------------------------------------------------------------
# EC2 INSTANCE PROVISIONING
# ---------------------------------------------------------------------------


class TestEC2Provisioning:
    """Tests for create_ec2_instance and related methods."""

    @patch("utils.aws_manager.boto3")
    def test_create_instance_success(self, mock_boto3, app):
        """Creates EC2 instance and returns instance ID."""
        mgr = _make_manager()
        mgr.ec2.run_instances.return_value = {
            "Instances": [{"InstanceId": "i-1234567890abcdef0"}]
        }
        # Mock the SSM client created inside _generate_user_data_script
        mock_ssm = MagicMock()
        mock_boto3.client.return_value = mock_ssm

        with app.app_context():
            app.config.update(
                {
                    "AWS_EC2_AMI_ID": "ami-test",
                    "AWS_EC2_INSTANCE_TYPE": "t3.medium",
                    "AWS_EC2_KEY_NAME": "test-key",
                    "AWS_EC2_SECURITY_GROUP": "sg-test",
                    "AWS_EC2_SUBNET_ID": "subnet-test",
                    "AWS_IAM_INSTANCE_PROFILE": "test-profile",
                    "SERVER_URL": "https://test.example.com",
                    "AWS_S3_CODE_BUCKET": "code-bucket",
                }
            )
            result = mgr.create_ec2_instance(
                "mig-001",
                "s3://test-bucket/data.bin",
                {"client_id": "test"},
                "webhook-secret-123",
            )

        assert result == "i-1234567890abcdef0"
        mgr.ec2.run_instances.assert_called_once()

        # Verify launch config
        launch_config = mgr.ec2.run_instances.call_args[1]
        assert launch_config["ImageId"] == "ami-test"
        assert launch_config["InstanceInitiatedShutdownBehavior"] == "terminate"
        assert launch_config["BlockDeviceMappings"][0]["Ebs"]["Encrypted"] is True

    def test_create_instance_missing_config(self, app):
        """Returns None when required EC2 config missing."""
        mgr = _make_manager()

        with app.app_context():
            app.config.update(
                {
                    "AWS_EC2_AMI_ID": None,
                    "AWS_EC2_INSTANCE_TYPE": "t3.medium",
                    "AWS_EC2_KEY_NAME": None,
                    "AWS_IAM_INSTANCE_PROFILE": None,
                }
            )
            result = mgr.create_ec2_instance(
                "mig-001", "s3://test/data.bin", {}, "secret"
            )

        assert result is None

    def test_terminate_instance_success(self):
        """Terminates instance and returns True."""
        mgr = _make_manager()
        result = mgr.terminate_instance("i-test")
        assert result is True
        mgr.ec2.terminate_instances.assert_called_once_with(InstanceIds=["i-test"])

    def test_terminate_instance_failure(self):
        """Returns False when termination fails."""
        mgr = _make_manager()
        mgr.ec2.terminate_instances.side_effect = Exception("access denied")
        result = mgr.terminate_instance("i-test")
        assert result is False

    def test_get_instance_status(self):
        """Returns instance state dictionary."""
        mgr = _make_manager()
        mgr.ec2.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "State": {"Name": "running"},
                            "InstanceType": "t3.medium",
                            "PublicIpAddress": "1.2.3.4",
                            "PrivateIpAddress": "10.0.0.1",
                            "LaunchTime": datetime(2026, 1, 1, tzinfo=timezone.utc),
                            "Monitoring": {"State": "enabled"},
                            "Tags": [{"Key": "Name", "Value": "test"}],
                        }
                    ]
                }
            ]
        }

        result = mgr.get_instance_status("i-test")
        assert result["state"] == "running"
        assert result["public_ip"] == "1.2.3.4"
        assert result["tags"]["Name"] == "test"

    def test_get_instance_status_not_found(self):
        """Returns not_found when instance doesn't exist."""
        mgr = _make_manager()
        mgr.ec2.describe_instances.return_value = {"Reservations": []}

        result = mgr.get_instance_status("i-nonexistent")
        assert result["state"] == "not_found"


# ---------------------------------------------------------------------------
# COST TRACKING
# ---------------------------------------------------------------------------


class TestCostTracking:
    """Tests for get_migration_cost."""

    def test_cost_tracking_success(self):
        """Parses AWS Cost Explorer response correctly."""
        mgr = _make_manager()
        mgr.ce.get_cost_and_usage.return_value = {
            "ResultsByTime": [
                {
                    "Groups": [
                        {
                            "Keys": ["Amazon EC2"],
                            "Metrics": {"UnblendedCost": {"Amount": "10.50"}},
                        },
                        {
                            "Keys": ["Amazon S3"],
                            "Metrics": {"UnblendedCost": {"Amount": "1.25"}},
                        },
                    ]
                }
            ]
        }

        result = mgr.get_migration_cost("mig-001", "2026-01-01", "2026-01-31")
        assert result["total_cost"] == 11.75
        assert result["breakdown"]["Amazon EC2"] == 10.50
        assert result["breakdown"]["Amazon S3"] == 1.25

    def test_cost_tracking_failure(self):
        """Returns zero cost on failure."""
        mgr = _make_manager()
        mgr.ce.get_cost_and_usage.side_effect = Exception("access denied")

        result = mgr.get_migration_cost("mig-001", "2026-01-01", "2026-01-31")
        assert result["total_cost"] == 0.0
        assert "error" in result


# ---------------------------------------------------------------------------
# CLEANUP & LIFECYCLE
# ---------------------------------------------------------------------------


class TestCleanupMigration:
    """Tests for cleanup_migration."""

    def test_full_cleanup_success(self, app):
        """All three cleanup steps succeed."""
        mgr = _make_manager()

        # S3 delete
        mgr.s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "migrations/2026/01/01/mig-001/data.bin"}],
            "IsTruncated": False,
        }

        with app.app_context():
            app.config["AWS_S3_BUCKET"] = "test-bucket"
            result = mgr.cleanup_migration("mig-001", instance_id="i-test")

        assert result["instance_terminated"] is True
        assert result["s3_deleted"] is True
        assert result["secret_deleted"] is True

    def test_cleanup_no_instance(self, app):
        """Cleanup without instance ID skips EC2 termination."""
        mgr = _make_manager()
        mgr.s3.list_objects_v2.return_value = {
            "Contents": [],
            "IsTruncated": False,
        }

        with app.app_context():
            app.config["AWS_S3_BUCKET"] = "test-bucket"
            result = mgr.cleanup_migration("mig-001")

        assert result["instance_terminated"] is True  # No instance to terminate
        mgr.ec2.terminate_instances.assert_not_called()

    def test_cleanup_secret_already_deleted(self, app):
        """Secret deletion succeeds when secret already gone."""
        from botocore.exceptions import ClientError

        mgr = _make_manager()
        mgr.s3.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
        mgr.secrets.delete_secret.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}}, "DeleteSecret"
        )

        with app.app_context():
            app.config["AWS_S3_BUCKET"] = "test-bucket"
            result = mgr.cleanup_migration("mig-001")

        assert result["secret_deleted"] is True


# ---------------------------------------------------------------------------
# CLOUDWATCH METRICS
# ---------------------------------------------------------------------------


class TestCloudWatchMetrics:
    """Tests for _publish_metric."""

    def test_publish_metric_success(self):
        """Publishes metric to CloudWatch."""
        mgr = _make_manager()
        mgr._publish_metric("TestMetric", 42, "Count")

        mgr.cloudwatch.put_metric_data.assert_called_once()
        call_args = mgr.cloudwatch.put_metric_data.call_args[1]
        assert call_args["Namespace"] == "QBMigrations"
        metric = call_args["MetricData"][0]
        assert metric["MetricName"] == "TestMetric"
        assert metric["Value"] == 42

    def test_publish_metric_failure_no_raise(self):
        """Metric publish failure doesn't raise (logs warning)."""
        mgr = _make_manager()
        mgr.cloudwatch.put_metric_data.side_effect = Exception("CloudWatch down")

        # Should not raise
        mgr._publish_metric("TestMetric", 1, "Count")
