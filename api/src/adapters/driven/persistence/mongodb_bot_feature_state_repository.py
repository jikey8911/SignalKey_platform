from datetime import datetime
from typing import Any, Dict, Optional
from bson import ObjectId

from api.src.adapters.driven.persistence.mongodb import db


class MongoBotFeatureStateRepository:
    """Persistencia de estado de features por bot/estrategia.

    Colección: bot_feature_states
    Un documento por botId.
    """

    def __init__(self, db_adapter=None):
        self.db = db_adapter if db_adapter is not None else db
        self.collection = self.db["bot_feature_states"]

    async def ensure_indexes(self):
        await self.collection.create_index("botId", unique=True)
        await self.collection.create_index([("strategyName", 1), ("symbol", 1), ("timeframe", 1)])
        await self.collection.create_index("updatedAt")

    async def upsert_state(self, payload: Dict[str, Any]) -> str:
        now = datetime.utcnow()
        bot_id = payload.get("botId")
        if not bot_id:
            raise ValueError("botId is required")

        if isinstance(bot_id, str) and ObjectId.is_valid(bot_id):
            bot_id = ObjectId(bot_id)

        payload = dict(payload)
        payload["botId"] = bot_id
        payload["updatedAt"] = now

        result = await self.collection.update_one(
            {"botId": bot_id},
            {"$set": payload, "$setOnInsert": {"createdAt": now}},
            upsert=True,
        )

        if result.upserted_id:
            return str(result.upserted_id)

        doc = await self.collection.find_one({"botId": bot_id}, {"_id": 1})
        return str(doc.get("_id")) if doc else ""

    async def get_by_bot_id(self, bot_id: Any) -> Optional[Dict[str, Any]]:
        if isinstance(bot_id, str) and ObjectId.is_valid(bot_id):
            bot_id = ObjectId(bot_id)
        return await self.collection.find_one({"botId": bot_id})
