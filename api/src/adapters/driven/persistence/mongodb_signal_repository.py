from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from api.src.domain.models.signal import Signal, SignalStatus, MarketType, Decision
from api.src.domain.ports.output.signal_repository import ISignalRepository

class MongoDBSignalRepository(ISignalRepository):
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.trading_signals

    async def save(self, signal: Signal) -> Signal:
        signal_dict = {
            "userId": ObjectId(signal.userId) if isinstance(signal.userId, str) and len(signal.userId) == 24 else signal.userId,
            "source": signal.source,
            "rawText": signal.rawText,
            "status": signal.status.value,
            "createdAt": signal.createdAt,
            # Campos analizados
            "symbol": signal.symbol,
            "marketType": signal.marketType.value if signal.marketType else None,
            "decision": signal.decision.value if signal.decision else None,
            "confidence": signal.confidence,
            "reasoning": signal.reasoning,
            "riskScore": signal.riskScore,
            "botId": ObjectId(signal.botId) if isinstance(signal.botId, str) and len(signal.botId) == 24 else signal.botId,
            "tradeId": signal.tradeId,
            "executionMessage": signal.executionMessage
        }
        result = await self.collection.insert_one(signal_dict)
        signal.id = str(result.inserted_id)
        return signal

    async def update(self, signal_id: str, update_data: dict) -> bool:
        # Transformar enums a strings si es necesario
        for key, value in update_data.items():
            if hasattr(value, 'value'):
                update_data[key] = value.value
        
        result = await self.collection.update_one(
            {"_id": ObjectId(signal_id)},
            {"$set": update_data}
        )
        return result.modified_count > 0

    async def find_by_id(self, signal_id: str) -> Optional[Signal]:
        try:
            oid = ObjectId(signal_id)
        except:
            return None

        doc = await self.collection.find_one({"_id": oid})
        if not doc:
            return None
        return self._map_to_entity(doc)

    async def find_by_user(self, user_id: str) -> List[Signal]:
        # Handle ObjectId or string ID consistently with save method
        query_id = ObjectId(user_id) if isinstance(user_id, str) and len(user_id) == 24 else user_id

        cursor = self.collection.find({"userId": query_id})
        signals = []
        async for doc in cursor:
            signals.append(self._map_to_entity(doc))
        return signals

    async def find_by_bot_id(self, bot_id: str) -> List[Signal]:
        query_id = ObjectId(bot_id) if isinstance(bot_id, str) and len(bot_id) == 24 else bot_id
        cursor = self.collection.find({"botId": query_id})
        signals = []
        async for doc in cursor:
            signals.append(self._map_to_entity(doc))
        return signals

    def _map_to_entity(self, doc: dict) -> Signal:
        return Signal(
            id=str(doc["_id"]),
            userId=str(doc["userId"]),
            source=doc["source"],
            rawText=doc["rawText"],
            status=SignalStatus(doc["status"]),
            createdAt=doc["createdAt"],
            symbol=doc.get("symbol"),
            marketType=MarketType(doc["marketType"]) if doc.get("marketType") else None,
            decision=Decision(doc["decision"]) if doc.get("decision") else None,
            confidence=doc.get("confidence"),
            reasoning=doc.get("reasoning"),
            riskScore=doc.get("riskScore"),
            botId=str(doc.get("botId")) if doc.get("botId") else None,
            tradeId=str(doc.get("tradeId")) if doc.get("tradeId") else None,
            executionMessage=doc.get("executionMessage")
        )
