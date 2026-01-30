import requests

# Test backend login endpoint directly
url = "http://127.0.0.1:8000/auth/login"
payload = {"username": "juank8911", "password": "juank8911"}

print("Testing backend /auth/login endpoint...")
print(f"URL: {url}")
print(f"Payload: {payload}")

try:
    response = requests.post(url, json=payload)
    print(f"\nStatus Code: {response.status_code}")
    print(f"Response: {response.json()}")
    print(f"Cookies: {response.cookies}")
    
    if response.status_code == 200:
        print("\n✅ Backend login endpoint works!")
    else:
        print(f"\n❌ Backend returned error: {response.status_code}")
except Exception as e:
    print(f"\n❌ Error: {e}")
