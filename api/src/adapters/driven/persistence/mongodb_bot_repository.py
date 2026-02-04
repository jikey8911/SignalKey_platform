from motor.motor_asyncio import AsyncIOMotorClient
from api.src.domain.entities.bot_instance import BotInstance
from bson import ObjectId
import os
from datetime import datetime

class MongoBotRepository:
    """
    Repositorio sp2 para la persistencia de bots. 
    Permite recuperar bots activos para reanudar operaciones tras fallos del sistema.
    """
    def __init__(self):
        # Allow overriding via env vars, but default to localhost
        self.uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.db_name = os.getenv("MONGODB_DB", "signalkey_db")
        self.client = AsyncIOMotorClient(self.uri)
        self.db = self.client[self.db_name]
        self.collection = self.db["bot_instances"]

    async def save(self, bot: BotInstance) -> str:
        doc = bot.to_dict()
        if "id" in doc: del doc["id"]
        result = await self.collection.insert_one(doc)
        return str(result.inserted_id)

    async def get_active_bots(self) -> list:
        """Recupera todos los bots que deben estar corriendo (Autotrade)."""
        cursor = self.collection.find({"status": "active"})
        return [self._map_doc(doc) async for doc in cursor]

    async def get_all_by_user(self, user_id: str) -> list:
        cursor = self.collection.find({"user_id": user_id})
        return [self._map_doc(doc) async for doc in cursor]

    async def update_status(self, bot_id: str, status: str) -> bool:
        result = await self.collection.update_one(
            {"_id": ObjectId(bot_id)},
            {"$set": {"status": status}}
        )
        return result.modified_count > 0
        
    async def update(self, bot_id: str, data: dict) -> bool:
        """Generic update"""
        if "_id" in data: del data["_id"]
        result = await self.collection.update_one(
            {"_id": ObjectId(bot_id)},
            {"$set": data}
        )
        return result.modified_count > 0
        
    async def delete(self, bot_id: str) -> bool:
        result = await self.collection.delete_one({"_id": ObjectId(bot_id)})
        return result.deleted_count > 0

    def _map_doc(self, doc) -> BotInstance:
        doc["id"] = str(doc["_id"])
        data = {k: v for k, v in doc.items() if k != "_id"}
        
        # Manejo de fechas isoformat a datetime si es necesario
        if isinstance(data.get('created_at'), str):
            try:
                data['created_at'] = datetime.fromisoformat(data['created_at'])
            except:
                pass
                
        # Robust Mapping: Filter fields that are not in BotInstance constructor
        # This prevents crashes if DB has extra fields (e.g. from future versions or manual edits)
        import inspect
        valid_fields = inspect.signature(BotInstance).parameters
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        
        return BotInstance(**filtered_data)
