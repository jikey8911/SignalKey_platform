import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from api.src.adapters.driven.persistence.mongodb import update_virtual_balance
from api.src.domain.entities.signal import SignalAnalysis
from api.src.domain.models.schemas import ExecutionResult
from api.src.application.services.cex_service import CEXService
from api.src.domain.ports.output.telegram_repository_port import ITelegramTradeRepository, ITelegramPositionRepository
from api.src.adapters.driven.notifications.socket_service import socket_service
from api.src.application.services.price_alert_manager import PriceAlertManager
from api.src.adapters.driven.exchange.stream_service import MarketStreamService

logger = logging.getLogger(__name__)

class TelegramTradeService:
    def __init__(
        self, 
        cex_service: CEXService, 
        trade_repository: ITelegramTradeRepository, 
        position_repository: ITelegramPositionRepository,
        stream_service: MarketStreamService, 
        alert_manager: PriceAlertManager
    ):
        self.cex_service = cex_service
        self.trade_repository = trade_repository
        self.position_repository = position_repository
        self.stream_service = stream_service
        self.alert_manager = alert_manager
        self.active_monitors: Dict[str, asyncio.Task] = {}
        logger.info("TelegramTradeService inicializado con Smart Monitoring.")

    async def start(self):
        """
        Inicia el monitoreo de trades existentes reconstruyendo sus flujos de trabajo.
        """
        active_trades = await self.trade_repository.get_active_trades()
        
        for trade in active_trades:
            task_key = str(trade["_id"])
            if task_key not in self.active_monitors:
                self.active_monitors[task_key] = asyncio.create_task(
                    self.manage_trade_workflow(trade)
                )
            
        logger.info(f"TelegramTradeService iniciado: orquestando {len(active_trades)} flujos de trade.")

    async def manage_trade_workflow(self, trade_doc: Dict[str, Any]):
        """
        Orquesta el ciclo de vida con Smart Monitoring (Sueño/Vigilia).
        """
        trade_id = str(trade_doc["_id"])
        symbol = trade_doc["symbol"]
        exchange_id = trade_doc.get("exchangeId", "binance")
        
        logger.info(f"🌀 Iniciando workflow para {symbol} ({trade_id})")

        try:
            while True:
                # Recargar estado actual del trade desde DB
                # (Esto es importante si el trade cambió de estado en otra iteración)
                # En una implementación real, podríamos consultar la DB aquí si sospechamos cambios externos.
                status = trade_doc.get("status")

                if status in ["closed", "cancelled", "failed"]:
                    logger.info(f"Trade {trade_id} finalizado ({status}). Terminando workflow.")
                    break

                # Determinamos el precio objetivo para despertar
                # Si estamos esperando entrada, el target es entryPrice
                # Si estamos activos, el target son los TPs o SL más cercanos
                target_price = trade_doc.get("entryPrice") 
                if status == "active":
                    # Si está activo, ya deberíamos estar en monitoreo crítico, 
                    # pero si por alguna razón salimos (ej: reinicio), volvemos directo al loop crítico.
                    pass 
                
                # --- FASE 1: MODO SUEÑO (Espera Pasiva con Alertas) ---
                if status == "waiting_entry":
                    logger.info(f"💤 Trade {trade_id} durmiendo. Esperando proximidad (0.5%) a {target_price}")
                    
                    # Esperar a que el precio esté cerca (0.5%)
                    # wait_for_proximity usa Websocket ligero o polling lento
                    await self.alert_manager.wait_for_proximity(
                        exchange_id, symbol, target_price, threshold_percent=0.5
                    )
                    logger.info(f"🔔 ¡DESPERTANDO! {symbol} cerca de entrada. Activando monitoreo fuerte.")

                # --- FASE 2: MODO VIGILIA (Monitoreo Crítico) ---
                # Suscribimos a Trades/Ticker de alta frecuencia
                await self.stream_service.subscribe_trades(exchange_id, symbol)
                
                # Ejecutar bucle crítico. Retorna si:
                # 1. El trade se cierra (True)
                # 2. El precio se aleja demasiado (>0.7%) (False) -> Volver a dormir
                finished = await self._ejecutar_monitoreo_critico(trade_doc)
                
                if finished:
                    break
                else:
                    logger.info(f"📉 Precio se alejó (>0.7%). Trade {trade_id} vuelve a dormir.")
                    # Pequeña pausa para evitar rebotes instantáneos
                    await asyncio.sleep(5)

        except asyncio.CancelledError:
            logger.info(f"Flujo de trade {trade_id} cancelado.")
        except Exception as e:
            logger.error(f"Error en workflow de trade {trade_id}: {e}", exc_info=True)
        finally:
            if trade_id in self.active_monitors:
                del self.active_monitors[trade_id]

    async def _ejecutar_monitoreo_critico(self, trade: Dict[str, Any]) -> bool:
        """
        Bucle de alta frecuencia.
        Retorna True si el trade finalizó, False si debe volver a dormir.
        """
        trade_id = str(trade["_id"])
        symbol = trade["symbol"]
        exchange_id = trade.get("exchangeId", "binance")
        entry_price = trade.get("entryPrice")
        
        while True:
            # Obtenemos precio actual del stream (memoria)
            ticker_data = await self.stream_service.subscribe_ticker(exchange_id, symbol)
            current_price = ticker_data.get('last', 0)
            
            if current_price > 0:
                # Lógica de negocio (Entrada, TP, SL)
                trade_updated = await self._update_trade_logic(trade, current_price)
                
                # Si el trade finalizó
                if trade.get("status") in ["closed", "failed"]:
                    return True
                
                # Si sigue esperando entrada, verificar si se alejó para dormir
                if trade.get("status") == "waiting_entry":
                    dist_percent = abs(current_price - entry_price) / entry_price
                    if dist_percent > 0.007: # 0.7% de distancia
                        return False # Volver a dormir

            await asyncio.sleep(0.5) # Frecuencia de actualización

    async def create_telegram_trade(self, analysis: SignalAnalysis, user_id: str, config: Dict[str, Any]) -> ExecutionResult:
        """
        Crea una nueva operación basada en una señal de Telegram.
        """
        try:
            symbol = analysis.symbol
            exchange_id = "binance"
            if config.get("exchanges") and len(config["exchanges"]) > 0:
                exchange_id = config["exchanges"][0].get("exchangeId", "binance").lower()

            mode = "simulated" if config.get("demoMode", True) else "real"
            
            tp_tasks = []
            for tp in analysis.parameters.tp:
                tp_tasks.append({
                    "price": tp.price,
                    "percent": tp.percent,
                    "qty": tp.qty,
                    "status": "pending"
                })

            trade_doc = {
                "userId": user_id,
                "symbol": symbol,
                "exchangeId": exchange_id,
                "marketType": analysis.market_type.value,
                "side": analysis.direction.value,
                "entryPrice": analysis.parameters.entry_price,
                "stopLoss": analysis.parameters.sl,
                "takeProfits": tp_tasks,
                "investment": analysis.parameters.investment or analysis.parameters.amount or 100.0,
                "pnl": 0.0,
                "roi": 0.0,
                "status": "waiting_entry", 
                "mode": mode,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow()
            }

            result_id = await self.trade_repository.create_trade(trade_doc)
            trade_id = str(result_id)
            trade_doc["_id"] = trade_id
            
            # Iniciar monitoreo
            task_key = trade_id
            if task_key not in self.active_monitors:
                self.active_monitors[task_key] = asyncio.create_task(
                    self.manage_trade_workflow(trade_doc)
                )

            logger.info(f"Trade creado: {trade_id} | {symbol} | {mode}")
            await socket_service.emit_to_user(user_id, "telegram_trade_new", {**trade_doc, "id": trade_id})

            return ExecutionResult(success=True, message="Trade registrado", details={"tradeId": trade_id})

        except Exception as e:
            logger.error(f"Error creando trade: {e}")
            return ExecutionResult(success=False, message=str(e))

    async def _update_trade_logic(self, trade: Dict[str, Any], current_price: float):
        trade_id = str(trade["_id"])
        user_id = trade["userId"]
        mode = trade.get("mode", "simulated")
        status = trade["status"]
        side = trade["side"]
        entry_price = trade["entryPrice"]
        sl_price = trade["stopLoss"]
        investment = trade.get("investment", 100.0)
        
        updates = {"updatedAt": datetime.utcnow()}
        position_updates = {}
        should_notify = False

        # --- 1. ENTRADA ---
        if status == "waiting_entry":
            hit_entry = (side == "LONG" and current_price >= entry_price) or \
                        (side == "SHORT" and current_price <= entry_price) # Simplificación para trigger, idealmente cruce

            if hit_entry:
                logger.info(f"🚀 Trade {trade_id} ENTRADA alcanzada a {current_price}")
                
                success = True
                if mode == "real":
                    # Lógica CCXT Real
                    # success = await self.cex_service.execute...
                    pass
                else:
                    # SIMULACIÓN: Descontar saldo
                    await update_virtual_balance(user_id, "cex", "USDT", -investment, is_relative=True)
                
                if success:
                    updates["status"] = "active"
                    updates["executedAt"] = datetime.utcnow()
                    updates["actualEntryPrice"] = current_price
                    trade["status"] = "active" # Actualizar objeto local
                    trade["actualEntryPrice"] = current_price
                    should_notify = True
                    
                    # Crear Posición en Vivo
                    position_updates = {
                        "symbol": trade["symbol"],
                        "side": side,
                        "size": investment / current_price,
                        "entryPrice": current_price,
                        "currentPrice": current_price,
                        "pnl": 0.0,
                        "roi": 0.0,
                        "mode": mode,
                        "status": "OPEN"
                    }
                    await self.position_repository.upsert_position(trade_id, position_updates)

        # --- 2. MONITOREO ACTIVO ---
        elif status == "active":
            actual_entry = trade.get("actualEntryPrice", entry_price)
            
            # Calcular PNL
            if side == "LONG":
                roi = ((current_price - actual_entry) / actual_entry) * 100
            else:
                roi = ((actual_entry - current_price) / actual_entry) * 100
            
            pnl_value = (investment * roi) / 100
            
            updates["pnl"] = round(pnl_value, 2)
            updates["roi"] = round(roi, 2)
            
            # Actualizar Posición en Vivo (Frecuente)
            await self.position_repository.upsert_position(trade_id, {
                "currentPrice": current_price,
                "pnl": pnl_value,
                "roi": roi,
                "lastUpdate": datetime.utcnow()
            })

            # Verificar SL
            hit_sl = (side == "LONG" and current_price <= sl_price) or \
                     (side == "SHORT" and current_price >= sl_price)

            if hit_sl:
                logger.info(f"🛑 Trade {trade_id} STOP LOSS a {current_price}")
                updates["status"] = "closed"
                updates["exitReason"] = "stop_loss"
                updates["exitPrice"] = current_price
                updates["pnlFinal"] = pnl_value
                updates["closedAt"] = datetime.utcnow()
                trade["status"] = "closed"
                should_notify = True
                
                if mode == "simulated":
                    # Devolver remanente al balance
                    return_amount = investment + pnl_value # (Ej: 100 - 10 = 90)
                    await update_virtual_balance(user_id, "cex", "USDT", return_amount, is_relative=True)
                
                await self.position_repository.close_position(trade_id)

            else:
                # Verificar TPs
                take_profits = trade.get("takeProfits", [])
                tp_changed = False
                all_hit = True
                
                total_sold_percent = 0
                
                for tp in take_profits:
                    if tp["status"] == "pending":
                        hit_tp = (side == "LONG" and current_price >= tp["price"]) or \
                                 (side == "SHORT" and current_price <= tp["price"])
                        
                        if hit_tp:
                            logger.info(f"💰 Trade {trade_id} TP alcanzado a {current_price}")
                            tp["status"] = "hit"
                            tp["hitAt"] = datetime.utcnow()
                            tp_changed = True
                            
                            # Realizar venta parcial
                            percent_to_sell = tp["percent"] # Ej: 33.3
                            # Calcular ganancia parcial (aproximada para simulación)
                            # En simulación simple, asumimos que liberamos esa parte del capital + ganancia
                            
                            if mode == "simulated":
                                part_investment = investment * (percent_to_sell / 100)
                                part_pnl = (part_investment * roi) / 100
                                return_amount = part_investment + part_pnl
                                await update_virtual_balance(user_id, "cex", "USDT", return_amount, is_relative=True)

                        else:
                            all_hit = False
                    elif tp["status"] == "hit":
                        pass
                
                if tp_changed:
                    updates["takeProfits"] = take_profits
                    should_notify = True
                    if all_hit:
                        updates["status"] = "closed"
                        updates["exitReason"] = "take_profit_all"
                        updates["closedAt"] = datetime.utcnow()
                        trade["status"] = "closed"
                        await self.position_repository.close_position(trade_id)

        # Guardar cambios si hubo eventos importantes
        if should_notify or updates.get("status") != status:
            await self.trade_repository.update_trade(trade_id, updates)
            # Notificar al frontend
            await socket_service.emit_to_user(user_id, "telegram_trade_update", {
                "id": trade_id,
                **updates
            })
