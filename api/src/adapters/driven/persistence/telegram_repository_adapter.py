from typing import Dict, Any, List, Optional
from datetime import datetime
from bson import ObjectId
from api.src.adapters.driven.persistence.mongodb import db
from api.src.domain.ports.output.telegram_repository_port import ITelegramSignalRepository, ITelegramTradeRepository

class MongoTelegramSignalRepository(ITelegramSignalRepository):
    async def save_approved_signal(self, signal_data: Dict[str, Any]) -> str:
        result = await db.db["telegram_signals"].insert_one(signal_data)
        return str(result.inserted_id)

class MongoTelegramTradeRepository(ITelegramTradeRepository):
    async def create_trade(self, trade_data: Dict[str, Any]) -> str:
        result = await db.db["telegram_trades"].insert_one(trade_data)
        return str(result.inserted_id)

    async def update_trade(self, trade_id: str, updates: Dict[str, Any]):
        await db.db["telegram_trades"].update_one(
            {"_id": ObjectId(trade_id) if isinstance(trade_id, str) else trade_id},
            {"$set": updates}
        )

    async def get_active_trades(self, exchange_id: Optional[str] = None) -> List[Dict[str, Any]]:
        query = {"status": {"$in": ["waiting_entry", "active"]}}
        if exchange_id:
            query["exchangeId"] = exchange_id
        
        return await db.db["telegram_trades"].find(query).to_list(length=1000)

    async def has_active_trade(self, user_id: str, symbol: str) -> bool:
        existing = await db.db["telegram_trades"].find_one({
            "userId": user_id,
            "symbol": symbol,
            "status": {"$in": ["waiting_entry", "active"]}
        })
        return existing is not None
