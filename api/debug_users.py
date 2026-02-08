import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

LOCAL_URI = "mongodb://localhost:27017"
LOCAL_DB_NAME = "signalkey_platform"
ATLAS_URI = os.getenv("MONGODB_URI")
ATLAS_DB_NAME = os.getenv("MONGODB_DB_NAME")

async def compare_users():
    print("--- USER COMPARISON START ---")
     
    local_client = AsyncIOMotorClient(LOCAL_URI)
    atlas_client = AsyncIOMotorClient(ATLAS_URI)
    
    local_db = local_client[LOCAL_DB_NAME]
    atlas_db = atlas_client[ATLAS_DB_NAME]
    
    print(f"Local DB: {LOCAL_DB_NAME}")
    print(f"Atlas DB: {ATLAS_DB_NAME}")

    # Helper to print users
    async def print_users(db, label):
        print(f"\n[{label}] Users:")
        users = await db.users.find({}).to_list(length=100)
        user_map = {}
        for u in users:
            uid = str(u.get('_id'))
            openid = u.get('openId')
            print(f"  - _id: {uid}, openId: {openid}, name: {u.get('name')}")
            if openid:
                user_map[openid] = uid
        return user_map

    local_map = await print_users(local_db, "LOCAL")
    atlas_map = await print_users(atlas_db, "ATLAS")
    
    print("\n--- ANALYSIS ---")
    for openid, local_uid in local_map.items():
        if openid in atlas_map:
            atlas_uid = atlas_map[openid]
            if local_uid != atlas_uid:
                print(f"MISMATCH for '{openid}':")
                print(f"  Local ID: {local_uid}")
                print(f"  Atlas ID: {atlas_uid}")
                print(f"  -> Migrated data using Local ID {local_uid} is NOT visible to Atlas User {atlas_uid}")
            else:
                print(f"MATCH for '{openid}': IDs are identical.")
        else:
             print(f"MISSING in Atlas: '{openid}'")

    print("--- USER COMPARISON END ---")
    
    local_client.close()
    atlas_client.close()

if __name__ == "__main__":
    asyncio.run(compare_users())
