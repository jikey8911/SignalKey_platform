
import os
import jwt
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pathlib import Path

# Load env using the same logic as api/config.py
env_path = Path("api/.env")
load_dotenv(dotenv_path=env_path)

secret = os.getenv("JWT_SECRET")
print(f"DEBUG: JWT_SECRET from api/.env = [{secret}]")

if not secret:
    print("WARNING: JWT_SECRET is not set in api/.env!")

# Simulate token generation
payload = {
    'openId': 'test_user',
    'appId': 'signalkey-dev',
    'name': 'Test User',
    'exp': datetime.utcnow() + timedelta(days=1)
}

token = jwt.encode(payload, secret or "your-secret-key-change-in-production", algorithm="HS256")
print(f"DEBUG: Generated token = {token}")

# Try to decode it
try:
    decoded = jwt.decode(token, secret or "your-secret-key-change-in-production", algorithms=["HS256"])
    print(f"DEBUG: Decoded payload = {decoded}")
except Exception as e:
    print(f"ERROR: Decoding failed: {e}")
