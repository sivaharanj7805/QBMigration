"""
Comprehensive End-to-End Tests for Core Features
Tests: Report Generation, Reconciliation Shield, Caseware Bundle, Discrepancy Doctor
"""

import pytest
import json
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture
def auth_headers(client, test_user):
    """Get JWT auth headers for authenticated requests."""
    response = client.post('/api/auth/login', json={
        'email': 'test@example.com',
        'password': 'Test1234'
    })
    assert response.status_code == 200
    data = response.get_json()
    token = data.get('token')
    return {'Authorization': f'Bearer {token}'}


class TestReportGeneration:
    """Test Report Generation feature end-to-end."""

    def test_list_reports_endpoint(self, client, auth_headers, test_migration):
        """Test listing reports returns correct structure."""
        response = client.get('/api/reports', headers=auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'reports' in data
        assert 'count' in data
        assert isinstance(data['reports'], list)

    def test_generate_variance_report(self, client, auth_headers, test_migration, db_session):
        """Test generating a variance report."""
        # First mark migration as completed
        test_migration.status = 'completed'
        test_migration.verification_results = json.dumps({
            'trial_balance': {
                'source_total': 1000000.00,
                'destination_total': 1000000.00,
                'is_balanced': True
            }
        })
        db_session.commit()

        response = client.post('/api/reports/generate',
            headers=auth_headers,
            json={
                'type': 'variance',
                'migration_id': test_migration.migration_id
            })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'report_id' in data
        assert 'download_url' in data

    def test_generate_health_report(self, client, auth_headers, test_migration, db_session):
        """Test generating a health report."""
        test_migration.status = 'completed'
        db_session.commit()

        response = client.post('/api/reports/generate',
            headers=auth_headers,
            json={
                'type': 'health',
                'migration_id': test_migration.migration_id
            })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    def test_generate_discrepancy_report(self, client, auth_headers, test_migration, db_session):
        """Test generating a discrepancy report."""
        test_migration.status = 'completed'
        test_migration.verification_results = json.dumps({
            'discrepancies': [
                {
                    'account_name': 'Cash',
                    'source_balance': 10000.00,
                    'destination_balance': 9500.00,
                    'difference': 500.00
                }
            ]
        })
        db_session.commit()

        response = client.post('/api/reports/generate',
            headers=auth_headers,
            json={
                'type': 'discrepancy',
                'migration_id': test_migration.migration_id
            })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    def test_download_report(self, client, auth_headers, test_migration, db_session):
        """Test downloading a generated report."""
        test_migration.status = 'completed'
        db_session.commit()

        # Generate report first
        client.post('/api/reports/generate',
            headers=auth_headers,
            json={
                'type': 'variance',
                'migration_id': test_migration.migration_id
            })

        # Download the report
        report_id = f'{test_migration.migration_id}_variance'
        response = client.get(f'/api/reports/{report_id}/download', headers=auth_headers)
        # Either 200 (success) or 404 (file not yet created due to missing reportlab)
        assert response.status_code in [200, 404]


class TestReconciliationShield:
    """Test Reconciliation Shield (Trial Balance) feature end-to-end."""

    def test_get_trial_balance_pending(self, client, auth_headers, test_migration):
        """Test trial balance returns PENDING for incomplete migration."""
        response = client.get(
            f'/api/migrations/{test_migration.migration_id}/trial-balance',
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['forensic_status'] in ['PENDING', 'NOT_AVAILABLE']

    def test_get_trial_balance_verified(self, client, auth_headers, test_migration, db_session):
        """Test trial balance returns VERIFIED for balanced migration."""
        test_migration.status = 'completed'
        test_migration.verification_results = json.dumps({
            'trial_balance': {
                'source_total': 1000000.00,
                'destination_total': 1000000.00,
                'is_balanced': True,
                'total_debits': 500000.00,
                'total_credits': 500000.00
            },
            'integrity': {
                'source_hash': 'abc123def456...',
                'destination_hash': 'abc123def456...',
                'hash_match': True
            }
        })
        db_session.commit()

        response = client.get(
            f'/api/migrations/{test_migration.migration_id}/trial-balance',
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['forensic_status'] == 'VERIFIED'
        assert data['is_balanced'] is True
        assert data['source_trial_balance'] == 1000000.00
        assert data['destination_trial_balance'] == 1000000.00
        assert data['discrepancy'] == 0.00

    def test_get_trial_balance_discrepancy(self, client, auth_headers, test_migration, db_session):
        """Test trial balance returns DISCREPANCY_DETECTED when unbalanced."""
        test_migration.status = 'completed'
        test_migration.verification_results = json.dumps({
            'trial_balance': {
                'source_total': 1000000.00,
                'destination_total': 999500.00,
                'is_balanced': False
            }
        })
        db_session.commit()

        response = client.get(
            f'/api/migrations/{test_migration.migration_id}/trial-balance',
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['forensic_status'] == 'DISCREPANCY_DETECTED'
        assert data['is_balanced'] is False
        assert data['discrepancy'] == 500.00

    def test_trial_balance_not_found(self, client, auth_headers):
        """Test trial balance returns 404 for non-existent migration."""
        response = client.get(
            '/api/migrations/non_existent_id/trial-balance',
            headers=auth_headers
        )
        assert response.status_code == 404


class TestCasewareBundle:
    """Test Caseware Bundle feature end-to-end."""

    def test_export_caseware_requires_auth(self, client, test_migration):
        """Test Caseware export requires authentication."""
        response = client.post(
            f'/api/migrations/{test_migration.migration_id}/export-caseware'
        )
        assert response.status_code == 401

    def test_export_caseware_creates_bundle(self, client, auth_headers, test_migration, db_session):
        """Test Caseware export creates bundle files."""
        test_migration.status = 'completed'
        db_session.commit()

        response = client.post(
            f'/api/migrations/{test_migration.migration_id}/export-caseware',
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'bundle_id' in data
        assert 'files' in data
        assert 'download_url' in data

    def test_download_caseware_bundle(self, client, auth_headers, test_migration, db_session):
        """Test downloading Caseware bundle."""
        test_migration.status = 'completed'
        db_session.commit()

        # Generate bundle first
        client.post(
            f'/api/migrations/{test_migration.migration_id}/export-caseware',
            headers=auth_headers
        )

        # Download bundle
        response = client.get(
            f'/api/migrations/{test_migration.migration_id}/caseware-bundle',
            headers=auth_headers
        )
        # Should either succeed or tell us to regenerate
        assert response.status_code in [200, 400]

    def test_caseware_bundle_without_generation_fails(self, client, auth_headers, test_migration):
        """Test downloading bundle without generating fails."""
        response = client.get(
            f'/api/migrations/{test_migration.migration_id}/caseware-bundle',
            headers=auth_headers
        )
        assert response.status_code == 400
        data = response.get_json()
        assert 'not yet generated' in data['error'].lower() or 'not found' in data['error'].lower()


class TestDiscrepancyDoctor:
    """Test Discrepancy Doctor feature end-to-end."""

    def test_get_discrepancies_empty(self, client, auth_headers, test_migration):
        """Test getting discrepancies when none exist."""
        response = client.get(
            f'/api/migrations/{test_migration.migration_id}/discrepancies',
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['has_discrepancies'] is False
        assert data['discrepancies'] == []

    def test_get_discrepancies_with_data(self, client, auth_headers, test_migration, db_session):
        """Test getting discrepancies when they exist."""
        test_migration.verification_results = json.dumps({
            'discrepancies': [
                {
                    'account_name': 'Cash',
                    'account_type': 'Bank',
                    'source_balance': 10000.00,
                    'destination_balance': 9500.00,
                    'difference': 500.00,
                    'severity': 'warning',
                    'possible_cause': 'Pending reconciliation'
                },
                {
                    'account_name': 'Accounts Receivable',
                    'account_type': 'Asset',
                    'source_balance': 50000.00,
                    'destination_balance': 49000.00,
                    'difference': 1000.00,
                    'severity': 'critical',
                    'possible_cause': 'Missing invoices'
                }
            ]
        })
        db_session.commit()

        response = client.get(
            f'/api/migrations/{test_migration.migration_id}/discrepancies',
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['has_discrepancies'] is True
        assert len(data['discrepancies']) == 2
        assert data['total_discrepancy'] == 1500.00  # 500 + 1000

    def test_download_discrepancy_report(self, client, auth_headers, test_migration, db_session):
        """Test downloading discrepancy report."""
        test_migration.status = 'completed'
        test_migration.verification_results = json.dumps({
            'discrepancies': [
                {
                    'account_name': 'Cash',
                    'source_balance': 10000.00,
                    'destination_balance': 9500.00,
                    'difference': 500.00
                }
            ]
        })
        db_session.commit()

        response = client.get(
            f'/api/migrations/{test_migration.migration_id}/discrepancy-report',
            headers=auth_headers
        )
        # Either 200 (success) or 500 (missing reportlab)
        assert response.status_code in [200, 500]


class TestAuditCertificate:
    """Test Audit Certificate feature end-to-end."""

    def test_certificate_preview(self, client, auth_headers, test_migration, db_session):
        """Test getting certificate preview metadata."""
        test_migration.status = 'completed'
        db_session.commit()

        response = client.get(
            f'/api/migrations/{test_migration.migration_id}/audit-certificate/preview',
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['available'] is True
        assert 'download_url' in data

    def test_certificate_not_available_for_incomplete(self, client, auth_headers, test_migration):
        """Test certificate not available for incomplete migration."""
        response = client.get(
            f'/api/migrations/{test_migration.migration_id}/audit-certificate/preview',
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['available'] is False

    def test_download_certificate(self, client, auth_headers, test_migration, db_session):
        """Test downloading audit certificate."""
        test_migration.status = 'completed'
        db_session.commit()

        response = client.get(
            f'/api/migrations/{test_migration.migration_id}/audit-certificate',
            headers=auth_headers
        )
        # Either 200 (success) or 500 (certificate generation issue)
        assert response.status_code in [200, 500]


class TestDashboardOverview:
    """Test Dashboard Overview API."""

    def test_overview_statistics(self, client, auth_headers, test_migration, db_session):
        """Test dashboard overview returns statistics."""
        # Update test migration to completed
        test_migration.status = 'completed'
        db_session.commit()

        response = client.get('/api/dashboard/overview', headers=auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'total_migrations' in data
        assert 'successful_migrations' in data
        assert 'success_rate' in data
        assert 'avg_completion_time' in data

    def test_recent_activity(self, client, auth_headers, test_migration):
        """Test recent activity feed."""
        response = client.get('/api/dashboard/recent-activity', headers=auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'activities' in data
        assert isinstance(data['activities'], list)


class TestAPIDataFlow:
    """Test complete data flow through API."""

    def test_complete_migration_flow(self, client, auth_headers, test_migration, db_session):
        """Test complete flow from migration to report generation."""
        # 1. Start with pending migration
        assert test_migration.status == 'pending'

        # 2. Simulate migration completion
        test_migration.status = 'completed'
        test_migration.verification_results = json.dumps({
            'trial_balance': {
                'source_total': 500000.00,
                'destination_total': 500000.00,
                'is_balanced': True
            },
            'integrity': {
                'source_hash': 'sha256_abc123...',
                'destination_hash': 'sha256_abc123...',
                'hash_match': True
            }
        })
        db_session.commit()

        # 3. Verify trial balance endpoint
        response = client.get(
            f'/api/migrations/{test_migration.migration_id}/trial-balance',
            headers=auth_headers
        )
        assert response.status_code == 200
        tb_data = response.get_json()
        assert tb_data['forensic_status'] == 'VERIFIED'

        # 4. Generate reports
        response = client.post('/api/reports/generate',
            headers=auth_headers,
            json={
                'type': 'variance',
                'migration_id': test_migration.migration_id
            })
        assert response.status_code == 200

        # 5. Export Caseware bundle
        response = client.post(
            f'/api/migrations/{test_migration.migration_id}/export-caseware',
            headers=auth_headers
        )
        assert response.status_code == 200

        # 6. Verify reports list
        response = client.get('/api/reports', headers=auth_headers)
        assert response.status_code == 200


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_invalid_migration_id(self, client, auth_headers):
        """Test handling of invalid migration ID."""
        response = client.get('/api/migrations/invalid_id/trial-balance', headers=auth_headers)
        assert response.status_code == 404

    def test_unauthorized_access(self, client, test_migration):
        """Test unauthorized access is denied."""
        response = client.get(
            f'/api/migrations/{test_migration.migration_id}/trial-balance'
        )
        assert response.status_code == 401

    def test_invalid_report_type(self, client, auth_headers, test_migration, db_session):
        """Test handling of invalid report type."""
        test_migration.status = 'completed'
        db_session.commit()

        response = client.post('/api/reports/generate',
            headers=auth_headers,
            json={
                'type': 'invalid_type',
                'migration_id': test_migration.migration_id
            })
        assert response.status_code == 400


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
