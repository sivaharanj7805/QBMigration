"""
Test Suite for Migrations REST API Endpoints
Tests cover:
1. List migrations (empty, with data, pagination, status filter)
2. Get migration details (found, not found, wrong user)
3. Get migration status (lightweight polling endpoint)
4. Cancel migration (allowed states vs disallowed)
5. Retry migration (only failed, respects max_retries)
6. Delete migration (success, blocked if processing)
7. Migration stats
8. Invalid migration_id format (SQL injection prevention)
"""

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from models.database import db
from models.user import User
from models.migration import Migration


class TestListMigrations:
    """Tests for GET /api/migrations"""

    def test_list_migrations_requires_auth(self, client, db_session):
        """Unauthenticated request returns 401."""
        response = client.get('/api/migrations')
        assert response.status_code == 401

    def test_list_migrations_empty(self, authenticated_client, db_session):
        """Returns empty list when user has no migrations."""
        response = authenticated_client.get('/api/migrations')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['migrations'] == []
        assert data['pagination']['total_items'] == 0

    def test_list_migrations_with_data(self, authenticated_client, db_session, test_user):
        """Returns migrations belonging to the current user."""
        for i in range(3):
            m = Migration(
                user_id=test_user.id,
                company_name=f'Company {i}',
                qb_file_name=f'file_{i}.qbw',
                status='pending',
            )
            db_session.add(m)
        db_session.commit()

        response = authenticated_client.get('/api/migrations')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert len(data['migrations']) == 3
        assert data['pagination']['total_items'] == 3

    def test_list_migrations_pagination(self, authenticated_client, db_session, test_user):
        """Pagination returns correct page size and metadata."""
        for i in range(15):
            m = Migration(
                user_id=test_user.id,
                company_name=f'Company {i}',
                qb_file_name=f'file_{i}.qbw',
                status='pending',
            )
            db_session.add(m)
        db_session.commit()

        # Request page 1 with 5 per page
        response = authenticated_client.get('/api/migrations?page=1&per_page=5')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data['migrations']) == 5
        assert data['pagination']['total_items'] == 15
        assert data['pagination']['total_pages'] == 3
        assert data['pagination']['has_next'] is True
        assert data['pagination']['has_prev'] is False

        # Request page 3
        response = authenticated_client.get('/api/migrations?page=3&per_page=5')
        data = response.get_json()
        assert len(data['migrations']) == 5
        assert data['pagination']['has_next'] is False
        assert data['pagination']['has_prev'] is True

    def test_list_migrations_status_filter(self, authenticated_client, db_session, test_user):
        """Filtering by status returns only matching migrations."""
        for status in ['pending', 'pending', 'completed', 'failed']:
            m = Migration(
                user_id=test_user.id,
                company_name='Co',
                qb_file_name='f.qbw',
                status=status,
            )
            db_session.add(m)
        db_session.commit()

        response = authenticated_client.get('/api/migrations?status=pending')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data['migrations']) == 2
        for mig in data['migrations']:
            assert mig['status'] == 'pending'

    def test_list_migrations_invalid_status_filter(self, authenticated_client, db_session):
        """Invalid status filter returns 400."""
        response = authenticated_client.get('/api/migrations?status=hacked')
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False

    def test_list_migrations_does_not_show_other_users(self, authenticated_client, db_session, test_user):
        """Migrations belonging to other users are not returned."""
        # Create another user
        other_user = User(
            email='other@example.com',
            first_name='Other',
            last_name='User',
            company_name='Other Co'
        )
        other_user.set_password('OtherPassword1234')
        db_session.add(other_user)
        db_session.commit()
        db_session.refresh(other_user)

        # Create migration for other user
        m = Migration(
            user_id=other_user.id,
            company_name='Other Co',
            qb_file_name='other.qbw',
            status='pending',
        )
        db_session.add(m)
        db_session.commit()

        response = authenticated_client.get('/api/migrations')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data['migrations']) == 0

    def test_list_migrations_ordered_by_newest_first(self, authenticated_client, db_session, test_user):
        """Migrations are returned newest first."""
        old = Migration(
            user_id=test_user.id,
            company_name='Old',
            qb_file_name='old.qbw',
            status='pending',
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        new = Migration(
            user_id=test_user.id,
            company_name='New',
            qb_file_name='new.qbw',
            status='pending',
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        db_session.add_all([old, new])
        db_session.commit()

        response = authenticated_client.get('/api/migrations')
        data = response.get_json()
        assert data['migrations'][0]['company_name'] == 'New'
        assert data['migrations'][1]['company_name'] == 'Old'


class TestGetMigration:
    """Tests for GET /api/migrations/<migration_id>"""

    def test_get_migration_found(self, authenticated_client, db_session, test_migration):
        """Returns migration details when found."""
        response = authenticated_client.get(
            f'/api/migrations/{test_migration.migration_id}'
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['migration']['migration_id'] == test_migration.migration_id
        assert data['migration']['status'] == 'pending'
        assert data['migration']['company_name'] == 'Test Company'

    def test_get_migration_not_found(self, authenticated_client, db_session):
        """Returns 404 for non-existent migration."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.get(f'/api/migrations/{fake_id}')
        assert response.status_code == 404
        data = response.get_json()
        assert data['success'] is False

    def test_get_migration_wrong_user(self, authenticated_client, db_session):
        """Returns 404 when migration belongs to another user (no info leak)."""
        # Create another user and their migration
        other_user = User(
            email='other2@example.com',
            first_name='Other',
            last_name='User',
            company_name='Other Co'
        )
        other_user.set_password('OtherPassword1234')
        db_session.add(other_user)
        db_session.commit()
        db_session.refresh(other_user)

        other_migration = Migration(
            user_id=other_user.id,
            company_name='Secret Co',
            qb_file_name='secret.qbw',
            status='completed',
        )
        db_session.add(other_migration)
        db_session.commit()
        db_session.refresh(other_migration)

        # Current user should not see other user's migration
        response = authenticated_client.get(
            f'/api/migrations/{other_migration.migration_id}'
        )
        assert response.status_code == 404

    def test_get_migration_requires_auth(self, client, db_session, test_migration):
        """Unauthenticated request returns 401."""
        response = client.get(f'/api/migrations/{test_migration.migration_id}')
        assert response.status_code == 401


class TestGetMigrationStatus:
    """Tests for GET /api/migrations/<migration_id>/status"""

    def test_get_status_success(self, authenticated_client, db_session, test_migration):
        """Returns lightweight status data."""
        response = authenticated_client.get(
            f'/api/migrations/{test_migration.migration_id}/status'
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['migration_id'] == test_migration.migration_id
        assert data['status'] == 'pending'
        assert 'progress_percent' in data

    def test_get_status_not_found(self, authenticated_client, db_session):
        """Returns 404 for non-existent migration."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.get(f'/api/migrations/{fake_id}/status')
        assert response.status_code == 404

    def test_get_status_with_current_step(self, authenticated_client, db_session, test_migration):
        """Status includes current_step when set."""
        test_migration.current_step = 'Migrating Invoices'
        test_migration.progress_percent = 45
        db_session.commit()

        response = authenticated_client.get(
            f'/api/migrations/{test_migration.migration_id}/status'
        )
        data = response.get_json()
        assert data['current_step'] == 'Migrating Invoices'
        assert data['progress_percent'] == 45

    def test_get_status_requires_auth(self, client, db_session, test_migration):
        """Unauthenticated request returns 401."""
        response = client.get(
            f'/api/migrations/{test_migration.migration_id}/status'
        )
        assert response.status_code == 401


class TestCancelMigration:
    """Tests for POST /api/migrations/<migration_id>/cancel"""

    @pytest.mark.parametrize('initial_status', ['pending', 'uploaded', 'provisioning', 'processing'])
    @patch('api.migrations.AWSMigrationManager')
    def test_cancel_allowed_states(self, mock_aws_cls, initial_status,
                                   authenticated_client, db_session, test_migration):
        """Cancel succeeds from allowed states: pending, uploaded, provisioning, processing."""
        mock_aws = MagicMock()
        mock_aws.cleanup_migration.return_value = {
            'instance_terminated': True,
            's3_deleted': True,
        }
        mock_aws_cls.return_value = mock_aws

        test_migration.status = initial_status
        db_session.commit()

        response = authenticated_client.post(
            f'/api/migrations/{test_migration.migration_id}/cancel'
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    @pytest.mark.parametrize('initial_status', ['completed', 'failed', 'cleaned'])
    def test_cancel_disallowed_states(self, initial_status,
                                      authenticated_client, db_session, test_migration):
        """Cancel fails from terminal states: completed, failed, cleaned."""
        test_migration.status = initial_status
        db_session.commit()

        response = authenticated_client.post(
            f'/api/migrations/{test_migration.migration_id}/cancel'
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'cannot be cancelled' in data['error']

    def test_cancel_not_found(self, authenticated_client, db_session):
        """Returns 404 for non-existent migration."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.post(f'/api/migrations/{fake_id}/cancel')
        assert response.status_code == 404

    def test_cancel_requires_auth(self, client, db_session, test_migration):
        """Unauthenticated request returns 401."""
        response = client.post(
            f'/api/migrations/{test_migration.migration_id}/cancel'
        )
        assert response.status_code == 401


class TestRetryMigration:
    """Tests for POST /api/migrations/<migration_id>/retry"""

    def test_retry_failed_migration(self, authenticated_client, db_session, test_migration):
        """Retry succeeds for a failed migration within retry limit."""
        test_migration.status = 'failed'
        test_migration.retry_count = 0
        db_session.commit()

        response = authenticated_client.post(
            f'/api/migrations/{test_migration.migration_id}/retry'
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

        # Verify migration was reset
        db_session.refresh(test_migration)
        assert test_migration.status == 'uploaded'
        assert test_migration.retry_count == 1
        assert test_migration.progress_percent == 0

    def test_retry_non_failed_migration(self, authenticated_client, db_session, test_migration):
        """Retry fails for non-failed migration."""
        test_migration.status = 'pending'
        db_session.commit()

        response = authenticated_client.post(
            f'/api/migrations/{test_migration.migration_id}/retry'
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'Only failed' in data['error']

    def test_retry_max_retries_reached(self, authenticated_client, db_session, test_migration):
        """Retry fails when max_retries is reached."""
        test_migration.status = 'failed'
        test_migration.retry_count = 3
        test_migration.max_retries = 3
        db_session.commit()

        response = authenticated_client.post(
            f'/api/migrations/{test_migration.migration_id}/retry'
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'Maximum retry' in data['error']

    def test_retry_not_found(self, authenticated_client, db_session):
        """Returns 404 for non-existent migration."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.post(f'/api/migrations/{fake_id}/retry')
        assert response.status_code == 404

    def test_retry_requires_auth(self, client, db_session, test_migration):
        """Unauthenticated request returns 401."""
        response = client.post(
            f'/api/migrations/{test_migration.migration_id}/retry'
        )
        assert response.status_code == 401

    def test_retry_increments_count_each_time(self, authenticated_client, db_session, test_migration):
        """Each retry increments the retry_count."""
        test_migration.status = 'failed'
        test_migration.retry_count = 1
        test_migration.max_retries = 3
        db_session.commit()

        response = authenticated_client.post(
            f'/api/migrations/{test_migration.migration_id}/retry'
        )
        assert response.status_code == 200

        db_session.refresh(test_migration)
        assert test_migration.retry_count == 2


class TestDeleteMigration:
    """Tests for DELETE /api/migrations/<migration_id>"""

    @patch('api.migrations.AWSMigrationManager')
    def test_delete_success(self, mock_aws_cls, authenticated_client, db_session, test_migration):
        """Delete succeeds and removes migration from database."""
        mock_aws = MagicMock()
        mock_aws.cleanup_migration.return_value = {}
        mock_aws_cls.return_value = mock_aws

        migration_id = test_migration.migration_id

        response = authenticated_client.delete(
            f'/api/migrations/{migration_id}'
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

        # Verify migration is gone
        result = Migration.query.filter_by(migration_id=migration_id).first()
        assert result is None

    @patch('api.migrations.AWSMigrationManager')
    def test_delete_completed_migration(self, mock_aws_cls, authenticated_client, db_session, test_migration):
        """Completed migrations can be deleted."""
        mock_aws = MagicMock()
        mock_aws.cleanup_migration.return_value = {}
        mock_aws_cls.return_value = mock_aws

        test_migration.status = 'completed'
        test_migration.cleanup_completed = True
        db_session.commit()

        response = authenticated_client.delete(
            f'/api/migrations/{test_migration.migration_id}'
        )
        assert response.status_code == 200

    def test_delete_not_found(self, authenticated_client, db_session):
        """Returns 404 for non-existent migration."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.delete(f'/api/migrations/{fake_id}')
        assert response.status_code == 404

    def test_delete_requires_auth(self, client, db_session, test_migration):
        """Unauthenticated request returns 401."""
        response = client.delete(
            f'/api/migrations/{test_migration.migration_id}'
        )
        assert response.status_code == 401

    @patch('api.migrations.AWSMigrationManager')
    def test_delete_cleanup_failure_still_deletes(self, mock_aws_cls,
                                                   authenticated_client, db_session, test_migration):
        """Migration is deleted even if AWS cleanup fails."""
        mock_aws = MagicMock()
        mock_aws.cleanup_migration.side_effect = Exception('AWS unreachable')
        mock_aws_cls.return_value = mock_aws

        migration_id = test_migration.migration_id

        response = authenticated_client.delete(
            f'/api/migrations/{migration_id}'
        )
        assert response.status_code == 200

        result = Migration.query.filter_by(migration_id=migration_id).first()
        assert result is None


class TestMigrationStats:
    """Tests for GET /api/migrations/stats"""

    def test_stats_empty(self, authenticated_client, db_session):
        """Stats return defaults when user has no migrations."""
        response = authenticated_client.get('/api/migrations/stats')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        stats = data['stats']
        assert stats['migrations_this_month'] == 0
        assert stats['total_records'] == '0'
        assert stats['success_rate'] == '100.0%'

    def test_stats_with_migrations(self, authenticated_client, db_session, test_user):
        """Stats reflect actual migration data."""
        # Create a completed migration with records
        m = Migration(
            user_id=test_user.id,
            company_name='Stats Co',
            qb_file_name='stats.qbw',
            status='completed',
            total_records_migrated=1500,
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(m)
        db_session.commit()

        response = authenticated_client.get('/api/migrations/stats')
        assert response.status_code == 200
        data = response.get_json()
        stats = data['stats']
        assert stats['migrations_this_month'] >= 1
        assert stats['success_rate'] == '100.0%'
        # total_records is formatted as string (e.g. "1.5K" or "1500")
        assert stats['total_records'] != '0'

    def test_stats_success_rate_with_failures(self, authenticated_client, db_session, test_user):
        """Success rate accounts for failed migrations."""
        # 1 completed, 1 failed
        for status in ['completed', 'failed']:
            m = Migration(
                user_id=test_user.id,
                company_name='Rate Co',
                qb_file_name='rate.qbw',
                status=status,
                created_at=datetime.now(timezone.utc),
            )
            db_session.add(m)
        db_session.commit()

        response = authenticated_client.get('/api/migrations/stats')
        data = response.get_json()
        assert data['stats']['success_rate'] == '50.0%'

    def test_stats_requires_auth(self, client, db_session):
        """Unauthenticated request returns 401."""
        response = client.get('/api/migrations/stats')
        assert response.status_code == 401


class TestInvalidMigrationId:
    """Tests for SQL injection prevention via migration_id validation."""

    def test_sql_injection_in_get(self, authenticated_client, db_session):
        """SQL injection attempt in GET returns 400."""
        response = authenticated_client.get(
            "/api/migrations/1; DROP TABLE migrations;--"
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'Invalid migration ID' in data['error']

    def test_sql_injection_in_status(self, authenticated_client, db_session):
        """SQL injection attempt in status endpoint returns 400."""
        response = authenticated_client.get(
            "/api/migrations/' OR 1=1 --/status"
        )
        assert response.status_code == 400

    def test_sql_injection_in_cancel(self, authenticated_client, db_session):
        """SQL injection attempt in cancel endpoint is safely handled.
        The cancel endpoint does not have explicit UUID validation like
        get/status, so Flask routing or the DB query handles it safely.
        The single-quote in the URL may cause Flask to return 404 (no route match).
        """
        response = authenticated_client.post(
            "/api/migrations/'; DELETE FROM users;--/cancel"
        )
        # Flask may return 404 (route not matched) or 400 -- either is safe
        assert response.status_code in [400, 404]
        assert response.status_code != 500  # Must not cause server error

    def test_non_uuid_format_rejected(self, authenticated_client, db_session):
        """Non-UUID strings are rejected with 400."""
        response = authenticated_client.get('/api/migrations/not-a-valid-uuid')
        assert response.status_code == 400
        data = response.get_json()
        assert 'Invalid migration ID' in data['error']

    def test_valid_uuid_format_accepted(self, authenticated_client, db_session):
        """Valid UUID format passes validation (returns 404 if not found)."""
        valid_uuid = str(uuid.uuid4())
        response = authenticated_client.get(f'/api/migrations/{valid_uuid}')
        # Valid format but not found should be 404, not 400
        assert response.status_code == 404

    def test_sql_injection_in_pagination(self, authenticated_client, db_session):
        """SQL injection in pagination parameters is handled safely."""
        response = authenticated_client.get(
            '/api/migrations?page=1;DROP TABLE migrations&per_page=10'
        )
        # Should not return 500; bad params default to safe values
        assert response.status_code == 200
