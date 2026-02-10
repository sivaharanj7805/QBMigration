import json

import requests

API_URL = "http://localhost:5000"

# Test registration
test_data = {
    "email": f"testuser_{int(__import__('time').time())}@example.com",
    "password": "TestPassword123!",
    "first_name": "Test",
    "last_name": "User",
    "company": "Test Company",
}

print(f"Testing registration with: {test_data['email']}")

try:
    response = requests.post(
        f"{API_URL}/api/auth/register",
        json=test_data,
        headers={"Content-Type": "application/json"},
    )

    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

except requests.exceptions.ConnectionError:
    print("ERROR: Cannot connect to server. Is Flask running?")
except Exception as e:
    print(f"ERROR: {e}")
