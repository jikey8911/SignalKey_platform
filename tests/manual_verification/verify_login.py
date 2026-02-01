import requests
import json
import sys

def test_login():
    url = "http://localhost:3000/api/auth/login"
    payload = {
        "username": "juank8911",
        "password": "juank8911"
    }
    headers = {"Content-Type": "application/json"}
    
    print(f"Testing login at {url}...")
    try:
        response = requests.post(url, json=payload, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ LOGIN SUCCESS")
            return True
        else:
            print("❌ LOGIN FAILED")
            return False
    except Exception as e:
        print(f"❌ CONNECTION ERROR: {e}")
        return False

if __name__ == "__main__":
    test_login()
