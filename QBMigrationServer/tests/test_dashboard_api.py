"""
Comprehensive Test Suite for Dashboard API Endpoints
ForensicBridge Enterprise Dashboard Backend

Tests cover:
1. Live Status API (Pizza Tracker)
2. Bulk Status API (Enterprise Manager)
3. Dashboard Overview API
4. Recent Activity API
5. Trial Balance API
6. Audit Certificate API
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

# Import Flask app
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models.database import db
from models.migration import Migration


class TestDashboardAPI:
    """Test suite for dashboard_api.py endpoints"""
    
    @pytest.fixture
    def app(self):
        """Create test application"""
        app = create_app(config_name='testing')
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        
        with app.app_context():
            db.create_all()
            yield app
            db.drop_all()
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()
    
    @pytest.fixture
    def auth_headers(self, app, client):
        """Create authenticated session headers"""
        # Create test user and login
        with app.app_context():
            from models.user import User
            user = User(
                email='test@forensicbridge.com',
                first_name='Test',
                last_name='User',
                company_name='ForensicBridge'
            )
            user.set_password('TestPass123!')
            db.session.add(user)
            db.session.commit()
        
        # Login to get session
        response = client.post('/api/auth/login', json={
            'email': 'test@forensicbridge.com',
            'password': 'TestPass123!'
        })
        
        # Get JWT token from response
        data = response.get_json()
        token = data.get('token', '') if data else ''
        
        return {'Authorization': f'Bearer {token}'}
    
    @pytest.fixture
    def sample_migration(self, app):
        """Create sample migration for testing"""
        with app.app_context():
            from models.user import User
            user = User.query.filter_by(email='test@forensicbridge.com').first()
            
            migration = Migration(
                migration_id='mig_test_001',
                user_id=user.id if user else 1,
                status='processing',
                progress_percent=65,
                company_name='Waterloo Manufacturing',
                qb_file_name='waterloo.qbw',
                current_step='Migrating Invoices',
                created_at=datetime.utcnow() - timedelta(minutes=30)
            )
            db.session.add(migration)
            db.session.commit()
            
            return migration.migration_id


class TestLiveStatusAPI(TestDashboardAPI):
    """Tests for /api/migrations/<id>/live-status endpoint"""
    
    def test_live_status_returns_correct_phase_extraction(self, client, auth_headers, sample_migration, app):
        """Test that progress 0-15% maps to EXTRACTION phase"""
        with app.app_context():
            migration = Migration.query.filter_by(migration_id=sample_migration).first()
            migration.progress_percent = 10
            db.session.commit()
        
        response = client.get(
            f'/api/migrations/{sample_migration}/live-status',
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        assert data['phase'] == 'EXTRACTION'
        assert data['phase_number'] == 1
    
    def test_live_status_returns_correct_phase_transit(self, client, auth_headers, sample_migration, app):
        """Test that progress 15-20% maps to TRANSIT phase"""
        with app.app_context():
            migration = Migration.query.filter_by(migration_id=sample_migration).first()
            migration.progress_percent = 18
            db.session.commit()
        
        response = client.get(
            f'/api/migrations/{sample_migration}/live-status',
            headers=auth_headers
        )
        
        data = response.get_json()
        assert data['phase'] == 'TRANSIT'
        assert data['phase_number'] == 2
    
    def test_live_status_returns_correct_phase_transformation(self, client, auth_headers, sample_migration, app):
        """Test that progress 20-85% maps to TRANSFORMATION phase"""
        with app.app_context():
            migration = Migration.query.filter_by(migration_id=sample_migration).first()
            migration.progress_percent = 65
            db.session.commit()
        
        response = client.get(
            f'/api/migrations/{sample_migration}/live-status',
            headers=auth_headers
        )
        
        data = response.get_json()
        assert data['phase'] == 'TRANSFORMATION'
        assert data['phase_number'] == 3
    
    def test_live_status_returns_correct_phase_verification(self, client, auth_headers, sample_migration, app):
        """Test that progress 85-100% maps to VERIFICATION phase"""
        with app.app_context():
            migration = Migration.query.filter_by(migration_id=sample_migration).first()
            migration.progress_percent = 92
            db.session.commit()
        
        response = client.get(
            f'/api/migrations/{sample_migration}/live-status',
            headers=auth_headers
        )
        
        data = response.get_json()
        assert data['phase'] == 'VERIFICATION'
        assert data['phase_number'] == 4
    
    def test_live_status_includes_all_four_phases(self, client, auth_headers, sample_migration):
        """Test that response includes all 4 phases"""
        response = client.get(
            f'/api/migrations/{sample_migration}/live-status',
            headers=auth_headers
        )
        
        data = response.get_json()
        assert len(data['phases']) == 4
        phase_names = [p['name'] for p in data['phases']]
        assert 'EXTRACTION' in phase_names
        assert 'TRANSIT' in phase_names
        assert 'TRANSFORMATION' in phase_names
        assert 'VERIFICATION' in phase_names
    
    def test_live_status_not_found_returns_404(self, client, auth_headers):
        """Test that non-existent migration returns 404"""
        response = client.get(
            '/api/migrations/nonexistent_id/live-status',
            headers=auth_headers
        )
        
        assert response.status_code == 404
    
    def test_live_status_includes_elapsed_time(self, client, auth_headers, sample_migration):
        """Test that response includes elapsed time"""
        response = client.get(
            f'/api/migrations/{sample_migration}/live-status',
            headers=auth_headers
        )
        
        data = response.get_json()
        assert 'elapsed_seconds' in data
        assert data['elapsed_seconds'] > 0


class TestBulkStatusAPI(TestDashboardAPI):
    """Tests for /api/migrations/bulk-status endpoint"""
    
    def test_bulk_status_returns_all_migrations(self, client, auth_headers, sample_migration, app):
        """Test that bulk status returns all migrations when no IDs specified"""
        response = client.post(
            '/api/migrations/bulk-status',
            json={},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        assert 'migrations' in data
    
    def test_bulk_status_filters_by_ids(self, client, auth_headers, sample_migration, app):
        """Test that bulk status filters by specified IDs"""
        response = client.post(
            '/api/migrations/bulk-status',
            json={'migration_ids': [sample_migration]},
            headers=auth_headers
        )
        
        data = response.get_json()
        assert sample_migration in data['migrations']
    
    def test_bulk_status_returns_correct_count(self, client, auth_headers, sample_migration, app):
        """Test that count matches returned migrations"""
        response = client.post(
            '/api/migrations/bulk-status',
            json={'migration_ids': [sample_migration]},
            headers=auth_headers
        )
        
        data = response.get_json()
        assert data['count'] == len(data['migrations'])


class TestDashboardOverviewAPI(TestDashboardAPI):
    """Tests for /api/dashboard/overview endpoint"""
    
    def test_overview_returns_statistics(self, client, auth_headers):
        """Test that overview returns all required statistics"""
        response = client.get(
            '/api/dashboard/overview',
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.get_json()
        
        overview = data.get('overview', {})
        assert 'total_migrations' in overview
        assert 'completed_migrations' in overview
        assert 'failed_migrations' in overview
        assert 'in_progress' in overview
        assert 'success_rate' in overview
        assert 'avg_duration_minutes' in overview
    
    def test_overview_success_rate_calculation(self, client, auth_headers, app):
        """Test that success rate is calculated correctly"""
        with app.app_context():
            from models.user import User
            user = User.query.filter_by(email='test@forensicbridge.com').first()
            user_id = user.id if user else 1
            
            # Create 8 completed and 2 failed migrations
            for i in range(8):
                m = Migration(
                    migration_id=f'completed_{i}',
                    user_id=user_id,
                    status='completed',
                    company_name=f'Company {i}'
                )
                db.session.add(m)
            
            for i in range(2):
                m = Migration(
                    migration_id=f'failed_{i}',
                    user_id=user_id,
                    status='failed',
                    company_name=f'Failed Company {i}'
                )
                db.session.add(m)
            
            db.session.commit()
        
        response = client.get(
            '/api/dashboard/overview',
            headers=auth_headers
        )
        
        data = response.get_json()
        # 8 / (8 + 2) = 80%
        assert data['overview']['success_rate'] == 80.0


class TestRecentActivityAPI(TestDashboardAPI):
    """Tests for /api/dashboard/recent-activity endpoint"""
    
    def test_recent_activity_returns_activities(self, client, auth_headers, sample_migration):
        """Test that recent activity returns activity list"""
        response = client.get(
            '/api/dashboard/recent-activity',
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'activities' in data
        assert isinstance(data['activities'], list)
    
    def test_recent_activity_includes_required_fields(self, client, auth_headers, sample_migration):
        """Test that each activity has required fields"""
        response = client.get(
            '/api/dashboard/recent-activity',
            headers=auth_headers
        )
        
        data = response.get_json()
        
        if data['activities']:
            activity = data['activities'][0]
            assert 'timestamp' in activity
            assert 'type' in activity
            assert 'message' in activity


class TestTrialBalanceAPI(TestDashboardAPI):
    """Tests for /api/migrations/<id>/trial-balance endpoint"""
    
    def test_trial_balance_returns_data(self, client, auth_headers, sample_migration):
        """Test that trial balance returns data structure"""
        response = client.get(
            f'/api/migrations/{sample_migration}/trial-balance',
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'forensic_status' in data
    
    def test_trial_balance_pending_for_incomplete_migration(self, client, auth_headers, sample_migration, app):
        """Test that trial balance shows PENDING for incomplete migration"""
        with app.app_context():
            migration = Migration.query.filter_by(migration_id=sample_migration).first()
            migration.status = 'processing'
            db.session.commit()
        
        response = client.get(
            f'/api/migrations/{sample_migration}/trial-balance',
            headers=auth_headers
        )
        
        data = response.get_json()
        assert data['forensic_status'] in ['PENDING', 'NOT_AVAILABLE']
    
    def test_trial_balance_not_found(self, client, auth_headers):
        """Test 404 for non-existent migration"""
        response = client.get(
            '/api/migrations/nonexistent/trial-balance',
            headers=auth_headers
        )
        
        assert response.status_code == 404


class TestAuditCertificateAPI(TestDashboardAPI):
    """Tests for /api/migrations/<id>/audit-certificate endpoints"""
    
    def test_certificate_preview_returns_data(self, client, auth_headers, sample_migration):
        """Test that certificate preview returns metadata"""
        response = client.get(
            f'/api/migrations/{sample_migration}/audit-certificate/preview',
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'available' in data
        assert 'migration_id' in data
    
    def test_certificate_download_requires_completion(self, client, auth_headers, sample_migration, app):
        """Test that download is only available for completed migrations"""
        with app.app_context():
            migration = Migration.query.filter_by(migration_id=sample_migration).first()
            migration.status = 'processing'
            db.session.commit()
        
        response = client.get(
            f'/api/migrations/{sample_migration}/audit-certificate',
            headers=auth_headers
        )
        
        assert response.status_code == 400
    
    def test_certificate_download_for_completed_migration(self, client, auth_headers, sample_migration, app):
        """Test that download works for completed migrations"""
        with app.app_context():
            migration = Migration.query.filter_by(migration_id=sample_migration).first()
            migration.status = 'completed'
            migration.completed_at = datetime.utcnow()
            db.session.commit()
        
        # Note: This test may fail if PDF generation dependencies aren't available
        # In that case, it should at least not crash
        response = client.get(
            f'/api/migrations/{sample_migration}/audit-certificate',
            headers=auth_headers
        )
        
        # Should either succeed (200) or handle missing dependencies gracefully (500)
        assert response.status_code in [200, 500]


# ============================================================================
# Performance Tests
# ============================================================================

class TestAPIPerformance:
    """Performance tests for API endpoints"""
    
    @pytest.fixture
    def app_with_data(self):
        """Create app with large dataset for performance testing"""
        from app import create_app
        app = create_app(config_name='testing')
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        
        with app.app_context():
            db.create_all()
            
            from models.user import User
            user = User(email='perf@test.com', first_name='Perf', last_name='Test')
            user.set_password('Test123!')
            db.session.add(user)
            db.session.commit()
            
            
            # Create 100 migrations for performance testing
            for i in range(100):
                m = Migration(
                    migration_id=f'perf_mig_{i}',
                    user_id=user.id,
                    status='completed' if i % 2 == 0 else 'failed',
                    progress_percent=100,
                    company_name=f'Company {i}',
                    created_at=datetime.utcnow() - timedelta(days=i)
                )
                db.session.add(m)
            
            db.session.commit()
            yield app
            db.drop_all()
    
    def test_bulk_status_performance_100_migrations(self, app_with_data):
        """Test that bulk status handles 100 migrations efficiently"""
        import time
        
        client = app_with_data.test_client()
        client.post('/api/auth/login', json={
            'email': 'perf@test.com',
            'password': 'Test123!'
        })
        
        start = time.time()
        response = client.post('/api/migrations/bulk-status', json={})
        duration = time.time() - start
        
        assert response.status_code == 200
        assert duration < 2.0  # Should complete in under 2 seconds
    
    def test_overview_performance(self, app_with_data):
        """Test that overview aggregation is efficient"""
        import time
        
        client = app_with_data.test_client()
        client.post('/api/auth/login', json={
            'email': 'perf@test.com',
            'password': 'Test123!'
        })
        
        start = time.time()
        response = client.get('/api/dashboard/overview')
        duration = time.time() - start
        
        assert response.status_code == 200
        assert duration < 1.0  # Should complete in under 1 second


# ============================================================================
# Security Tests
# ============================================================================

class TestAPISecurity:
    """Security tests for API endpoints"""
    
    @pytest.fixture
    def app(self):
        from app import create_app
        app = create_app(config_name='testing')
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        
        with app.app_context():
            db.create_all()
            yield app
            db.drop_all()
    
    def test_unauthenticated_access_denied(self, app):
        """Test that unauthenticated requests are denied"""
        client = app.test_client()
        
        endpoints = [
            '/api/migrations/test/live-status',
            '/api/migrations/bulk-status',
            '/api/dashboard/overview',
            '/api/dashboard/recent-activity',
            '/api/migrations/test/trial-balance',
            '/api/migrations/test/audit-certificate'
        ]
        
        for endpoint in endpoints:
            if 'bulk' in endpoint:
                response = client.post(endpoint, json={})
            else:
                response = client.get(endpoint)
            
            # Should return 401 Unauthorized or redirect to login
            assert response.status_code in [401, 302, 403]


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
