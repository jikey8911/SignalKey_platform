import asyncio
import logging
import ccxt.async_support as ccxt
from datetime import datetime
from api.models.mongodb import db, update_virtual_balance
from api.services.cex_service import CEXService
from bson import ObjectId

logger = logging.getLogger(__name__)

class MonitorService:
    def __init__(self, cex_service: Optional[CEXService] = None):
        self.running = False
        self.interval = 300 # 5 minutos en segundos
        self.cex_service = cex_service or CEXService()

    async def start_monitoring(self):
        if self.running:
            return
        self.running = True
        logger.info("MonitorService iniciado (Intervalo: 5 min)")
        while self.running:
            try:
                await self.check_open_positions()
            except Exception as e:
                logger.error(f"Error en check_open_positions: {e}")
            await asyncio.sleep(self.interval)

    async def stop_monitoring(self):
        self.running = False
        await self.cex_service.close_all()

    async def check_open_positions(self):
        # Buscar posiciones abiertas en modo demo
        cursor = db.trades.find({"status": "open", "isDemo": True})
        open_trades = await cursor.to_list(length=100)
        
        if not open_trades:
            return

        logger.info(f"Monitoreando {len(open_trades)} posiciones abiertas...")

        for trade in open_trades:
            try:
                symbol = trade["symbol"]
                market_type = trade["marketType"]
                entry_price = trade["entryPrice"]
                side = trade["side"]
                tp = trade.get("tp")
                sl = trade.get("sl")
                amount = trade["amount"]
                user = await db.users.find_one({"_id": user_id})
                if not user:
                    continue
                user_open_id = user["openId"]

                # Obtener precio actual
                current_price = 0.0
                if market_type == "CEX":
                    current_price = await self.cex_service.get_current_price(symbol, user_open_id)
                else:
                    # Para DEX, simulación o API externa
                    current_price = entry_price * 1.01 # Simulación de subida del 1%

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
            asset = "USDT" if market_type == "CEX" else "SOL"
            
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
