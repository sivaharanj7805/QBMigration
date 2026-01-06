"""
Basic tests to verify setup
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def test_imports():
    """Test that we can import our modules"""
    try:
        from app import create_app
        from models.user import User
        from models.migration import Migration
        from models.database import db
        assert True
    except ImportError as e:
        assert False, f"Import failed: {str(e)}"


def test_config():
    """Test configuration loading"""
    from app import create_app
    
    app = create_app('testing')
    assert app is not None
    assert app.config['TESTING'] == True


def test_app_creation():
    """Test app creation"""
    from app import create_app
    
    app = create_app('testing')
    
    assert app.name == 'app'
    assert 'SQLALCHEMY_DATABASE_URI' in app.config


def test_routes_registered():
    """Test that routes are registered"""
    from app import create_app
    
    app = create_app('testing')
    
    # Get all registered routes
    routes = [str(rule) for rule in app.url_map.iter_rules()]
    
    # Check critical routes exist
    assert '/' in routes
    assert '/health' in routes
    assert any('auth' in route for route in routes)


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])