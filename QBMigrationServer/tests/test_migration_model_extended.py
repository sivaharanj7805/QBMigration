"""Extended tests for models/migration.py - status management, expiry, cost, webhooks."""

import json
from datetime import datetime, timedelta, timezone


class TestMigrationStatusManagement:
    """Tests for idempotent status transition methods."""

    def test_mark_as_uploading_from_pending(self, db_session, test_migration):
        assert test_migration.status == "pending"
        result = test_migration.mark_as_uploading()
        assert result is True
        assert test_migration.status == "uploading"

    def test_mark_as_uploading_idempotent(self, db_session, test_migration):
        test_migration.status = "uploading"
        db_session.commit()
        result = test_migration.mark_as_uploading()
        assert result is False

    def test_mark_as_uploaded(self, db_session, test_migration):
        test_migration.status = "uploading"
        db_session.commit()
        result = test_migration.mark_as_uploaded(
            "s3://bucket/key", "bucket", "key"
        )
        assert result is True
        assert test_migration.status == "uploaded"
        assert test_migration.s3_uri == "s3://bucket/key"

    def test_mark_as_uploaded_from_pending(self, db_session, test_migration):
        result = test_migration.mark_as_uploaded(
            "s3://bucket/key", "bucket", "key"
        )
        assert result is True

    def test_mark_as_uploaded_idempotent(self, db_session, test_migration):
        test_migration.status = "completed"
        db_session.commit()
        result = test_migration.mark_as_uploaded("s3://b/k", "b", "k")
        assert result is False

    def test_mark_as_provisioning(self, db_session, test_migration):
        test_migration.status = "uploaded"
        db_session.commit()
        result = test_migration.mark_as_provisioning()
        assert result is True
        assert test_migration.status == "provisioning"
        assert test_migration.current_step == "Creating AWS instance"

    def test_mark_as_provisioning_wrong_status(self, db_session, test_migration):
        result = test_migration.mark_as_provisioning()
        assert result is False

    def test_mark_as_processing(self, db_session, test_migration):
        test_migration.status = "provisioning"
        db_session.commit()
        result = test_migration.mark_as_processing("i-1234567890")
        assert result is True
        assert test_migration.status == "processing"
        assert test_migration.aws_instance_id == "i-1234567890"
        assert test_migration.started_at is not None

    def test_mark_as_processing_wrong_status(self, db_session, test_migration):
        test_migration.status = "completed"
        db_session.commit()
        result = test_migration.mark_as_processing("i-123")
        assert result is False

    def test_mark_as_failed(self, db_session, test_migration):
        test_migration.status = "processing"
        db_session.commit()
        result = test_migration.mark_as_failed("Something went wrong")
        assert result is True
        assert test_migration.status == "failed"

    def test_mark_as_failed_with_code(self, db_session, test_migration):
        test_migration.status = "processing"
        db_session.commit()
        result = test_migration.mark_as_failed("Error", error_code="EC2_TIMEOUT")
        assert result is True
        assert test_migration.error_code == "EC2_TIMEOUT"

    def test_mark_as_failed_wrong_status(self, db_session, test_migration):
        test_migration.status = "completed"
        db_session.commit()
        result = test_migration.mark_as_failed("Error msg")
        assert result is False

    def test_mark_as_completed_no_results(self, db_session, test_migration):
        test_migration.status = "processing"
        db_session.commit()
        result = test_migration.mark_as_completed(results=None)
        assert result is False

    def test_mark_as_completed_with_trial_balance(self, db_session, test_migration):
        test_migration.status = "processing"
        db_session.commit()
        results = {
            "customers": 10,
            "vendors": 5,
            "invoices": 20,
            "bills": 8,
            "items": 15,
            "total": 58,
            "trial_balance": {
                "is_balanced": True,
                "source_total": 10000.00,
                "destination_total": 10000.00,
            },
        }
        result = test_migration.mark_as_completed(results=results)
        assert result is True
        assert test_migration.status == "completed"
        assert test_migration.customers_migrated == 10
        assert test_migration.total_records_migrated == 58
        assert test_migration.progress_percent == 100

    def test_mark_as_completed_trial_balance_mismatch(self, db_session, test_migration):
        test_migration.status = "processing"
        db_session.commit()
        results = {
            "trial_balance": {
                "is_balanced": False,
                "source_total": 10000.00,
                "destination_total": 9500.00,
            },
        }
        import pytest

        with pytest.raises(ValueError, match="Trial balance reconciliation failed"):
            test_migration.mark_as_completed(results=results)
        assert test_migration.status == "failed"
        assert test_migration.error_code == "TRIAL_BALANCE_MISMATCH"

    def test_mark_as_completed_missing_trial_balance(self, db_session, test_migration):
        test_migration.status = "processing"
        db_session.commit()
        results = {"customers": 10}
        import pytest

        with pytest.raises(ValueError, match="Trial balance verification data missing"):
            test_migration.mark_as_completed(results=results)
        assert test_migration.status == "failed"


class TestMigrationCleanup:
    """Tests for cleanup tracking methods."""

    def test_mark_cleanup_started(self, db_session, test_migration):
        test_migration.mark_cleanup_started()
        assert test_migration.status == "cleanup"
        assert test_migration.current_step == "Cleaning up AWS resources"

    def test_mark_s3_deleted(self, db_session, test_migration):
        test_migration.mark_s3_deleted()
        assert test_migration.s3_file_deleted is True
        assert test_migration.s3_file_deleted_at is not None

    def test_mark_ec2_terminated(self, db_session, test_migration):
        test_migration.mark_ec2_terminated()
        assert test_migration.ec2_terminated is True
        assert test_migration.ec2_terminated_at is not None

    def test_mark_cleanup_completed(self, db_session, test_migration):
        test_migration.mark_cleanup_completed()
        assert test_migration.status == "cleaned"
        assert test_migration.cleanup_completed is True
        assert test_migration.cleanup_completed_at is not None
        assert test_migration.current_step == "All resources deleted"


class TestMigrationRetry:
    """Tests for retry logic."""

    def test_can_retry_initial(self, db_session, test_migration):
        assert test_migration.can_retry() is True

    def test_can_retry_max_reached(self, db_session, test_migration):
        test_migration.retry_count = 3
        db_session.commit()
        assert test_migration.can_retry() is False

    def test_increment_retry(self, db_session, test_migration):
        assert test_migration.retry_count == 0
        test_migration.increment_retry()
        assert test_migration.retry_count == 1


class TestMigrationExpiry:
    """Tests for expiration and stuck detection."""

    def test_is_expired_false(self, db_session, test_migration):
        # Default expiry is 48 hours from now
        assert test_migration.is_expired() is False

    def test_is_expired_true(self, db_session, test_migration):
        test_migration.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.commit()
        assert test_migration.is_expired() is True

    def test_is_expired_no_expiry(self, db_session, test_migration):
        test_migration.expires_at = None
        db_session.commit()
        assert test_migration.is_expired() is False

    def test_is_expired_naive_datetime(self, db_session, test_migration):
        # Test with naive datetime (no timezone info)
        test_migration.expires_at = datetime.utcnow() - timedelta(hours=1)
        db_session.commit()
        assert test_migration.is_expired() is True

    def test_is_stuck_not_processing(self, db_session, test_migration):
        assert test_migration.is_stuck() is False

    def test_is_stuck_no_started_at(self, db_session, test_migration):
        test_migration.status = "processing"
        db_session.commit()
        assert test_migration.is_stuck() is False

    def test_is_stuck_true(self, db_session, test_migration):
        test_migration.status = "processing"
        test_migration.started_at = datetime.now(timezone.utc) - timedelta(hours=7)
        db_session.commit()
        assert test_migration.is_stuck() is True

    def test_is_stuck_false_within_timeout(self, db_session, test_migration):
        test_migration.status = "processing"
        test_migration.started_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.commit()
        assert test_migration.is_stuck() is False

    def test_needs_cleanup_completed(self, db_session, test_migration):
        test_migration.status = "completed"
        test_migration.cleanup_completed = False
        db_session.commit()
        assert test_migration.needs_cleanup() is True

    def test_needs_cleanup_already_cleaned(self, db_session, test_migration):
        test_migration.cleanup_completed = True
        db_session.commit()
        assert test_migration.needs_cleanup() is False

    def test_needs_cleanup_failed(self, db_session, test_migration):
        test_migration.status = "failed"
        test_migration.cleanup_completed = False
        db_session.commit()
        assert test_migration.needs_cleanup() is True


class TestMigrationCostEstimation:
    """Tests for cost estimation."""

    def test_estimate_cost(self, db_session, test_migration):
        test_migration.data_size_bytes = 1024 * 1024 * 1024  # 1 GB
        db_session.commit()
        test_migration.estimate_cost()
        assert test_migration.estimated_cost_usd is not None
        assert test_migration.estimated_cost_usd > 0
        assert test_migration.cost_breakdown is not None
        breakdown = json.loads(test_migration.cost_breakdown)
        assert "s3_storage" in breakdown
        assert "ec2_compute" in breakdown
        assert "data_transfer" in breakdown

    def test_estimate_cost_no_data(self, db_session, test_migration):
        test_migration.data_size_bytes = None
        db_session.commit()
        test_migration.estimate_cost()
        # Should return early without setting cost
        assert test_migration.estimated_cost_usd is None

    def test_set_actual_cost(self, db_session, test_migration):
        cost_dict = {"ec2": 1.50, "s3": 0.25, "data_transfer": 0.10}
        test_migration.set_actual_cost(cost_dict)
        assert test_migration.actual_cost_usd == 1.85
        breakdown = json.loads(test_migration.cost_breakdown)
        assert breakdown["ec2"] == 1.5


class TestMigrationWebhookTracking:
    """Tests for webhook replay prevention."""

    def test_is_webhook_processed_empty(self, db_session, test_migration):
        assert test_migration.is_webhook_processed("wh-123") is False

    def test_is_webhook_processed_found(self, db_session, test_migration):
        test_migration.webhook_processed_ids = json.dumps(["wh-123", "wh-456"])
        db_session.commit()
        assert test_migration.is_webhook_processed("wh-123") is True

    def test_is_webhook_processed_not_found(self, db_session, test_migration):
        test_migration.webhook_processed_ids = json.dumps(["wh-123"])
        db_session.commit()
        assert test_migration.is_webhook_processed("wh-999") is False

    def test_is_webhook_processed_invalid_json(self, db_session, test_migration):
        test_migration.webhook_processed_ids = "not-json"
        db_session.commit()
        assert test_migration.is_webhook_processed("wh-123") is False

    def test_mark_webhook_processed(self, db_session, test_migration):
        result = test_migration.mark_webhook_processed("wh-new")
        assert result is True
        assert test_migration.is_webhook_processed("wh-new") is True
        assert test_migration.last_webhook_at is not None

    def test_mark_webhook_processed_duplicate(self, db_session, test_migration):
        test_migration.mark_webhook_processed("wh-dup")
        result = test_migration.mark_webhook_processed("wh-dup")
        assert result is False


class TestMigrationErrorEncryption:
    """Tests for error message encryption."""

    def test_set_error_message_none(self, db_session, test_migration):
        test_migration.set_error_message(None)
        assert test_migration.error_message_encrypted is None

    def test_set_error_message_empty(self, db_session, test_migration):
        test_migration.set_error_message("")
        assert test_migration.error_message_encrypted is None

    def test_set_error_message_no_key(self, db_session, test_migration):
        # In test env (not production), should store sanitized placeholder
        test_migration.set_error_message("Some error occurred")
        assert test_migration.error_message_encrypted is not None

    def test_get_error_message_none(self, db_session, test_migration):
        test_migration.error_message_encrypted = None
        assert test_migration.get_error_message() is None

    def test_get_error_message_with_key(self, db_session, test_migration):
        from flask import current_app
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        current_app.config["BACKUP_ENCRYPTION_KEY"] = key
        test_migration.set_error_message("Test error message")
        result = test_migration.get_error_message()
        assert result == "Test error message"

    def test_calculate_file_hash(self, db_session, test_migration):
        test_migration.calculate_file_hash("test data")
        assert test_migration.file_hash is not None
        assert len(test_migration.file_hash) == 64

    def test_calculate_file_hash_bytes(self, db_session, test_migration):
        test_migration.calculate_file_hash(b"test data bytes")
        assert test_migration.file_hash is not None
        assert len(test_migration.file_hash) == 64


class TestMigrationToDict:
    """Tests for migration serialization."""

    def test_to_dict_basic(self, db_session, test_migration):
        d = test_migration.to_dict()
        assert d["migration_id"] == test_migration.migration_id
        assert d["status"] == test_migration.status
        assert "progress_percent" in d
        assert "created_at" in d

    def test_to_dict_include_sensitive(self, db_session, test_migration):
        test_migration.s3_uri = "s3://bucket/key"
        test_migration.aws_instance_id = "i-123"
        db_session.commit()
        d = test_migration.to_dict(include_sensitive=True)
        assert d["s3_uri"] == "s3://bucket/key"
        assert d["aws_instance_id"] == "i-123"
        assert "cleanup_completed" in d

    def test_to_dict_failed_migration(self, db_session, test_migration):
        test_migration.status = "failed"
        test_migration.error_code = "EC2_TIMEOUT"
        db_session.commit()
        d = test_migration.to_dict()
        assert d["error_code"] == "EC2_TIMEOUT"
        assert d["can_retry"] is True

    def test_to_dict_with_cost(self, db_session, test_migration):
        test_migration.estimated_cost_usd = 2.50
        test_migration.actual_cost_usd = 2.30
        db_session.commit()
        d = test_migration.to_dict()
        assert d["estimated_cost_usd"] == 2.50
        assert d["actual_cost_usd"] == 2.30

    def test_to_dict_with_cost_breakdown(self, db_session, test_migration):
        test_migration.cost_breakdown = json.dumps({"ec2": 1.5, "s3": 0.5})
        db_session.commit()
        d = test_migration.to_dict(include_sensitive=True)
        assert "cost_breakdown" in d
        assert d["cost_breakdown"]["ec2"] == 1.5

    def test_to_dict_caseware_destination(self, db_session, test_migration):
        test_migration.destination = "caseware"
        test_migration.caseware_bundle_ready = True
        db_session.commit()
        d = test_migration.to_dict()
        assert d["caseware_bundle_ready"] is True

    def test_to_dict_data_size(self, db_session, test_migration):
        test_migration.data_size_bytes = 1048576  # 1 MB
        db_session.commit()
        d = test_migration.to_dict(include_sensitive=True)
        assert d["data_size_mb"] == 1.0

    def test_get_duration_minutes(self, db_session, test_migration):
        test_migration.started_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        test_migration.completed_at = datetime.now(timezone.utc)
        db_session.commit()
        duration = test_migration.get_duration_minutes()
        assert duration is not None
        assert 29 <= duration <= 31

    def test_get_duration_minutes_no_start(self, db_session, test_migration):
        duration = test_migration.get_duration_minutes()
        # Returns 0 or None when no start time set
        assert duration is None or duration == 0
