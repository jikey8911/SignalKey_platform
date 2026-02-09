import asyncio
import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MigrationScript")

# MongoDB URI from environment or default
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://mongodb:27017")
DB_NAME = os.getenv("MONGODB_DB_NAME", "signalkey_db")

async def migrate_collection(db, collection_name, user_id_field="userId"):
    """
    Migrates string user IDs (openId) to ObjectId in the specified collection.
    """
    logger.info(f"Starting migration for collection: {collection_name} (field: {user_id_field})")
    collection = db[collection_name]
    users_collection = db["users"]

    # Find documents where user_id_field is a string (potential openId)
    # Note: We check if it's a string and NOT an ObjectId string representation that we just converted
    # But simpler: just find all documents and check type in python
    cursor = collection.find({})

    count = 0
    updated = 0
    errors = 0

    async for doc in cursor:
        count += 1
        user_id_val = doc.get(user_id_field)

        # Check if it's already an ObjectId
        if isinstance(user_id_val, ObjectId):
            continue

        # Check if it's a string that looks like an openId (not 24 hex chars, or 24 hex chars that is actually an openId)
        # However, openId can be anything. The key is to look it up in users collection by openId.

        if isinstance(user_id_val, str):
            # Try to find user by openId
            user = await users_collection.find_one({"openId": user_id_val})

            if user:
                # Found the user, update with ObjectId
                new_id = user["_id"]
                try:
                    await collection.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {user_id_field: new_id}}
                    )
                    updated += 1
                except Exception as e:
                    logger.error(f"Error updating document {doc['_id']}: {e}")
                    errors += 1
            else:
                # Fallback: maybe it's already an ObjectId string?
                if ObjectId.is_valid(user_id_val):
                     # If it's a valid ObjectId string, convert it to ObjectId type
                     try:
                        await collection.update_one(
                            {"_id": doc["_id"]},
                            {"$set": {user_id_field: ObjectId(user_id_val)}}
                        )
                        updated += 1
                     except Exception as e:
                        logger.error(f"Error converting string ObjectId for {doc['_id']}: {e}")
                        errors += 1
                else:
                    logger.warning(f"User not found for openId: {user_id_val} in doc {doc['_id']}")
                    errors += 1

        if count % 100 == 0:
            logger.info(f"Processed {count} documents in {collection_name}...")

    logger.info(f"Finished {collection_name}. Updated: {updated}, Errors: {errors}, Total Scanned: {count}")

    # Create Index
    logger.info(f"Creating index for {collection_name} on {user_id_field}...")
    await collection.create_index([(user_id_field, 1)])
    logger.info(f"Index created.")

async def main():
    logger.info("Connecting to MongoDB...")
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[DB_NAME]

    # Check connection
    try:
        await client.server_info()
        logger.info("Connected to MongoDB successfully.")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        return

    # Migrate collections
    # 1. bot_instances (uses 'user_id' based on schemas, but check repo)
    # checking repo: cursor = self.collection.find({"user_id": user_id}) -> uses 'user_id'
    await migrate_collection(db, "bot_instances", "user_id")

    # 2. trades (uses 'userId' in some places, check schema/repo)
    # trade_router: db.trades.find({"userId": user_id}) -> uses 'userId'
    await migrate_collection(db, "trades", "userId")

    # 3. positions (uses 'userId' based on ExecutionEngine)
    # ExecutionEngine: "userId": user_id
    await migrate_collection(db, "positions", "userId")

    # 4. virtual_balances (uses 'userId' based on ExecutionEngine/mongodb.py)
    # mongodb.py: {"userId": user["_id"]...}
    await migrate_collection(db, "virtual_balances", "userId")

    # 5. trading_signals (uses 'userId' based on repository)
    # MongoDBSignalRepository: "userId": ...
    await migrate_collection(db, "trading_signals", "userId")

    # 6. app_configs (uses 'userId' based on mongodb.py)
    await migrate_collection(db, "app_configs", "userId")

    logger.info("All migrations completed.")

if __name__ == "__main__":
    asyncio.run(main())
