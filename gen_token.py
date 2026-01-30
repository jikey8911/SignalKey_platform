
import os
import jwt
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Use the unified secret
SECRET = "dev-secret-key-123"

# Simulate token generation exactly as in auth_router.py
payload = {
    'openId': 'juank8911',
    'appId': 'signalkey-dev',
    'name': 'juank8911',
    'exp': datetime.utcnow() + timedelta(days=365)
}

token = jwt.encode(payload, SECRET, algorithm="HS256")
print(token)
