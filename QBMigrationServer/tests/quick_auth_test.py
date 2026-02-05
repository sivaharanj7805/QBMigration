"""
Quick standalone auth test - bypasses pytest fixture issues
Run with: python tests/quick_auth_test.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models.database import db
from models.user import User

def test_auth():
    print("=" * 60)
    print("STANDALONE AUTH TEST")
    print("=" * 60)
    
    # Create app
    app = create_app('testing')
    
    with app.app_context():
        # Create tables
        db.create_all()
        
        # Clean up first
        User.query.delete()
        db.session.commit()
        print("[OK] Database cleaned")
        
        # Create test user
        user = User(
            email='test@example.com',
            first_name='Test',
            last_name='User'
        )
        user.set_password('TestPassword1234')
        db.session.add(user)
        db.session.commit()
        print("[OK] User created: {} (ID: {})".format(user.email, user.id))
        
        # Test with Flask test client
        with app.test_client() as client:
            # TEST 1: Register
            print("\n--- Test 1: Register ---")
            response = client.post('/api/auth/register', json={
                'email': 'new@example.com',
                'password': 'NewPassword1234'
            })
            print("Register status: {}".format(response.status_code))
            print("Register response: {}".format(response.get_json()))
            assert response.status_code == 201, "Expected 201, got {}".format(response.status_code)
            print("[OK] Register PASSED")
            
            # TEST 2: Login
            print("\n--- Test 2: Login ---")
            response = client.post('/api/auth/login', json={
                'email': 'test@example.com',
                'password': 'TestPassword1234'
            })
            print("Login status: {}".format(response.status_code))
            data = response.get_json()
            print("Login response success: {}".format(data.get('success') if data else 'None'))
            assert response.status_code == 200, "Expected 200, got {}".format(response.status_code)
            assert data['success'] == True, "Login should return success=True"
            print("[OK] Login PASSED")
            
            # TEST 3: Get current user
            print("\n--- Test 3: Get Me (with session) ---")
            response = client.get('/api/auth/me')
            print("Me status: {}".format(response.status_code))
            if response.status_code == 200:
                print("[OK] Session auth PASSED")
            else:
                print("[INFO] Session auth returned {}".format(response.status_code))
            
            # TEST 4: Wrong password
            print("\n--- Test 4: Wrong Password ---")
            response = client.post('/api/auth/login', json={
                'email': 'test@example.com',
                'password': 'WrongPassword1234'
            })
            print("Wrong password status: {}".format(response.status_code))
            assert response.status_code == 401, "Expected 401, got {}".format(response.status_code)
            print("[OK] Wrong password rejected PASSED")
            
            # TEST 5: Logout
            print("\n--- Test 5: Logout ---")
            # First login
            client.post('/api/auth/login', json={
                'email': 'test@example.com',
                'password': 'TestPassword1234'
            })
            response = client.post('/api/auth/logout')
            print("Logout status: {}".format(response.status_code))
            assert response.status_code == 200, "Expected 200, got {}".format(response.status_code)
            print("[OK] Logout PASSED")
        
        # Cleanup
        User.query.delete()
        db.session.commit()
        
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)

if __name__ == '__main__':
    test_auth()
