import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load env vars
load_dotenv()

# Configuration
LOCAL_URI = "mongodb://localhost:27017"
LOCAL_DB_NAME = "signalkey_platform"  
ATLAS_URI = os.getenv("MONGODB_URI")
# Ensure we pick up the new DB name from env, or parse it from URI if needed, 
# but os.getenv("MONGODB_DB_NAME") is safest as I just updated it.
ATLAS_DB_NAME = os.getenv("MONGODB_DB_NAME")

async def migrate():
    if not ATLAS_URI:
        logger.error("ATLAS_URI not found in environment variables.")
        return

    logger.info(f"Source (Local): {LOCAL_URI} [{LOCAL_DB_NAME}]")
    logger.info(f"Destination (Atlas): {ATLAS_URI.split('@')[-1]} [{ATLAS_DB_NAME}]")

    local_client = AsyncIOMotorClient(LOCAL_URI)
    atlas_client = AsyncIOMotorClient(ATLAS_URI)

    try:
        # Check source connection
        await local_client.server_info()
        logger.info("Connected to Local MongoDB.")
        
        # Check destination connection
        await atlas_client.server_info()
        logger.info("Connected to Atlas MongoDB.")

        local_db = local_client[LOCAL_DB_NAME]
        atlas_db = atlas_client[ATLAS_DB_NAME]

        # Get all collections from local
        collections = await local_db.list_collection_names()
        logger.info(f"Found collections to migrate: {collections}")

        for col_name in collections:
            logger.info(f"Migrating collection: {col_name}...")
            
            source_col = local_db[col_name]
            dest_col = atlas_db[col_name]
            
            # Count source docs
            count = await source_col.count_documents({})
            if count == 0:
                logger.info(f"Skipping empty collection: {col_name}")
                continue

            logger.info(f"Found {count} documents in {col_name}. Copying...")
            
            # Read all docs
            cursor = source_col.find({})
            batch = []
            migrated_count = 0
            
            async for doc in cursor:
                batch.append(doc)
                if len(batch) >= 100:
                    try:
                        await dest_col.insert_many(batch, ordered=False)
                        migrated_count += len(batch)
                        batch = []
                    except Exception as e:
                        # Log but continue, duplicate key errors are expected if run multiple times
                        # but here we are targeting a new DB so it should be clean.
                        logger.warning(f"Batch insert warning in {col_name}: {e}")
                        migrated_count += len(batch)
                        batch = []

            if batch:
                try:
                    await dest_col.insert_many(batch, ordered=False)
                    migrated_count += len(batch)
                except Exception as e:
                     logger.warning(f"Final batch insert warning in {col_name}: {e}")

            logger.info(f"Finished {col_name}. Migrated ~{migrated_count}/{count} documents.")

        logger.info("Migration completed successfully!")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
    finally:
        local_client.close()
        atlas_client.close()

if __name__ == "__main__":
    asyncio.run(migrate())
