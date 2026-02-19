import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from datetime import datetime
from typing import Optional, List, Dict, Any
from bson import ObjectId

from api.config import Config

logger = logging.getLogger(__name__)

# Global instances (Singleton pattern)
_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None

def get_database() -> AsyncIOMotorDatabase:
    """Standardized way to get the database instance"""
    global _client, _db
    if _db is not None:
        return _db
    
    if _client is None:
        uri = Config.MONGODB_URI
        if "localhost" in uri:
            logger.error("CRITICAL: Attempting to connect to LOCALHOST MongoDB! Expected Atlas.")
            # raise Exception("Safety Block: Refusing to connect to localhost DB in production mode") 
        
        safe_uri = uri.split('@')[-1] if '@' in uri else 'localhost'
        logger.info(f"MongoDB: Connecting to {safe_uri}...")
        _client = AsyncIOMotorClient(uri)
    
    _db = _client[Config.MONGODB_DB_NAME]
    return _db

# For legacy compatibility and quick access
client = AsyncIOMotorClient(Config.MONGODB_URI)
db = client[Config.MONGODB_DB_NAME]

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
async def get_app_config(user_id: Any):
    """Get app config for user and ensure it has the correct structure"""
    import logging
    logger = logging.getLogger(__name__)
    
    # Accept ObjectId or string (openId or hex)
    user = None
    if isinstance(user_id, ObjectId):
        user = await db.users.find_one({"_id": user_id})
    else:
        # Try finding by openId
        user = await db.users.find_one({"openId": user_id})
        # If not found, try as ObjectId string
        if not user and ObjectId.is_valid(user_id):
             user = await db.users.find_one({"_id": ObjectId(user_id)})

    if not user:
        return None
    
    # Use strict ObjectId lookup for app_configs
    config = await db.app_configs.find_one({"userId": user["_id"]})
    
    if config:
        # Migrar campo legacy si es necesario
        needs_migration = False
        
        # Si tiene geminiApiKey pero no aiApiKey, migrar
        if "geminiApiKey" in config and config.get("geminiApiKey") and not config.get("aiApiKey"):
            logger.info(f"Migrating legacy geminiApiKey to aiApiKey for user {user['_id']}")
            config["aiApiKey"] = config["geminiApiKey"]
            needs_migration = True
        
        # Si no tiene aiProvider definido, establecer gemini como default
        if "aiProvider" not in config:
            logger.info(f"Setting default aiProvider=gemini for user {user['_id']}")
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

async def update_virtual_balance(user_id: Any, market_type: str, asset: str, amount: float, is_relative: bool = False):
    """Updates virtual balance for a user.

    Normaliza market_type para evitar documentos duplicados por capitalización ("cex" vs "CEX").

    user_id: Can be ObjectId, openId string, or ObjectId string.
    """
    # Normalize market_type (canonical: CEX/DEX)
    mt = str(market_type or "CEX").strip()
    u_mt = mt.upper()
    if u_mt in {"CEX", "SPOT", "CE", "SPOT_CEX"}:
        market_type = "CEX"
    elif u_mt in {"DEX"}:
        market_type = "DEX"
    elif u_mt in {"FUTURE", "FUTURES", "SWAP", "PERP", "PERPETUAL"}:
        market_type = "CEX"
    else:
        # common lowercase
        l = mt.lower()
        if l in {"cex", "spot"}:
            market_type = "CEX"
        elif l == "dex":
            market_type = "DEX"

    user = None
    if isinstance(user_id, ObjectId):
        user = await db.users.find_one({"_id": user_id})
    else:
        user = await db.users.find_one({"openId": user_id})
        if not user and ObjectId.is_valid(user_id):
             user = await db.users.find_one({"_id": ObjectId(user_id)})

    if not user:
        logger.warning(f"update_virtual_balance: User not found for id {user_id}")
        return
    
    # Use ObjectId for virtual_balances operations
    if is_relative:
        # Sumar o restar al balance existente
        await db.virtual_balances.update_one(
            {"userId": user["_id"], "marketType": market_type, "asset": asset},
            {"$inc": {"amount": amount}, "$set": {"updatedAt": datetime.utcnow()}},
            upsert=True
        )
        # Obtener el nuevo balance para emitir
        balance_doc = await db.virtual_balances.find_one({"userId": user["_id"], "marketType": market_type, "asset": asset})
        amount = balance_doc["amount"]
    else:
        # Establecer valor absoluto
        await db.virtual_balances.update_one(
            {"userId": user["_id"], "marketType": market_type, "asset": asset},
            {"$set": {"amount": amount, "updatedAt": datetime.utcnow()}},
            upsert=True
        )
    
    # Emitir cambio por socket using openId (string) as per frontend expectation/socket service
    from api.src.adapters.driven.notifications.socket_service import socket_service
    await socket_service.emit_to_user(user["openId"], "balance_update", {
        "marketType": market_type,
        "asset": asset,
        "amount": amount,
        "updatedAt": datetime.utcnow().isoformat()
    })

async def init_db():
    """
    Inicializa la base de datos MongoDB con valores por defecto si es necesario.
    """
    logger.info("Initializing MongoDB collections and defaults...")
    try:
        collections = await db.list_collection_names()
        for coll in ["virtual_balances", "trades", "trading_signals"]:
            if coll not in collections:
                await db.create_collection(coll)
                logger.info(f"Created collection: {coll}")
    except Exception as e:
        logger.error(f"Error during MongoDB initialization: {e}")
