"""
MongoDB connection module for database access
"""
import os
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from api.config import Config

# Global client instance
_client: AsyncIOMotorClient = None
_db: AsyncIOMotorDatabase = None


async def get_database() -> AsyncIOMotorDatabase:
    """
    Get MongoDB database instance.
    Uses MONGODB_URI from environment variables.
    Returns the database specified in MONGODB_DB_NAME or defaults to 'signalkey_platform'.
    """
    global _client, _db
    
    if _db is not None:
        return _db
    
    # Initialize client if not exists
    if _client is None:
        mongodb_uri = Config.MONGODB_URI
        _client = AsyncIOMotorClient(mongodb_uri)
    
    # Get database name from env or use default
    db_name = os.getenv("MONGODB_DB_NAME", "signalkey_platform")
    _db = _client[db_name]
    
    return _db


async def close_database():
    """Close MongoDB connection"""
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
