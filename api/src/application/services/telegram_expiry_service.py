import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId

from api.src.adapters.driven.persistence.mongodb import db, get_app_config
from api.src.adapters.driven.ai.ai_adapter import AIAdapter as PromptAIAdapter
from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service

logger = logging.getLogger(__name__)


class TelegramExpiryService:
    """Handles expiry of telegram_bots when expiresAt <= now.

    Flow:
    - Find expired bots not handled
    - Ask AI: close vs update TP/SL
    - Apply action
    """

    def __init__(self):
        self.ai = PromptAIAdapter()

    async def check_and_handle_expired(self, limit: int = 20):
        now = datetime.utcnow()
        cursor = (
            db.telegram_bots
            .find({
                "expiresAt": {"$lte": now},
                "status": {"$in": ["waiting_entry", "active"]},
                "expiryHandledAt": {"$exists": False},
            })
            .sort("expiresAt", 1)
            .limit(limit)
        )
        bots = await cursor.to_list(length=limit)
        for bot in bots:
            try:
                await self._handle_one(bot)
            except Exception as e:
                logger.error(f"expiry handle failed for bot {bot.get('_id')}: {e}")

    async def _handle_one(self, bot: Dict[str, Any]):
        bot_id = bot.get("_id")
        if not isinstance(bot_id, ObjectId):
            return

        user_oid = bot.get("userId")
        if not isinstance(user_oid, ObjectId):
            return

        # Load user openId + config
        user = await db.users.find_one({"_id": user_oid})
        if not user:
            return
        open_id = user.get("openId")
        config = await get_app_config(open_id)
        config = config or {}

        exchange_id = (bot.get("exchangeId") or "binance").lower()
        symbol = str(bot.get("symbol") or "").strip().replace("#", "")
        market_type = bot.get("marketType")

        # Get a current price snapshot (best effort)
        current_price = 0.0
        try:
            current_price = float(await ccxt_service.get_public_current_price(symbol, exchange_id=exchange_id) or 0.0)
        except Exception:
            current_price = 0.0

        prompt = self._build_expiry_prompt(bot, current_price)
        content = await self.ai.generate_content(prompt, config=config)

        decision = None
        try:
            decision = json.loads(content)
        except Exception:
            decision = {"action": "close", "reason": "invalid_ai_json"}

        action = (decision.get("action") or "close").lower()

        if action == "update":
            await self._apply_update(bot_id, decision)
        else:
            await self._apply_close(bot_id, decision)

    def _build_expiry_prompt(self, bot: Dict[str, Any], current_price: float) -> str:
        cfg = bot.get("config") or {}
        return f"""
Eres un gestor de riesgo para bots de señales de Telegram.

El bot SE VENCIO (tiempo en 0). Debes decidir si:
- action="close" (cerrar el bot / cancelar señal), o
- action="update" (actualizar stopLoss y takeProfits para extender la señal)

REGLAS:
- Responde SOLO JSON.
- Si propones update: must include newStopLoss y newTakeProfits (lista con price+percent sum=100).
- Si no estás seguro, cierra.

BOT:
- symbol: {bot.get('symbol')}
- exchangeId: {bot.get('exchangeId')}
- marketType: {bot.get('marketType')}
- side: {bot.get('side')}
- status: {bot.get('status')}
- entryPrice: {cfg.get('entryPrice')}
- stopLoss: {cfg.get('stopLoss')}
- takeProfits: {cfg.get('takeProfits')}
- currentPrice: {current_price}

JSON:
{{
  "action": "close" | "update",
  "reason": "...",
  "newStopLoss": 0.0,
  "newTakeProfits": [{{"price":0.0,"percent":100.0}}]
}}
"""

    async def _apply_close(self, bot_id: ObjectId, decision: Dict[str, Any]):
        now = datetime.utcnow()
        await db.telegram_bots.update_one(
            {"_id": bot_id},
            {"$set": {
                "status": "expired",
                "expiryHandledAt": now,
                "expiryDecision": decision,
                "updatedAt": now,
            }}
        )
        # cancel pending trade items
        await db.telegram_trades.update_many(
            {"botId": bot_id, "status": {"$in": ["pending", "active"]}},
            {"$set": {"status": "cancelled", "updatedAt": now}}
        )

    async def _apply_update(self, bot_id: ObjectId, decision: Dict[str, Any]):
        now = datetime.utcnow()
        new_sl = decision.get("newStopLoss")
        new_tps = decision.get("newTakeProfits")

        updates: Dict[str, Any] = {
            "expiryHandledAt": now,
            "expiryDecision": decision,
            "updatedAt": now,
        }

        if new_sl is not None:
            updates["config.stopLoss"] = new_sl

        if isinstance(new_tps, list) and new_tps:
            updates["config.takeProfits"] = new_tps

        await db.telegram_bots.update_one({"_id": bot_id}, {"$set": updates})

        # reflect in items collection (best-effort)
        if new_sl is not None:
            await db.telegram_trades.update_many(
                {"botId": bot_id, "kind": "sl", "status": "active"},
                {"$set": {"status": "cancelled", "updatedAt": now}}
            )
            await db.telegram_trades.insert_one({
                "botId": bot_id,
                "userId": (await db.telegram_bots.find_one({"_id": bot_id})).get("userId"),
                "kind": "sl",
                "level": 0,
                "targetPrice": float(new_sl),
                "status": "active",
                "createdAt": now,
                "updatedAt": now,
            })

        if isinstance(new_tps, list) and new_tps:
            await db.telegram_trades.update_many(
                {"botId": bot_id, "kind": "tp", "status": "pending"},
                {"$set": {"status": "cancelled", "updatedAt": now}}
            )
            docs = []
            for idx, tp in enumerate(new_tps, start=1):
                try:
                    docs.append({
                        "botId": bot_id,
                        "userId": (await db.telegram_bots.find_one({"_id": bot_id})).get("userId"),
                        "kind": "tp",
                        "level": idx,
                        "targetPrice": float(tp.get("price")),
                        "percent": float(tp.get("percent")),
                        "status": "pending",
                        "createdAt": now,
                        "updatedAt": now,
                    })
                except Exception:
                    continue
            if docs:
                await db.telegram_trades.insert_many(docs)
