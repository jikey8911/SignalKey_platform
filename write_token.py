
import jwt
import datetime

token = jwt.encode(
    {'openId': 'test', 'appId': 'test', 'name': 'test', 'exp': datetime.datetime.utcnow() + datetime.timedelta(days=1)},
    'dev-secret-key-123',
    algorithm='HS256'
)

with open('full_token.txt', 'w') as f:
    f.write(token)
print("Token written to full_token.txt")
