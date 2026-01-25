import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

ATLAS_URI = os.getenv("MONGODB_URI")
# Explicitly check signalkey_platform
ATLAS_DB_NAME = "signalkey_platform"

async def verify_new_db():
    print("--- VERIFICATION START ---")
    print(f"Checking Atlas DB: {ATLAS_DB_NAME}")
    
    if not ATLAS_URI:
        print("Error: MONGODB_URI missing")
        return

    try:
        client = AsyncIOMotorClient(ATLAS_URI)
        db = client[ATLAS_DB_NAME]
        
        # List collections
        cols = await db.list_collection_names()
        print(f"Collections found: {cols}")
        
        # Check users
        users = await db.users.find({}).to_list(10)
        print(f"\nUsers (Count: {len(users)}):")
        for u in users:
            print(f"  - {u.get('openId')} (ID: {u.get('_id')})")
            
        # Check logs count
        logs_count = await db.telegram_logs.count_documents({})
        print(f"\nTelegram Logs: {logs_count}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(verify_new_db())
