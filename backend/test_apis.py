"""
Test script to verify all backend API endpoints
Run this script to test if the backend is working correctly
"""

import requests
import json
import time

BASE_URL = "http://localhost:5000/api"

def print_response(title, response):
    """Pretty print API response"""
    print(f"\n{'='*50}")
    print(f"TEST: {title}")
    print(f"{'='*50}")
    print(f"Status Code: {response.status_code}")
    try:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except:
        print(f"Response: {response.text}")

def test_health():
    """Test health endpoint"""
    response = requests.get(f"{BASE_URL}/health")
    print_response("Health Check", response)
    return response.status_code == 200

def test_signup():
    """Test signup endpoint"""
    payload = {
        "email": f"testuser{int(time.time())}@example.com",
        "password": "password123",
        "fullName": "Test User",
        "role": "patient"
    }
    response = requests.post(f"{BASE_URL}/auth/signup", json=payload)
    print_response("User Signup", response)
    
    if response.status_code == 201:
        return response.json()
    return None

def test_login(email, password):
    """Test login endpoint"""
    payload = {
        "email": email,
        "password": password
    }
    response = requests.post(f"{BASE_URL}/auth/login", json=payload)
    print_response("User Login", response)
    
    if response.status_code == 200:
        return response.json()
    return None

def test_update_profile(token):
    """Test profile update endpoint"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "date_of_birth": "1990-01-01",
        "blood_type": "O+",
        "address": "123 Test Street",
        "emergency_contact": "Jane Doe",
        "emergency_phone": "123-456-7890"
    }
    response = requests.post(
        f"{BASE_URL}/auth/update-patient-profile",
        json=payload,
        headers=headers
    )
    print_response("Update Patient Profile", response)
    return response.status_code == 200

def main():
    """Run all tests"""
    print("\n" + "🧪 "*25)
    print("PULSESYNC BACKEND API TESTS")
    print("🧪 "*25)
    
    # Test 1: Health check
    if not test_health():
        print("\n❌ Backend is not running!")
        print("Start the backend with: python app.py")
        return
    
    print("\n✓ Backend is running!")
    
    # Test 2: Signup
    signup_response = test_signup()
    if not signup_response:
        print("\n❌ Signup failed!")
        return
    
    user_email = signup_response.get('user_id')
    token = signup_response.get('token')
    
    # For login test, create a test user first
    test_email = f"logintest{int(time.time())}@example.com"
    test_password = "password123"
    
    # Create test user
    signup_payload = {
        "email": test_email,
        "password": test_password,
        "fullName": "Login Test User",
        "role": "patient"
    }
    requests.post(f"{BASE_URL}/auth/signup", json=signup_payload)
    
    # Test 3: Login
    login_response = test_login(test_email, test_password)
    if not login_response:
        print("\n❌ Login failed!")
        return
    
    token = login_response.get('token')
    
    # Test 4: Update profile (requires valid token)
    if token:
        test_update_profile(token)
    
    print("\n" + "="*50)
    print("✓ ALL TESTS COMPLETED!")
    print("="*50 + "\n")

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print("\n❌ Cannot connect to backend!")
        print("Make sure the backend is running on http://localhost:5000")
        print("Start it with: python app.py")
    except Exception as e:
        print(f"\n❌ Error: {e}")
