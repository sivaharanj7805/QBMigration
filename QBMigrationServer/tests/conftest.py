import pytest
import sys
import os

# Add parent directory to Python path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from models.user import User
from models.migration import Migration

@pytest.fixture(scope='session')
def app():
    """Create application for testing"""
    os.environ['FLASK_ENV'] = 'testing'
    app = create_app('testing')
    
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture(scope='function')
def client(app):
    """Create test client"""
    return app.test_client()

@pytest.fixture(scope='function')
def db_session(app):
    """Create database session for tests"""
    with app.app_context():
        db.session.begin_nested()
        yield db.session
        db.session.rollback()

@pytest.fixture
def test_user(db_session):
    """Create test user"""
    user = User(
        email='test@example.com',
        first_name='Test',
        last_name='User',
        company_name='Test Company'
    )
    user.set_password('Test1234')
    db_session.add(user)
    db_session.commit()
    return user