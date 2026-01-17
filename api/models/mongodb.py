import os
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from typing import Optional, List, Dict, Any
from bson import ObjectId

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB_NAME", "signalkey_platform")

client = AsyncIOMotorClient(MONGODB_URI)
db = client[DB_NAME]

class MongoModel:
    @classmethod
    async def get_by_id(cls, collection_name: str, id: str):
        return await db[collection_name].find_one({"_id": ObjectId(id)})

    @classmethod
    async def get_by_query(cls, collection_name: str, query: Dict[str, Any]):
        return await db[collection_name].find_one(query)

    @classmethod
    async def list_by_query(cls, collection_name: str, query: Dict[str, Any], limit: int = 50, sort: List = None):
        cursor = db[collection_name].find(query)
        if sort:
            cursor = cursor.sort(sort)
        return await cursor.to_list(length=limit)

    @classmethod
    async def create(cls, collection_name: str, data: Dict[str, Any]):
        data["createdAt"] = datetime.utcnow()
        result = await db[collection_name].insert_one(data)
        return str(result.inserted_id)

    @classmethod
    async def update(cls, collection_name: str, id: str, data: Dict[str, Any]):
        data["updatedAt"] = datetime.utcnow()
        await db[collection_name].update_one({"_id": ObjectId(id)}, {"$set": data})

    @classmethod
    async def upsert(cls, collection_name: str, query: Dict[str, Any], data: Dict[str, Any]):
        data["updatedAt"] = datetime.utcnow()
        await db[collection_name].update_one(query, {"$set": data, "$setOnInsert": {"createdAt": datetime.utcnow()}}, upsert=True)

# Helper functions for specific collections
async def get_app_config(user_id: str):
    """Get app config for user and ensure it has the correct structure"""
    import logging
    logger = logging.getLogger(__name__)
    
    # user_id can be the openId or the ObjectId string
    # First try by openId in users collection to get the ObjectId
    user = await db.users.find_one({"openId": user_id})
    if not user:
        return None
    
    config = await db.app_configs.find_one({"userId": user["_id"]})
    
    if config:
        # Migrar campo legacy si es necesario
        needs_migration = False
        
        # Si tiene geminiApiKey pero no aiApiKey, migrar
        if "geminiApiKey" in config and config.get("geminiApiKey") and not config.get("aiApiKey"):
            logger.info(f"Migrating legacy geminiApiKey to aiApiKey for user {user_id}")
            config["aiApiKey"] = config["geminiApiKey"]
            needs_migration = True
        
        # Si no tiene aiProvider definido, establecer gemini como default
        if "aiProvider" not in config:
            logger.info(f"Setting default aiProvider=gemini for user {user_id}")
            config["aiProvider"] = "gemini"
            needs_migration = True
        
        # Actualizar en la base de datos si hubo cambios
        if needs_migration:
            await db.app_configs.update_one(
                {"userId": user["_id"]},
                {"$set": {
                    "aiApiKey": config.get("aiApiKey"),
                    "aiProvider": config.get("aiProvider", "gemini")
                }}
            )
    
    return config

async def save_trade(trade_data: Dict[str, Any]):
    trade_data["createdAt"] = datetime.utcnow()
    return await db.trades.insert_one(trade_data)

async def update_virtual_balance(user_id: str, market_type: str, asset: str, amount: float):
    user = await db.users.find_one({"openId": user_id})
    if not user:
        return
    await db.virtual_balances.update_one(
        {"userId": user["_id"], "marketType": market_type, "asset": asset},
        {"$set": {"amount": amount, "updatedAt": datetime.utcnow()}},
        upsert=True
    )
