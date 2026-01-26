import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any
from src.adapters.driven.persistence.mongodb import db, update_virtual_balance
from src.application.services.cex_service import CEXService
from src.application.services.dex_service import DEXService
from src.adapters.driven.notifications.socket_service import socket_service

logger = logging.getLogger(__name__)

class TrackerService:
    def __init__(self, cex_service: CEXService = None, dex_service: DEXService = None):
        self.cex_service = cex_service or CEXService()
        self.dex_service = dex_service or DEXService()
        self.is_running = False

    async def start_monitoring(self):
        """Inicia el bucle global de monitoreo de trades"""
        if self.is_running:
            return
        self.is_running = True
        logger.info("TrackerService: Bucle de monitoreo iniciado (30s interval)")
        asyncio.create_task(self._monitor_loop())

    async def stop_monitoring(self):
        self.is_running = False

    async def add_trade_to_monitor(self, trade_id: str):
        """Notifica al tracker que hay un nuevo trade (el loop lo recogerá)"""
        logger.info(f"TrackerService: Nuevo trade detectado para monitoreo: {trade_id}")

    async def _monitor_loop(self):
        while self.is_running:
            try:
                # Buscar trades activos (pending para entrada, open para TP/SL)
                trades = await db.trades.find({
                    "status": {"$in": ["pending", "open", "monitoring"]}
                }).to_list(length=100)

                for trade in trades:
                    await self._process_trade_monitoring(trade)

                await asyncio.sleep(30) 
            except Exception as e:
                logger.error(f"Error en TrackerService loop: {e}")
                await asyncio.sleep(10)

    async def _process_trade_monitoring(self, trade: Dict[str, Any]):
        trade_id = trade["_id"]
        symbol = trade["symbol"]
        market_type = trade["marketType"]
        user_id_obj = trade["userId"]
        side = trade["side"]
        
        user = await db.users.find_one({"_id": user_id_obj})
        if not user: return
        user_id = user["openId"]

        try:
            # 1. Obtener precio actual
            network = trade.get("network", "ethereum")
            current_price = await self._get_current_price(symbol, market_type, user_id, network)
            if current_price <= 0: return

            # 2. Actualizar precio en DB y emitir por socket
            await db.trades.update_one(
                {"_id": trade_id},
                {"$set": {"currentPrice": current_price, "lastMonitoredAt": datetime.utcnow()}}
            )
            
            await socket_service.emit_to_user(user_id, "trade_update", {
                "id": str(trade_id),
                "symbol": symbol,
                "currentPrice": current_price,
                "status": trade["status"]
            })

            # 3. Lógica de ejecución
            if trade["status"] == "pending" or trade["status"] == "monitoring":
                # Monitorear entrada
                entry_price = trade.get("entryPrice")
                should_execute = False
                if side == "BUY" and current_price <= entry_price: should_execute = True
                elif side == "SELL" and current_price >= entry_price: should_execute = True
                
                if should_execute:
                    logger.info(f"TrackerService: Precio de entrada alcanzado para {symbol} ({current_price})")
                    await self._execute_trade_step(trade, "open", "ENTRY", user_id, current_price)

            elif trade["status"] == "open":
                # Monitorear TP/SL
                # Check SL
                sl = trade.get("stopLoss") or trade.get("sl")
                if sl:
                    is_sl = (side == "BUY" and current_price <= sl) or (side == "SELL" and current_price >= sl)
                    if is_sl:
                        logger.info(f"TrackerService: SL alcanzado para {symbol} ({current_price})")
                        await self._execute_trade_step(trade, "closed", "STOP_LOSS", user_id, current_price)
                        return

                # Check TPs
                tps = trade.get("takeProfits") or trade.get("tp") or []
                for i, tp in enumerate(tps):
                    if tp.get("executed"): continue
                    
                    is_tp = (side == "BUY" and current_price >= tp["price"]) or (side == "SELL" and current_price <= tp["price"])
                    if is_tp:
                        logger.info(f"TrackerService: TP alcanzado para {symbol} ({current_price})")
                        # Si es el último TP, cerrar trade, si no, mantener abierto pero marcar TP
                        is_last = i == len(tps) - 1
                        new_status = "closed" if is_last else "open"
                        await self._execute_trade_step(trade, new_status, f"TAKE_PROFIT_{i+1}", user_id, current_price, tp_index=i)
                        break

        except Exception as e:
            logger.error(f"Error monitoreando trade {trade_id}: {e}")

    async def _get_current_price(self, symbol: str, market_type: str, user_id: str, network: str = "ethereum") -> float:
        if market_type == "DEX":
            return await self.dex_service.get_current_price(symbol, network, user_id)
        return await self.cex_service.get_current_price(symbol, user_id)

    async def _execute_trade_step(self, trade: Dict[str, Any], new_status: str, action: str, user_id: str, price: float, tp_index: int = None):
        trade_id = trade["_id"]
        amount = trade["amount"]
        market_type = trade["marketType"]
        
        # Actualizar balance virtual (Simulación Demo)
        asset = "USDT" if market_type != "DEX" else trade.get("asset", "USDT")
        
        # Lógica de balance:
        # ENTRY BUY -> Resta USDT
        # ENTRY SELL -> Resta Asset (Simulado como USDT para simplificar)
        # EXIT (TP/SL) -> Suma USDT + PnL
        
        if "ENTRY" in action:
            await update_virtual_balance(user_id, market_type, asset, -amount, is_relative=True)
        elif "TAKE_PROFIT" in action or "STOP_LOSS" in action:
            # Calcular PnL simple para el balance
            entry_price = trade["entryPrice"]
            pnl_pct = (price - entry_price) / entry_price if trade["side"] == "BUY" else (entry_price - price) / entry_price
            return_amount = amount * (1 + pnl_pct)
            await update_virtual_balance(user_id, market_type, asset, return_amount, is_relative=True)

        # Actualizar Trade en DB
        update_fields = {"status": new_status, "updatedAt": datetime.utcnow()}
        if tp_index is not None:
            tps = trade.get("takeProfits") or trade.get("tp") or []
            tps[tp_index]["executed"] = True
            tps[tp_index]["executedAt"] = datetime.utcnow()
            tps[tp_index]["executionPrice"] = price
            update_fields["takeProfits"] = tps
        
        if new_status == "closed":
            update_fields["exitPrice"] = price
            update_fields["closedAt"] = datetime.utcnow()

        await db.trades.update_one({"_id": trade_id}, {"$set": update_fields})
        
        # Emitir por socket
        await socket_service.emit_to_user(user_id, "trade_update", {
            "id": str(trade_id),
            "status": new_status,
            "action": action,
            "price": price
        })

tracker_service = TrackerService()
