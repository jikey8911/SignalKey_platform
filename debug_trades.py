import requests
import json

try:
    # 1. Login
    login_url = "http://localhost:8000/api/auth/login"
    login_data = {"username": "juank8911", "password": "juank8911"}
    session = requests.Session()
    response = session.post(login_url, json=login_data)
    
    if response.status_code != 200:
        print(f"Login failed: {response.text}")
        exit()
        
    token = response.json().get("token")
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Get Trades
    trades_url = "http://localhost:8000/api/telegram/trades"
    trades_res = session.get(trades_url, headers=headers)
    
    print(f"Status Code: {trades_res.status_code}")
    print("Response Data:")
    print(json.dumps(trades_res.json(), indent=2))

except Exception as e:
    print(f"Error: {e}")
