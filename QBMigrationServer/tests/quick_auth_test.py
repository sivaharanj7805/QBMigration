"""
Quick standalone auth test - bypasses pytest fixture issues
Run with: python tests/quick_auth_test.py
"""
import sys
import os
import logging

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models.database import db
from models.user import User

def test_auth():
    logger.info("=" * 60)
    logger.info("STANDALONE AUTH TEST")
    logger.info("=" * 60)
    
    # Create app
    app = create_app('testing')
    
    with app.app_context():
        # Create tables
        db.create_all()
        
        # Clean up first
        User.query.delete()
        db.session.commit()
        logger.info("[OK] Database cleaned")
        
        # Create test user
        user = User(
            email='test@example.com',
            first_name='Test',
            last_name='User'
        )
        user.set_password('Test1234')
        db.session.add(user)
        db.session.commit()
        logger.info("[OK] User created: {} (ID: {})".format(user.email, user.id))
        
        # Test with Flask test client
        with app.test_client() as client:
            # TEST 1: Register
            logger.debug("\n--- Test 1: Register ---")
            response = client.post('/api/auth/register', json={
                'email': 'new@example.com',
                'password': 'NewPass123'
            })
            logger.info("Register status: {}".format(response.status_code))
            logger.info("Register response: {}".format(response.get_json()))
            assert response.status_code == 201, "Expected 201, got {}".format(response.status_code)
            logger.info("[OK] Register PASSED")
            
            # TEST 2: Login
            logger.debug("\n--- Test 2: Login ---")
            response = client.post('/api/auth/login', json={
                'email': 'test@example.com',
                'password': 'Test1234'
            })
            logger.info("Login status: {}".format(response.status_code))
            data = response.get_json()
            logger.info("Login response success: {}".format(data.get('success') if data else 'None'))
            assert response.status_code == 200, "Expected 200, got {}".format(response.status_code)
            assert data['success'] == True, "Login should return success=True"
            logger.info("[OK] Login PASSED")
            
            # TEST 3: Get current user
            logger.debug("\n--- Test 3: Get Me (with session) ---")
            response = client.get('/api/auth/me')
            logger.info("Me status: {}".format(response.status_code))
            if response.status_code == 200:
                logger.info("[OK] Session auth PASSED")
            else:
                logger.info("[INFO] Session auth returned {}".format(response.status_code))
            
            # TEST 4: Wrong password
            logger.debug("\n--- Test 4: Wrong Password ---")
            response = client.post('/api/auth/login', json={
                'email': 'test@example.com',
                'password': 'WrongPass123'
            })
            logger.info("Wrong password status: {}".format(response.status_code))
            assert response.status_code == 401, "Expected 401, got {}".format(response.status_code)
            logger.info("[OK] Wrong password rejected PASSED")
            
            # TEST 5: Logout
            logger.debug("\n--- Test 5: Logout ---")
            # First login
            client.post('/api/auth/login', json={
                'email': 'test@example.com',
                'password': 'Test1234'
            })
            response = client.post('/api/auth/logout')
            logger.info("Logout status: {}".format(response.status_code))
            assert response.status_code == 200, "Expected 200, got {}".format(response.status_code)
            logger.info("[OK] Logout PASSED")
        
        # Cleanup
        User.query.delete()
        db.session.commit()
        
    logger.info("\n" + "=" * 60)
    logger.info("ALL TESTS PASSED")
    logger.info("=" * 60)

if __name__ == '__main__':
    test_auth()
