
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGODB_URI = "mongodb://localhost:27017"
DB_NAME = "signalkey_platform"

async def check_users():
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[DB_NAME]
    users = await db.users.find({}).to_list(100)
    print(f"Found {len(users)} users:")
    for user in users:
        print(f" - ID: {user['_id']}, Username: {user.get('username')}, OpenID: {user.get('openId')}")

if __name__ == "__main__":
    asyncio.run(check_users())
