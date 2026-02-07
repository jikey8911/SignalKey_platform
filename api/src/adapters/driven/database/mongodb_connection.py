from api.src.adapters.driven.persistence.mongodb import get_database as persistence_get_database
from motor.motor_asyncio import AsyncIOMotorDatabase

async def get_database() -> AsyncIOMotorDatabase:
    """
    Get MongoDB database instance (delegated to persistence.mongodb for standardization).
    """
    return get_database_sync()

def get_database_sync() -> AsyncIOMotorDatabase:
    """Synchronous access to the database instance (from persistence.mongodb)"""
    from api.src.adapters.driven.persistence.mongodb import db
    return db

async def close_database():
    """Close MongoDB connection (Stub, as lifecycle is managed globally or in persistence)"""
    pass
