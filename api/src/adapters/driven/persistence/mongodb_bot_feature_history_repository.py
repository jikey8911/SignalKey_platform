from datetime import datetime
from typing import Any, Dict, List
from bson import ObjectId

from api.src.adapters.driven.persistence.mongodb import db


class MongoBotFeatureHistoryRepository:
    """Historical per-candle features per bot."""

    def __init__(self, db_adapter=None):
        self.db = db_adapter if db_adapter is not None else db
        self.collection = self.db["bot_feature_history"]

    async def ensure_indexes(self):
        await self.collection.create_index([("botId", 1), ("candleTs", 1)], unique=True)
        await self.collection.create_index([("strategyName", 1), ("symbol", 1), ("timeframe", 1), ("candleTs", -1)])

    async def upsert_many(self, docs: List[Dict[str, Any]]) -> int:
        now = datetime.utcnow()
        upserts = 0
        for d in docs or []:
            bot_id = d.get("botId")
            if isinstance(bot_id, str) and ObjectId.is_valid(bot_id):
                bot_id = ObjectId(bot_id)
            candle_ts = d.get("candleTs")
            if not bot_id or not candle_ts:
                continue

            payload = dict(d)
            payload["botId"] = bot_id
            payload["updatedAt"] = now

            result = await self.collection.update_one(
                {"botId": bot_id, "candleTs": candle_ts},
                {"$set": payload, "$setOnInsert": {"createdAt": now}},
                upsert=True,
            )
            if result.upserted_id or result.modified_count > 0:
                upserts += 1
        return upserts
