"""
Pytest configuration and fixtures for QB Migration Server tests
Ensures isolated, repeatable tests with proper database management
"""

import pytest
import sys
import os
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy import text
import logging

# Add parent directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from models.database import db
from models.user import User
from models.migration import Migration

# Configure logging for tests
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


@pytest.fixture(scope='session')
def app():
    """
    Create application for testing (session-scoped)
    
    SAFETY CHECKS:
    - Ensures testing environment
    - Validates test database connection
    - Prevents accidental production database usage
    """
    # SAFETY: Force testing environment
    os.environ['FLASK_ENV'] = 'testing'
    
    # Create test app
    app = create_app('testing')
    
    # SAFETY CHECK 1: Verify we're using test database
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if 'qbmigration_test' not in db_uri and 'test' not in db_uri and 'sqlite' not in db_uri:
        raise RuntimeError(
            f"DANGER: Not using test database! Current DB: {db_uri}\n"
            f"Expected database name to contain 'test' or 'qbmigration_test'"
        )
    
    # SAFETY CHECK 2: Verify testing mode enabled
    if not app.config['TESTING']:
        raise RuntimeError("TESTING flag not set to True in app config!")
    
    # SAFETY CHECK 3: Verify rate limiting disabled for tests
    if app.config.get('RATELIMIT_ENABLED', False):
        logger.warning("Rate limiting is enabled in tests - this may cause failures")
    
    # Push application context for entire test session
    ctx = app.app_context()
    ctx.push()
    
    # Create all tables
    try:
        db.create_all()
        logger.info(f"Test database tables created: {db_uri}")
    except Exception as e:
        ctx.pop()
        raise RuntimeError(f"Failed to create test database tables: {str(e)}")
    
    # SAFETY CHECK 4: Verify tables were created
    inspector = db.inspect(db.engine)
    tables = inspector.get_table_names()
    required_tables = {'users', 'migrations'}
    
    if not required_tables.issubset(set(tables)):
        missing = required_tables - set(tables)
        ctx.pop()
        raise RuntimeError(f"Required tables not created: {missing}")
    
    logger.info(f"Test database ready with tables: {tables}")
    
    yield app
    
    # Cleanup after all tests
    try:
        db.session.remove()
        db.drop_all()
        logger.info("Test database cleaned up successfully")
    except Exception as e:
        logger.error(f"Cleanup error: {str(e)}")
    finally:
        ctx.pop()


@pytest.fixture(scope='function')
def client(app):
    """
    Create Flask test client
    
    SAFETY: Each test gets fresh client with clean cookies/session
    """
    with app.test_client() as client:
        yield client


@pytest.fixture(scope='function', autouse=True)
def db_session(app):
    """
    Create clean database session for each test.
    
    PRODUCTION-GRADE APPROACH:
    - Truncates all tables before each test
    - No complex transaction nesting
    - Data is actually visible within tests
    - Clean slate for each test
    """
    # Clear all data before test
    for table in reversed(db.metadata.sorted_tables):
        try:
            db.session.execute(table.delete())
        except Exception:
            pass
    db.session.commit()
    
    yield db.session
    
    # Clear all data after test
    for table in reversed(db.metadata.sorted_tables):
        try:
            db.session.execute(table.delete())
        except Exception:
            pass
    db.session.commit()




@pytest.fixture
def test_user(db_session):
    """
    Create test user for authentication tests
    
    SAFETY FEATURES:
    - User is created in isolated transaction
    - Properly bound to session (no detached instance errors)
    - Automatically cleaned up after test
    - Password strength validated
    """
    # SAFETY CHECK: Verify session is active
    if not db_session.is_active:
        raise RuntimeError("Database session is not active!")
    
    # Create user with validated password
    user = User(
        email='test@example.com',
        first_name='Test',
        last_name='User',
        company_name='Test Company'
    )
    
    try:
        # This will raise ValueError if password is weak
        user.set_password('Test1234')
    except ValueError as e:
        raise RuntimeError(f"Test user password failed validation: {str(e)}")
    
    # Add to session and commit
    db_session.add(user)
    
    try:
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        raise RuntimeError(f"Failed to create test user: {str(e)}")
    
    # SAFETY: Refresh to load all attributes and ensure session binding
    db_session.refresh(user)
    
    # SAFETY CHECK: Verify user was created
    if not user.id:
        raise RuntimeError("Test user was not assigned an ID!")
    
    # SAFETY CHECK: Verify user is in session
    if user not in db_session:
        raise RuntimeError("Test user is not in database session!")
    
    logger.debug(f"Test user created: {user.email} (ID: {user.id})")
    
    return user


@pytest.fixture
def authenticated_client(client, test_user):
    """
    Create authenticated test client
    
    Convenience fixture for tests that need pre-authenticated requests
    
    Usage:
        def test_something(authenticated_client):
            response = authenticated_client.get('/api/protected')
            # Already logged in as test_user
    """
    # Login the test user
    response = client.post('/api/auth/login', json={
        'email': 'test@example.com',
        'password': 'Test1234'
    })
    
    # SAFETY CHECK: Verify login succeeded
    if response.status_code != 200:
        raise RuntimeError(f"Test user login failed: {response.data}")
    
    return client


@pytest.fixture
def test_migration(db_session, test_user):
    """
    Create test migration for migration-related tests
    
    SAFETY: Properly bound to session, automatically cleaned up
    """
    migration = Migration(
        user_id=test_user.id,
        company_name='Test Company',
        qb_file_name='test.qbw',
        data_size_bytes=1000000,
        status='pending'
    )
    
    db_session.add(migration)
    
    try:
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        raise RuntimeError(f"Failed to create test migration: {str(e)}")
    
    db_session.refresh(migration)
    
    # SAFETY CHECK: Verify migration was created
    if not migration.migration_id:
        raise RuntimeError("Test migration was not assigned an ID!")
    
    return migration


# ============================================================================
# PYTEST CONFIGURATION
# ============================================================================

def pytest_configure(config):
    """
    Pytest configuration hook
    
    SAFETY: Adds custom markers and validates test environment
    """
    # Register custom markers
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "requires_aws: marks tests that require AWS credentials"
    )


def pytest_collection_modifyitems(config, items):
    """
    Modify test collection
    
    SAFETY: Skip AWS tests if credentials not available
    """
    skip_aws = pytest.mark.skip(reason="AWS credentials not configured")
    
    for item in items:
        if "requires_aws" in item.keywords:
            # Check if AWS credentials are available
            if not os.getenv('AWS_ACCESS_KEY_ID'):
                item.add_marker(skip_aws)


@pytest.fixture(scope='session', autouse=True)
def verify_test_environment():
    """
    Verify test environment setup before running any tests
    
    SAFETY: Prevents tests from running in unsafe conditions
    """
    # SAFETY CHECK 1: Verify we're not in production
    if os.getenv('FLASK_ENV') == 'production':
        raise RuntimeError("DANGER: Cannot run tests in production environment!")
    
    # SAFETY CHECK 2: Verify PostgreSQL is accessible
    try:
        from app import create_app
        test_app = create_app('testing')
        with test_app.app_context():
            db.session.execute(text('SELECT 1'))
    except Exception as e:
        raise RuntimeError(
            f"Cannot connect to test database!\n"
            f"Error: {str(e)}\n"
            f"Make sure PostgreSQL is running and test database exists."
        )
    
    # SAFETY CHECK 3: Warn about missing encryption key
    if not os.getenv('BACKUP_ENCRYPTION_KEY'):
        logger.warning(
            "BACKUP_ENCRYPTION_KEY not set - encryption tests may fail"
        )
    
    logger.info("✅ Test environment verification passed")
    
    yield
    
    logger.info("✅ All tests completed")


# ============================================================================
# HELPER FUNCTIONS FOR TESTS
# ============================================================================

@pytest.fixture
def fake_encrypted_data():
    """
    Generate fake encrypted data for upload tests
    
    Returns properly formatted encrypted data that passes validation
    """
    return "IV:test123456789:TAG:abcdef123456:CIPHER:" + ("x" * 500) + ":KEY:test"


@pytest.fixture
def fake_qbo_credentials():
    """Generate fake QBO credentials for testing"""
    return {
        'client_id': 'test_client_id',
        'client_secret': 'test_client_secret',
        'refresh_token': 'test_refresh_token',
        'realm_id': 'test_realm_id'
    }