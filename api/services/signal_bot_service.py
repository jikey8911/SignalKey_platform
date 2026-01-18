import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List
from api.models.mongodb import db, save_trade, update_virtual_balance
from api.services.cex_service import CEXService
from api.services.dex_service import DEXService
from api.models.schemas import AnalysisResult, ExecutionResult

logger = logging.getLogger(__name__)

class SignalBotService:
    def __init__(self):
        self.cex_service = CEXService()
        self.dex_service = DEXService()

    async def can_activate_bot(self, user_id: str, config: Dict[str, Any]) -> bool:
        """Verifica si el usuario puede activar un nuevo bot basado en su límite."""
        max_bots = config.get("botStrategy", {}).get("maxActiveBots", 5)
        active_bots_count = await db.trades.count_documents({
            "userId": user_id,
            "status": "active"
        })
        return active_bots_count < max_bots

    async def activate_bot(self, analysis: AnalysisResult, user_id: str, config: Dict[str, Any]) -> ExecutionResult:
        """Activa un bot para una señal aprobada."""
        if not await self.can_activate_bot(user_id, config):
            return ExecutionResult(success=False, message="Límite de bots activos alcanzado")

        demo_mode = config.get("demoMode", True)
        market_type = analysis.market_type # "CEX" o "DEX"
        symbol = analysis.symbol
        
        # Determinar precios de TP y SL basados en porcentajes de la configuración
        strategy = config.get("botStrategy", {})
        tp_levels_count = strategy.get("tpLevels", 3)
        tp_percent_step = strategy.get("tpPercent", 2.0)
        sl_percent = strategy.get("slPercent", 1.5)
        
        # Obtener precio de entrada (simulado o real)
        entry_price = 0.0
        if demo_mode:
            # Simulación de precio de entrada
            entry_price = analysis.parameters.get("entry_price") or 100.0 # Placeholder
        else:
            # Aquí se llamaría al servicio real para obtener precio o ejecutar orden market
            pass

        # Calcular niveles de TP
        take_profits = []
        for i in range(1, tp_levels_count + 1):
            price = entry_price * (1 + (tp_percent_step * i / 100))
            take_profits.append({
                "level": i,
                "price": price,
                "percent": strategy.get("sellPercentPerTP", 33.3),
                "status": "pending"
            })

        stop_loss = entry_price * (1 - (sl_percent / 100))

        # Crear el documento del bot (Trade)
        bot_doc = {
            "userId": user_id,
            "symbol": symbol,
            "side": "BUY",
            "entryPrice": entry_price,
            "stopLoss": stop_loss,
            "takeProfits": take_profits,
            "amount": config.get("investmentLimits", {}).get("cexMaxAmount" if market_type == "CEX" else "dexMaxAmount", 10.0),
            "marketType": market_type,
            "isDemo": demo_mode,
            "status": "active",
            "currentTPLevel": 0,
            "pnl": 0.0,
            "createdAt": datetime.utcnow()
        }

        inserted_id = await save_trade(bot_doc)
        
        # Si es demo, actualizar balance virtual
        if demo_mode:
            asset = "USDT" if market_type == "CEX" else "SOL"
            # Lógica de balance virtual aquí...
            pass

        return ExecutionResult(
            success=True, 
            message=f"Bot activado para {symbol} ({market_type}) en modo {'DEMO' if demo_mode else 'REAL'}",
            details={"botId": str(inserted_id)}
        )

    async def monitor_bots(self):
        """Proceso en segundo plano para monitorear y actualizar bots activos."""
        while True:
            try:
                active_bots = await db.trades.find({"status": "active"}).to_list(length=100)
                for bot in active_bots:
                    await self._process_bot_tick(bot)
            except Exception as e:
                logger.error(f"Error en monitor_bots: {e}")
            await asyncio.sleep(60) # Revisar cada minuto

    async def _process_bot_tick(self, bot: Dict[str, Any]):
        """Actualiza el estado de un bot individual basado en el precio actual."""
        symbol = bot["symbol"]
        current_price = await self._get_current_price(bot)
        
        # Verificar Stop Loss
        if current_price <= bot["stopLoss"]:
            await self._close_bot(bot, current_price, "failed", "Stop Loss alcanzado")
            return

        # Verificar Take Profits
        updated_tps = bot["takeProfits"]
        any_tp_hit = False
        for tp in updated_tps:
            if tp["status"] == "pending" and current_price >= tp["price"]:
                tp["status"] = "hit"
                tp["hitAt"] = datetime.utcnow()
                bot["currentTPLevel"] = tp["level"]
                any_tp_hit = True
                logger.info(f"Bot {bot['_id']} alcanzó TP Nivel {tp['level']} para {symbol}")

        if any_tp_hit:
            # Si todos los TP se alcanzaron, cerrar bot
            if all(tp["status"] == "hit" for tp in updated_tps):
                await self._close_bot(bot, current_price, "completed", "Todos los TP alcanzados")
            else:
                await db.trades.update_one(
                    {"_id": bot["_id"]},
                    {"$set": {"takeProfits": updated_tps, "currentTPLevel": bot["currentTPLevel"], "lastMonitoredAt": datetime.utcnow()}}
                )

    async def _get_current_price(self, bot: Dict[str, Any]) -> float:
        # Lógica para obtener precio real vía CCXT o DEX API
        return bot["entryPrice"] * 1.01 # Simulación temporal

    async def _close_bot(self, bot: Dict[str, Any], exit_price: float, status: str, reason: str):
        pnl = ((exit_price - bot["entryPrice"]) / bot["entryPrice"]) * 100
        await db.trades.update_one(
            {"_id": bot["_id"]},
            {
                "$set": {
                    "status": status,
                    "exitPrice": exit_price,
                    "pnl": pnl,
                    "closeReason": reason,
                    "executedAt": datetime.utcnow()
                }
            }
        )
        logger.info(f"Bot {bot['_id']} cerrado: {status} ({reason}). PnL: {pnl:.2f}%")
