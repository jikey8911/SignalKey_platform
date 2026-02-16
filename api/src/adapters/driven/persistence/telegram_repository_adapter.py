from typing import Dict, Any, List, Optional
from datetime import datetime
from bson import ObjectId
from api.src.adapters.driven.persistence.mongodb import db
from api.src.domain.ports.output.telegram_repository_port import ITelegramSignalRepository, ITelegramTradeRepository, ITelegramPositionRepository

class MongoTelegramSignalRepository(ITelegramSignalRepository):
    async def save_signal(self, signal_data: Dict[str, Any]) -> str:
        result = await db["telegram_signals"].insert_one(signal_data)
        return str(result.inserted_id)

class MongoTelegramTradeRepository(ITelegramTradeRepository):
    async def create_trade(self, trade_data: Dict[str, Any]) -> str:
        result = await db["telegram_trades"].insert_one(trade_data)
        return str(result.inserted_id)

    async def update_trade(self, trade_id: str, updates: Dict[str, Any]):
        await db["telegram_trades"].update_one(
            {"_id": ObjectId(trade_id) if isinstance(trade_id, str) else trade_id},
            {"$set": updates}
        )

    async def get_active_trades(self, exchange_id: Optional[str] = None) -> List[Dict[str, Any]]:
        query = {"status": {"$in": ["waiting_entry", "active"]}}
        if exchange_id:
            query["exchangeId"] = exchange_id
        
        return await db["telegram_trades"].find(query).to_list(length=1000)

    async def has_active_trade(self, user_id: str, symbol: str) -> bool:
        existing = await db["telegram_trades"].find_one({
            "userId": user_id,
            "symbol": symbol,
            "status": {"$in": ["waiting_entry", "active"]}
        })
        return existing is not None

    async def update_trade_item_status(self, bot_id: str, kind: str, status: str):
        await db["telegram_trades"].update_many(
            {
                "botId": ObjectId(bot_id) if isinstance(bot_id, str) and len(bot_id) == 24 else bot_id,
                "kind": kind
            },
            {"$set": {"status": status, "updatedAt": datetime.utcnow()}}
        )

class MongoTelegramPositionRepository(ITelegramPositionRepository):
    async def upsert_position(self, trade_id: str, position_data: Dict[str, Any]):
        # Usamos update_one con upsert=True para crear o reemplazar
        await db["telegram_positions"].update_one(
            {"tradeId": trade_id},
            {"$set": position_data},
            upsert=True
        )

    async def close_position(self, trade_id: str):
        # Opción A: Eliminar la posición de la tabla "en vivo" (más limpio)
        await db["telegram_positions"].delete_one({"tradeId": trade_id})
