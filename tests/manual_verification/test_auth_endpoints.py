"""
Test script for authentication and configuration endpoints
"""
import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_login():
    """Test login endpoint"""
    print("=" * 60)
    print("Testing Login Endpoint")
    print("=" * 60)
    
    url = f"{BASE_URL}/auth/login"
    payload = {
        "username": "juank8911",
        "password": "juank8911"
    }
    
    try:
        response = requests.post(url, json=payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        # Check if cookie was set
        if 'manus.sid' in response.cookies:
            print(f"✅ Cookie set: manus.sid")
            return response.cookies['manus.sid']
        else:
            print("❌ No cookie set")
            return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def test_auth_me(token):
    """Test /auth/me endpoint"""
    print("\n" + "=" * 60)
    print("Testing /auth/me Endpoint")
    print("=" * 60)
    
    url = f"{BASE_URL}/auth/me"
    cookies = {'manus.sid': token}
    
    try:
        response = requests.get(url, cookies=cookies)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("✅ Authentication successful")
            return response.json()
        else:
            print("❌ Authentication failed")
            return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def test_get_config(user_id, token):
    """Test GET /config/{user_id} endpoint"""
    print("\n" + "=" * 60)
    print("Testing GET /config/{user_id} Endpoint")
    print("=" * 60)
    
    url = f"{BASE_URL}/config/{user_id}"
    cookies = {'manus.sid': token}
    
    try:
        response = requests.get(url, cookies=cookies)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("✅ Config retrieved successfully")
            return response.json()
        else:
            print("❌ Failed to retrieve config")
            return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def test_logout(token):
    """Test logout endpoint"""
    print("\n" + "=" * 60)
    print("Testing Logout Endpoint")
    print("=" * 60)
    
    url = f"{BASE_URL}/auth/logout"
    cookies = {'manus.sid': token}
    
    try:
        response = requests.post(url, cookies=cookies)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("✅ Logout successful")
            return True
        else:
            print("❌ Logout failed")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("\n🚀 Starting Authentication Flow Tests\n")
    
    # Test 1: Login
    token = test_login()
    if not token:
        print("\n❌ Login failed, stopping tests")
        exit(1)
    
    # Test 2: Get current user
    user_data = test_auth_me(token)
    if not user_data:
        print("\n❌ Auth check failed, stopping tests")
        exit(1)
    
    user_id = user_data.get('user', {}).get('openId')
    if not user_id:
        print("\n❌ No user ID found, stopping tests")
        exit(1)
    
    # Test 3: Get user config
    config = test_get_config(user_id, token)
    
    # Test 4: Logout
    test_logout(token)
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)
