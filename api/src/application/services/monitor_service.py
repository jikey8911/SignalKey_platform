import asyncio
import logging
import ccxt.async_support as ccxt
from datetime import datetime
from src.adapters.driven.persistence.mongodb import db, update_virtual_balance
from src.application.services.cex_service import CEXService
from src.application.services.dex_service import DEXService
from bson import ObjectId
from typing import Optional

logger = logging.getLogger(__name__)

class MonitorService:
    def __init__(self, cex_service: Optional[CEXService] = None, dex_service: Optional[DEXService] = None):
        self.running = False
        self.interval = 60 # Reducido a 1 minuto para mejor monitoreo
        self.cex_service = cex_service or CEXService()
        self.dex_service = dex_service or DEXService()

    async def start_monitoring(self):
        if self.running:
            return
        self.running = True
        logger.info("MonitorService iniciado (Intervalo: 5 min)")
        while self.running:
            try:
                await self.check_open_positions()
                await self.push_connection_status()
            except Exception as e:
                logger.error(f"Error en el ciclo de monitoreo: {e}")
            await asyncio.sleep(self.interval)

    async def stop_monitoring(self):
        self.running = False
        await self.cex_service.close_all()
        await self.dex_service.close_all()

    async def check_open_positions(self):
        # 1. Monitorear posiciones simuladas (Demo)
        cursor_demo = db.trades.find({"status": "open", "isDemo": True})
        open_trades_demo = await cursor_demo.to_list(length=100)
        
        # 2. Monitorear posiciones reales si es necesario (Pendiente integración profunda)
        # Por ahora nos enfocamos en que el servicio sea capaz de consultar el exchange
        
        if not open_trades_demo:
            return

        logger.info(f"Monitoreando {len(open_trades_demo)} posiciones DEMO abiertas...")

        for trade in open_trades_demo:
            try:
                symbol = str(trade.get("symbol", "")).strip()
                if not symbol or "/" not in symbol and len(symbol) < 3:
                    continue
                    
                market_type = trade["marketType"]
                entry_price = trade["entryPrice"]
                side = trade["side"]
                tp = trade.get("tp")
                sl = trade.get("sl")
                amount = trade["amount"]
                
                trade_user_id = trade.get("userId")
                if not trade_user_id:
                    continue
                    
                user = await db.users.find_one({"_id": trade_user_id})
                if not user:
                    continue
                user_open_id = user["openId"]

                # Obtener precio actual
                current_price = 0.0
                if market_type == "CEX":
                    current_price = await self.cex_service.get_current_price(symbol, user_open_id)
                else:
                    network = trade.get("network", "ethereum")
                    current_price = await self.dex_service.get_current_price(symbol, network, user_open_id)

                if current_price == 0:
                    continue

                # Calcular PnL actual
                pnl = 0.0
                if side == "BUY":
                    pnl = (current_price - entry_price) * (amount / entry_price)
                else: # SELL
                    pnl = (entry_price - current_price) * (amount / entry_price)

                # Verificar TP/SL
                should_close = False
                close_reason = ""

                if tp and ((side == "BUY" and current_price >= tp) or (side == "SELL" and current_price <= tp)):
                    should_close = True
                    close_reason = "TP Reached"
                elif sl and ((side == "BUY" and current_price <= sl) or (side == "SELL" and current_price >= sl)):
                    should_close = True
                    close_reason = "SL Reached"

                # Actualizar precio actual y PnL en la DB
                await db.trades.update_one(
                    {"_id": trade["_id"]},
                    {"$set": {"currentPrice": current_price, "pnl": pnl, "updatedAt": datetime.utcnow()}}
                )

                if should_close:
                    await self.close_position(trade, current_price, pnl, close_reason)

            except Exception as e:
                logger.error(f"Error monitoreando trade {trade.get('_id')}: {e}")

    async def close_position(self, trade, close_price, pnl, reason):
        logger.info(f"Cerrando posición {trade['symbol']} ({reason}). PnL: {pnl}")
        
        # Actualizar trade a completado
        await db.trades.update_one(
            {"_id": trade["_id"]},
            {
                "$set": {
                    "status": "completed",
                    "exitPrice": close_price,
                    "pnl": pnl,
                    "closeReason": reason,
                    "executedAt": datetime.utcnow()
                }
            }
        )

        # Actualizar balance virtual del usuario
        # Buscamos el openId del usuario
        user = await db.users.find_one({"_id": trade["userId"]})
        if user:
            user_open_id = user["openId"]
            market_type = trade["marketType"]
            asset = "USDT" if market_type == "CEX" else trade.get("asset", "USDT")
            
            # Obtener balance actual
            balance_doc = await db.virtual_balances.find_one({
                "userId": trade["userId"],
                "marketType": market_type,
                "asset": asset
            })
            
            if balance_doc:
                # El nuevo balance es el anterior + el monto inicial + el pnl
                # (Ya que al abrir restamos el monto inicial)
                new_balance = balance_doc["amount"] + trade["amount"] + pnl
                await update_virtual_balance(user_open_id, market_type, asset, new_balance)
                logger.info(f"Balance virtual actualizado para {user_open_id}: {new_balance}")

    async def push_connection_status(self):
        """Envía el estado de conexión a todos los usuarios conectados vía WebSocket"""
        from src.adapters.driven.notifications.socket_service import socket_service
        from bot.telegram_bot_manager import bot_manager
        from src.adapters.driven.persistence.mongodb import get_app_config

        active_users = socket_service.active_connections.keys()
        if not active_users:
            return

        for user_id in list(active_users):
            try:
                status = {
                    "gemini": False,
                    "exchange": False,
                    "telegram": False,
                    "gmgn": False, # legacy name used in frontend
                }
                
                config = await get_app_config(user_id)
                if not config:
                    continue
                
                # Check AI Provider
                if config.get("aiApiKey") or config.get("geminiApiKey"):
                    status["gemini"] = True
                
                # Check Exchange
                exchanges = config.get("exchanges", [])
                active_ex = next((e for e in exchanges if e.get("isActive") and e.get("apiKey")), None)
                if active_ex:
                    status["exchange"] = True
                
                # Check Telegram
                if bot_manager.is_bot_active(user_id):
                    status["telegram"] = True
                
                # Check ZeroEx (mapped to gmgn in status for frontend compatibility)
                if config.get("zeroExApiKey") or config.get("gmgnApiKey"):
                    status["gmgn"] = True
                
                # Fetch Real Balance simplified for status (UNIFIED via CEXService)
                try:
                    balances = await self.cex_service.fetch_balance(user_id)
                    if balances and 'total' in balances:
                        status["balance_usdt"] = balances['total'].get('USDT', 0.0)
                except Exception as e:
                    logger.error(f"Error fetching unified balance for status: {e}")

                await socket_service.emit_to_user(user_id, "status_update", status)
            except Exception as e:
                logger.error(f"Error pushing status for user {user_id}: {e}")
