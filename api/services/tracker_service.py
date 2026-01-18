import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from api.models.mongodb import db
from api.models.schemas import TradeSchema
from api.services.cex_service import CEXService
from api.services.dex_service import DEXService

logger = logging.getLogger(__name__)

class TrackerService:
    def __init__(self, cex_service: Optional[CEXService] = None, dex_service: Optional[DEXService] = None):
        self.active_monitors = {} # {trade_id: task}
        self.cex_service = cex_service or CEXService()
        self.dex_service = dex_service or DEXService()
        self.is_running = False

    async def start_monitoring(self):
        """Inicia el bucle global de monitoreo de trades pendientes"""
        if self.is_running:
            return
        self.is_running = True
        logger.info("TrackerService: Bucle de monitoreo iniciado")
        asyncio.create_task(self._monitor_loop())

    async def add_trade_to_monitor(self, trade_id: str):
        """Notifica al tracker que hay un nuevo trade para monitorear"""
        logger.info(f"TrackerService: Nuevo trade para monitorear: {trade_id}")
        # El bucle _monitor_loop lo recogerá en la siguiente iteración

    async def _monitor_loop(self):
        while self.is_running:
            try:
                # 1. Buscar trades en estado 'monitoring' o 'pending' (si son limit)
                # O trades 'open' que necesiten monitoreo de TP/SL
                trades = await db.trades.find({
                    "status": {"$in": ["monitoring", "open"]}
                }).to_list(length=100)

                for trade in trades:
                    await self._process_trade_monitoring(trade)

                # Esperar exactamente 39 segundos antes de la siguiente iteración
                await asyncio.sleep(39) 
            except Exception as e:
                logger.error(f"Error en TrackerService loop: {e}")
                await asyncio.sleep(10)

    async def _process_trade_monitoring(self, trade: Dict[str, Any]):
        trade_id = trade["_id"]
        symbol = trade["symbol"]
        market_type = trade["marketType"]
        user_id_obj = trade["userId"]
        
        # Obtener user_id (openId) para los servicios
        user = await db.users.find_one({"_id": user_id_obj})
        if not user:
            return
        user_id = user["openId"]

        try:
            # 2. Obtener precio actual (ahora delegando correctamente a DEX/CEX)
            current_price = await self._get_current_price(symbol, market_type, user_id)
            if not current_price or current_price <= 0:
                return

            # Actualizar precio actual en la colección 'trades'
            await db.trades.update_one(
                {"_id": trade_id},
                {"$set": {
                    "currentPrice": current_price,
                    "lastMonitoredAt": datetime.utcnow()
                }}
            )

            # EMITIR POR SOCKET
            from api.services.socket_service import socket_service
            await socket_service.emit_to_user(user_id, "trade_update", {
                "id": str(trade_id),
                "currentPrice": current_price,
                "status": trade["status"],
                "lastMonitoredAt": datetime.utcnow().isoformat()
            })

            # ... resto de la lógica de TP/SL ...
            # 3. Lógica de proximidad y frecuencia
            if trade["status"] == "monitoring":
                target = trade.get("targetPrice") or trade.get("entryPrice")
                if target:
                    diff_pct = abs(current_price - target) / target * 100
                    if diff_pct < 2.0:
                        logger.info(f"TrackerService: Proximidad detectada para {symbol} ({diff_pct:.2f}%).")
                        await self._high_frequency_monitor(trade, target, "BUY", user_id)

            elif trade["status"] == "open":
                for tp in trade.get("takeProfits", []):
                    if current_price >= tp["price"]:
                        await self._high_frequency_monitor(trade, tp["price"], "SELL", user_id, tp_data=tp)
                        break
                
                sl = trade.get("stopLoss")
                if sl and current_price <= sl:
                    await self._execute_trade_action(trade, "SELL", "STOP_LOSS", user_id)

        except Exception as e:
            logger.error(f"Error procesando monitoreo para trade {trade_id}: {e}")

    async def _get_current_price(self, symbol: str, market_type: str, user_id: str) -> float:
        try:
            if market_type == "DEX":
                return await self.dex_service.get_current_price(symbol, user_id)
            else:
                return await self.cex_service.get_current_price(symbol, user_id)
        except Exception as e:
            logger.error(f"TrackerService: Error obteniendo precio para {symbol}: {e}")
            return 0.0

    async def _high_frequency_monitor(self, trade: Dict[str, Any], target: float, side: str, user_id: str, tp_data=None):
        """Monitoreo cada pocos segundos cuando el precio está cerca del objetivo"""
        logger.info(f"Alta frecuencia iniciada para {trade['symbol']} ({side})")
        
        last_price = target
        waiting_for_maximization = False
        grace_start_time = None
        
        # Intentar maximizar durante un máximo de 5 minutos o hasta que la tendencia cambie
        for _ in range(60): # 60 * 5s = 5 mins
            current_price = await self._get_current_price(trade["symbol"], trade["marketType"], user_id)
            
            if side == "BUY":
                # En compra, queremos el precio más bajo posible
                if current_price < last_price:
                    # El precio sigue bajando, esperamos para comprar más barato
                    waiting_for_maximization = True
                    grace_start_time = datetime.utcnow()
                    logger.info(f"Maximizando COMPRA: {current_price} < {last_price}. Esperando...")
                elif waiting_for_maximization and current_price > last_price * 1.002: # Rebote del 0.2%
                    logger.info(f"Maximización terminada (Rebote detectado): Comprando a {current_price}")
                    break
            else:
                # En venta, queremos el precio más alto posible
                if current_price > last_price:
                    # El precio sigue subiendo, esperamos para vender más caro
                    waiting_for_maximization = True
                    grace_start_time = datetime.utcnow()
                    logger.info(f"Maximizando VENTA: {current_price} > {last_price}. Esperando...")
                elif waiting_for_maximization and current_price < last_price * 0.998: # Caída del 0.2%
                    logger.info(f"Maximización terminada (Caída detectada): Vendiendo a {current_price}")
                    break
            
            last_price = current_price
            await asyncio.sleep(5) # Alta frecuencia: cada 5 segundos

        # Ejecutar la acción final
        action_type = "TAKE_PROFIT" if tp_data else "ENTRY"
        await self._execute_trade_action(trade, side, action_type, user_id, tp_data)

    async def _execute_trade_action(self, trade: Dict[str, Any], side: str, action_type: str, user_id: str, tp_data=None):
        trade_id = trade["_id"]
        symbol = trade["symbol"]
        market_type = trade["marketType"]
        
        logger.info(f"EJECUTANDO ORDEN: {side} {symbol} por {action_type} para usuario {user_id}")
        
        try:
            # Re-usar lógica existente de los servicios
            # Nota: AnálisisResult ficticio para no refactorizar todo execute_trade aún
            from api.models.schemas import AnalysisResult
            analysis = AnalysisResult(
                decision=side,
                symbol=symbol,
                market_type=market_type,
                confidence=1.0,
                reasoning=f"Ejecución automática por TrackerService ({action_type})",
                parameters={
                    "amount": trade["amount"],
                    "leverage": trade.get("leverage", 1),
                    "tp": trade.get("takeProfits", []),
                    "sl": trade.get("stopLoss")
                }
            )

            if market_type == "DEX":
                result = await self.dex_service.execute_trade(analysis, user_id=user_id)
            else:
                result = await self.cex_service.execute_trade(analysis, user_id=user_id)

            if result.success:
                status = "open" if action_type == "ENTRY" else "closed"
                
                # Obtener el precio actual para el registro final
                current_price = await self._get_current_price(symbol, market_type, user_id)
                
                update_data = {
                    "status": status, 
                    "executedAt": datetime.utcnow(),
                    "exitPrice": current_price if status == "closed" else None
                }
                
                await db.trades.update_one({"_id": trade_id}, {"$set": update_data})
                
                # EMITIR POR SOCKET
                from api.services.socket_service import socket_service
                await socket_service.emit_to_user(user_id, "trade_update", {
                    "id": str(trade_id),
                    "status": status,
                    "executedAt": datetime.utcnow().isoformat(),
                    "action": action_type,
                    "price": current_price
                })
                
                logger.info(f"TrackerService: Orden {action_type} ejecutada con éxito para {symbol}")
            else:
                logger.error(f"TrackerService: Fallo al ejecutar orden {action_type} para {symbol}: {result.message}")

        except Exception as e:
            logger.error(f"Error en _execute_trade_action para {trade_id}: {e}")

# tracker_service = TrackerService() # Eliminado para instanciar en main.py con servicios compartidos
