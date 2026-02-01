import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from bson import json_util
import json

async def inspect():
    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGODB_DB_NAME", "signalkey_platform")
    client = AsyncIOMotorClient(uri)
    db = client[db_name]
    
    collections = ["users", "app_configs", "virtual_balances"]
    for coll in collections:
        print(f"\n--- {coll} ---")
        docs = await db[coll].find().to_list(10)
        print(json.dumps(docs, indent=2, default=json_util.default))

if __name__ == "__main__":
    asyncio.run(inspect())
