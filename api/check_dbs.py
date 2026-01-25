import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

LOCAL_URI = "mongodb://localhost:27017"
ATLAS_URI = os.getenv("MONGODB_URI")

async def check_databases():
    print("--- DIAGNOSTIC START ---")
    
    # Check Local
    try:
        local_client = AsyncIOMotorClient(LOCAL_URI)
        print(f"\n[LOCAL] Connecting to {LOCAL_URI}...")
        local_dbs = await local_client.list_database_names()
        print(f"[LOCAL] Databases found: {local_dbs}")
        
        for db_name in local_dbs:
            if db_name in ['admin', 'local', 'config']: continue
            db = local_client[db_name]
            cols = await db.list_collection_names()
            print(f"  - DB '{db_name}' collections: {cols}")
            for col in cols:
                count = await db[col].count_documents({})
                print(f"    - {col}: {count} docs")
                
    except Exception as e:
        print(f"[LOCAL] Error: {e}")

    # Check Atlas
    try:
        print(f"\n[ATLAS] Connecting to Atlas...")
        if not ATLAS_URI:
            print("[ATLAS] Error: MONGODB_URI not found in .env")
            return

        atlas_client = AsyncIOMotorClient(ATLAS_URI)
        atlas_dbs = await atlas_client.list_database_names()
        print(f"[ATLAS] Databases found: {atlas_dbs}")
        
        for db_name in atlas_dbs:
            if db_name in ['admin', 'local', 'config']: continue
            db = atlas_client[db_name]
            cols = await db.list_collection_names()
            print(f"  - DB '{db_name}' collections: {cols}")
            for col in cols:
                count = await db[col].count_documents({})
                print(f"    - {col}: {count} docs")

    except Exception as e:
        print(f"[ATLAS] Error: {e}")
        
    print("\n--- DIAGNOSTIC END ---")

if __name__ == "__main__":
    asyncio.run(check_databases())
