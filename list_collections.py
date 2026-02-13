
import asyncio
import os
import sys

# Ensure api module can be loaded
sys.path.append(os.getcwd())

from api.config import Config
from motor.motor_asyncio import AsyncIOMotorClient

async def list_collections():
    uri = Config.MONGODB_URI
    db_name = Config.MONGODB_DB_NAME
    print(f"Connecting to: {uri.split('@')[-1]} (HIDDEN CREDENTIALS)")
    print(f"Database: {db_name}")

    client = AsyncIOMotorClient(uri)
    db = client[db_name]
    
    try:
        collections = await db.list_collection_names()
        print(f"Collections found ({len(collections)}):")
        for name in sorted(collections):
            count = await db[name].count_documents({})
            print(f" - {name}: {count} documents")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(list_collections())
