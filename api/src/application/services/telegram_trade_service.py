import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
from bson import ObjectId
from api.src.adapters.driven.persistence.mongodb import db, update_virtual_balance, get_app_config
from api.src.domain.entities.signal import SignalAnalysis, Decision
from api.src.domain.models.schemas import ExecutionResult
from api.src.application.services.cex_service import CEXService
from api.src.domain.ports.output.telegram_repository_port import ITelegramTradeRepository
from api.src.adapters.driven.notifications.socket_service import socket_service

from api.src.application.services.price_alert_manager import PriceAlertManager
from api.src.adapters.driven.exchange.stream_service import MarketStreamService

logger = logging.getLogger(__name__)
class TelegramTradeService:
    def __init__(self, cex_service: CEXService, trade_repository: ITelegramTradeRepository, stream_service: MarketStreamService, alert_manager: PriceAlertManager):
        self.cex_service = cex_service
        self.trade_repository = trade_repository
        self.stream_service = stream_service
        self.alert_manager = alert_manager
        self.active_monitors: Dict[str, asyncio.Task] = {}
        logger.info("TelegramTradeService inicializado con PriceAlertManager.")

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
        Orquesta el ciclo de vida sin consumo constante de CPU.
        """
        trade_id = str(trade_doc["_id"])
        symbol = trade_doc["symbol"]
        exchange_id = trade_doc.get("exchangeId", "binance")
        status = trade_doc.get("status", "waiting_entry")

        try:
            # --- FASE 1: ESPERA PASIVA (Si está esperando entrada) ---
            if status == "waiting_entry":
                entry_target = trade_doc["entryPrice"]
                await self.alert_manager.wait_for_proximity(
                    exchange_id, symbol, entry_target
                )
                logger.info(f"🎯 ZONA DE ENTRADA detectada para {symbol}. Cambiando a monitoreo crítico.")

            # --- FASE 2: ACTIVACIÓN DE ALTO FLUJO ---
            # Suscribimos a Trades (Máxima resolución)
            await self.stream_service.subscribe_trades(exchange_id, symbol)
            
            # Iniciamos el bucle de ejecución crítico
            await self._ejecutar_monitoreo_critico(trade_doc)

        except asyncio.CancelledError:
            logger.info(f"Flujo de trade {trade_id} cancelado.")
        except Exception as e:
            logger.error(f"Error en workflow de trade {trade_id}: {e}", exc_info=True)
        finally:
            if trade_id in self.active_monitors:
                del self.active_monitors[trade_id]

    async def _ejecutar_monitoreo_critico(self, trade: Dict[str, Any]):
        """
        Bucle de alta frecuencia para ejecución inmediata.
        """
        trade_id = str(trade["_id"])
        symbol = trade["symbol"]
        exchange_id = trade.get("exchangeId", "binance")
        
        logger.info(f"🚀 Monitoreo CRÍTICO activado para {symbol} ({trade_id})")

        while True:
            # En esta fase, escuchamos el stream de trades (o ticker si trades falla)
            # Para simplificar y seguir el patrón, usamos subscribe_ticker pero el Manager ya despertó la zona
            # Sin embargo, para máxima precisión usamos la lógica que ya teníamos
            
            # Recargar trade de la DB para tener el estado más fresco si otros procesos lo tocan
            # (Aunque en este flujo el dueño es esta tarea)
            
            # Obtenemos precio actual (del stream ya activo en background)
            ticker_data = await self.stream_service.subscribe_ticker(exchange_id, symbol)
            current_price = ticker_data.get('last', 0)
            
            if current_price > 0:
                # Ejecutar la lógica de actualización
                await self._update_trade_logic(trade, current_price)
                
                # Si el trade se cerró, salimos del bucle
                if trade.get("status") == "closed":
                    logger.info(f"✅ Trade {trade_id} finalizado y cerrado.")
                    break

            await asyncio.sleep(0.5) # Resolución de 500ms en zona crítica es suficiente para la mayoría

    async def _subscribe_to_monitor(self, trade: Dict[str, Any]):
        # Obsoleto: Reemplazado por manage_trade_workflow
        task_key = str(trade["_id"])
        if task_key not in self.active_monitors:
            self.active_monitors[task_key] = asyncio.create_task(
                self.manage_trade_workflow(trade)
            )

    async def _on_price_update(self, trade: Dict[str, Any], current_price: float):
        # Obsoleto: Usado por monitor_price_with_alerts antiguo
        await self._update_trade_logic(trade, current_price)

    async def create_telegram_trade(self, analysis: SignalAnalysis, user_id: str, config: Dict[str, Any]) -> ExecutionResult:
        """
        Crea una nueva operación basada en una señal de Telegram.
        """
        try:
            symbol = analysis.symbol
            # Obtener el exchange ID oficial de la configuración del usuario
            exchange_id = "binance" # Default
            if config.get("exchanges") and len(config["exchanges"]) > 0:
                exchange_id = config["exchanges"][0].get("exchangeId", "binance").lower()

            mode = "simulated" if config.get("demoMode", True) else "real"
            
            # Preparar los niveles de TP (Tasks)
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
                "status": "waiting_entry", 
                "mode": mode,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow()
            }

            result_id = await self.trade_repository.create_trade(trade_doc)
            trade_id = str(result_id)
            trade_doc["_id"] = trade_id
            
            # Iniciar el flujo de trabajo orquestado
            await self._subscribe_to_monitor(trade_doc)

            logger.info(f"Telegram trade created: {trade_id} for {symbol} ({mode})")
            
            # Notificar al frontend
            await socket_service.emit_to_user(user_id, "telegram_trade_new", {**trade_doc, "id": trade_id})

            return ExecutionResult(success=True, message="Trade de Telegram registrado", details={"tradeId": trade_id})

        except Exception as e:
            logger.error(f"Error creating telegram trade: {e}")
            return ExecutionResult(success=False, message=str(e))

    async def _update_trade_logic(self, trade: Dict[str, Any], current_price: float):
        trade_id = trade["_id"]
        status = trade["status"]
        side = trade["side"] # LONG / SHORT
        entry_price = trade["entryPrice"]
        sl_price = trade["stopLoss"]
        tp_levels = trade.get("takeProfits", [])
        user_id = trade["userId"]
        mode = trade.get("mode", "simulated")
        exchange_id = trade.get("exchangeId", "binance")
        investment = trade.get("investment", 100.0)

        updates = {"updatedAt": datetime.utcnow()}
        should_notify = False

        # 1. Lógica de Entrada
        if status == "waiting_entry":
            hit_entry = False
            if side == "LONG" and current_price >= entry_price: hit_entry = True
            if side == "SHORT" and current_price <= entry_price: hit_entry = True

            if hit_entry:
                logger.info(f"Telegram Trade {trade_id} hitting ENTRY at {current_price} ({mode})")
                
                exec_success = True
                if mode == "real":
                    ccxt_side = "buy" if side == "LONG" else "sell"
                    amount_to_trade = investment / current_price if current_price > 0 else 0
                    
                    try:
                        res = await self.cex_service.ccxt_provider.execute_trade(
                            symbol=trade["symbol"],
                            side=ccxt_side,
                            amount=amount_to_trade,
                            user_id=user_id,
                            exchange_id=exchange_id
                        )
                        if not res.get("success"):
                            exec_success = False
                            logger.error(f"Real entry failed for {trade_id}: {res.get('message')}")
                    except Exception as e:
                        exec_success = False
                        logger.error(f"Exception in real entry for {trade_id}: {e}")

                if exec_success:
                    updates["status"] = "active"
                    updates["executedAt"] = datetime.utcnow()
                    updates["actualEntryPrice"] = current_price
                    status = "active"
                    should_notify = True
                else:
                    return 

        # 2. Lógica de Monitoreo (PNL, SL, TP)
        actual_entry = trade.get("actualEntryPrice", entry_price)
        pnl = 0.0
        if actual_entry > 0:
            if side == "LONG":
                pnl = ((current_price - actual_entry) / actual_entry) * 100
            else:
                pnl = ((actual_entry - current_price) / actual_entry) * 100
        
        updates["pnl"] = round(pnl, 2)
        updates["currentPrice"] = current_price

        # 3. Verificar Stop Loss
        hit_sl = False
        if side == "LONG" and current_price <= sl_price: hit_sl = True
        if side == "SHORT" and current_price >= sl_price: hit_sl = True

        if hit_sl:
            logger.info(f"Telegram Trade {trade_id} hitting STOP LOSS at {current_price} ({mode})")
            
            exec_success = True
            if mode == "real":
                ccxt_side = "sell" if side == "LONG" else "buy"
                amount_to_close = investment / actual_entry if actual_entry > 0 else 0
                try:
                    await self.cex_service.ccxt_provider.execute_trade(
                        symbol=trade["symbol"],
                        side=ccxt_side,
                        amount=amount_to_close,
                        user_id=user_id,
                        exchange_id=exchange_id
                    )
                except Exception as e:
                    logger.error(f"Error closing Real SL: {e}")

            if exec_success:
                updates["status"] = "closed"
                updates["exitPrice"] = current_price
                updates["exitReason"] = "stop_loss"
                updates["closedAt"] = datetime.utcnow()
                should_notify = True
        else:
            # 4. Verificar Take Profits (Tasks)
            all_tp_hit = True
            tp_changed = False
            for tp in tp_levels:
                if tp["status"] == "pending":
                    hit_tp = False
                    if side == "LONG" and current_price >= tp["price"]: hit_tp = True
                    if side == "SHORT" and current_price <= tp["price"]: hit_tp = True
                    
                    if hit_tp:
                        logger.info(f"Telegram Trade {trade_id} hitting TP at {tp['price']} ({mode})")
                        
                        exec_success = True
                        if mode == "real":
                            ccxt_side = "sell" if side == "LONG" else "buy"
                            qty_to_sell = tp.get("qty") or (investment * (tp["percent"]/100)) / actual_entry
                            try:
                                await self.cex_service.ccxt_provider.execute_trade(
                                    symbol=trade["symbol"],
                                    side=ccxt_side,
                                    amount=qty_to_sell,
                                    user_id=user_id,
                                    exchange_id=exchange_id
                                )
                            except Exception as e:
                                logger.error(f"Error executing real TP {tp['price']}: {e}")
                                
                        if exec_success:
                            tp["status"] = "hit"
                            tp["hitAt"] = datetime.utcnow()
                            tp_changed = True
                    else:
                        all_tp_hit = False
                
            if tp_changed:
                updates["takeProfits"] = tp_levels
                should_notify = True
                if all_tp_hit:
                    updates["status"] = "closed"
                    updates["exitPrice"] = current_price
                    updates["exitReason"] = "all_tps_hit"
                    updates["closedAt"] = datetime.utcnow()
                    logger.info(f"Telegram Trade {trade_id} CLOSED: All TPs hit.")

        # Persistir cambios usando el repositorio
        await self.trade_repository.update_trade(trade_id, updates)

        # Notificar al usuario vía WebSocket si hubo cambios significativos o simplemente el ticker
        await socket_service.emit_to_user(user_id, "telegram_trade_update", {
            "id": str(trade_id),
            "currentPrice": current_price,
            "pnl": updates["pnl"],
            "status": updates.get("status", status),
            "takeProfits": tp_levels if tp_changed else None,
            "exitReason": updates.get("exitReason")
        })
