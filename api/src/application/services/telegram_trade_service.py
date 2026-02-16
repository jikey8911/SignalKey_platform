import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from bson import ObjectId
from api.src.adapters.driven.persistence.mongodb import update_virtual_balance, db
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
        """Orquesta el ciclo de vida con Smart Monitoring (Sueño/Vigilia).

        Reglas:
        - Despertar cuando precio está a <= 0.5% del target
        - Volver a dormir cuando se aleja a > 0.7%

        Targets:
        - waiting_entry: entryPrice
        - active: 2 alertas concurrentes (next TP pendiente + SL)
        """
        trade_id = str(trade_doc["_id"])
        symbol = trade_doc["symbol"]
        exchange_id = trade_doc.get("exchangeId", "binance")

        logger.info(f"🌀 Iniciando workflow para {symbol} ({trade_id})")

        try:
            while True:
                status = trade_doc.get("status")

                if status in ["closed", "cancelled", "failed"]:
                    logger.info(f"Trade {trade_id} finalizado ({status}). Terminando workflow.")
                    break

                # --- FASE 1: MODO SUEÑO (Alertas pasivas) ---
                sleep_targets: list[float] = []

                if status == "waiting_entry":
                    entry_price = trade_doc.get("entryPrice")
                    if not entry_price:
                        logger.warning(f"Trade {trade_id} sin entryPrice. Durmiendo 5s.")
                        await asyncio.sleep(5)
                        continue

                    logger.info(f"💤 Trade {trade_id} durmiendo. Esperando proximidad (0.5%) a entrada {entry_price}")
                    await self.alert_manager.wait_for_proximity(
                        exchange_id, symbol, float(entry_price), market_type=trade_doc.get("marketType"), threshold_percent=0.5
                    )
                    logger.info(f"🔔 ¡DESPERTANDO! {symbol} cerca de entrada. Activando monitoreo fuerte.")
                    sleep_targets = [float(entry_price)]
                    
                    # Actualizar estado de la alerta de entrada en DB
                    try:
                        await self.trade_repository.update_trade_item_status(trade_id, "entry", "hit")
                    except Exception as e:
                        logger.warning(f"No se pudo actualizar estado de alerta entry para {trade_id}: {e}")

                elif status == "active":
                    # Crear 2 alertas: next TP y SL (si existen)
                    sl = trade_doc.get("stopLoss")

                    # Choose the nearest pending TP to the *current* price
                    ticker = await self.stream_service.subscribe_ticker(exchange_id, symbol, market_type=trade_doc.get("marketType"))
                    current_price = float(ticker.get("last", 0) or 0)

                    pending_tps = []
                    for tp in (trade_doc.get("takeProfits") or []):
                        if tp.get("status") == "pending" and tp.get("price") is not None:
                            try:
                                pending_tps.append(float(tp["price"]))
                            except Exception:
                                continue

                    next_tp = None
                    if pending_tps and current_price > 0:
                        next_tp = min(pending_tps, key=lambda p: abs(p - current_price))
                    elif pending_tps:
                        # Fallback if price is unknown
                        next_tp = pending_tps[0]

                    tasks = []
                    if sl:
                        tasks.append(asyncio.create_task(
                            self.alert_manager.wait_for_proximity(exchange_id, symbol, float(sl), market_type=trade_doc.get("marketType"), threshold_percent=0.5)
                        ))
                        sleep_targets.append(float(sl))
                    if next_tp is not None:
                        tasks.append(asyncio.create_task(
                            self.alert_manager.wait_for_proximity(exchange_id, symbol, float(next_tp), market_type=trade_doc.get("marketType"), threshold_percent=0.5)
                        ))
                        sleep_targets.append(float(next_tp))

                    if tasks:
                        logger.info(
                            f"💤 Trade {trade_id} (active) durmiendo. Alertas 0.5% para: "
                            f"SL={sl} TP={next_tp}"
                        )
                        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                        for p in pending:
                            p.cancel()
                        logger.info(f"🔔 ¡DESPERTANDO! {symbol} cerca de TP/SL. Activando monitoreo fuerte.")
                    else:
                        # Sin SL ni TP pendientes: mantener monitoreo fuerte ligero
                        logger.info(f"Trade {trade_id} active sin SL/TP pendientes. Monitoreo continuo.")

                # --- FASE 2: MODO VIGILIA (Monitoreo crítico) ---
                await self.stream_service.subscribe_trades(exchange_id, symbol)

                finished = await self._ejecutar_monitoreo_critico(trade_doc, sleep_targets=sleep_targets)

                if finished:
                    break

                logger.info(f"📉 Precio se alejó (>0.7%). Trade {trade_id} vuelve a dormir.")
                await asyncio.sleep(5)

        except asyncio.CancelledError:
            logger.info(f"Flujo de trade {trade_id} cancelado.")
        except Exception as e:
            logger.error(f"Error en workflow de trade {trade_id}: {e}", exc_info=True)
        finally:
            if trade_id in self.active_monitors:
                del self.active_monitors[trade_id]

    async def _ejecutar_monitoreo_critico(self, trade: Dict[str, Any], sleep_targets: Optional[List[float]] = None) -> bool:
        """Bucle de alta frecuencia.

        - Retorna True si el trade finalizó.
        - Retorna False si debe volver a dormir (precio se aleja >0.7% del target relevante).

        `sleep_targets`: lista de precios objetivo relevantes para la fase actual
        (ej: [entry] o [sl, next_tp]).
        """
        symbol = trade["symbol"]
        exchange_id = trade.get("exchangeId", "binance")
        entry_price = trade.get("entryPrice")

        while True:
            ticker_data = await self.stream_service.subscribe_ticker(exchange_id, symbol, market_type=trade.get("marketType"))
            current_price = float(ticker_data.get("last", 0) or 0)

            if current_price > 0:
                await self._update_trade_logic(trade, current_price)

                if trade.get("status") in ["closed", "failed"]:
                    return True

                # Decide si vuelve a dormir por alejamiento >0.7%
                targets = [t for t in (sleep_targets or []) if t]
                if not targets and entry_price:
                    targets = [float(entry_price)]

                if targets:
                    nearest = min(targets, key=lambda t: abs(current_price - t))
                    dist_percent = abs(current_price - nearest) / nearest
                    if dist_percent > 0.007:
                        return False

            await asyncio.sleep(0.5)

    async def create_telegram_trade(self, analysis: SignalAnalysis, user_id: str, config: Dict[str, Any], signal_id: str = None) -> ExecutionResult:
        """
        Crea una nueva operación basada en una señal de Telegram.
        """
        try:
            symbol = str(analysis.symbol or "").strip().replace("#", "")

            # Prefer explicit overrides (from telegram_bots) over global config.exchanges[0]
            exchange_id = (config.get("telegramExchangeId") or config.get("telegram_exchange_id") or "").strip().lower()
            if not exchange_id:
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
                "signalId": signal_id,
                "symbol": symbol,
                "exchangeId": exchange_id,
                "marketType": analysis.market_type.value,
                "side": analysis.direction.value,
                "entryPrice": analysis.parameters.entry_price,
                # SL current + immutable initial snapshot (useful for UI charting)
                "stopLoss": analysis.parameters.sl,
                "stopLossInitial": analysis.parameters.sl,
                # History of SL movements for UI charting
                "stopLossHistory": [],
                "takeProfits": tp_tasks,
                "investment": analysis.parameters.investment or analysis.parameters.amount or 100.0,
                "pnl": 0.0,
                "roi": 0.0,
                "status": "waiting_entry",
                "mode": mode,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow(),
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
                    trade["status"] = "active"  # Actualizar objeto local
                    trade["actualEntryPrice"] = current_price
                    should_notify = True

                    # Ensure SL history captures the initial SL at entry time
                    hist = list(trade.get("stopLossHistory") or [])
                    hist.append({
                        "from": None,
                        "to": float(trade.get("stopLoss")) if trade.get("stopLoss") is not None else None,
                        "trigger": "entry",
                        "tpPrice": None,
                        "atPrice": current_price,
                        "timestamp": datetime.utcnow(),
                    })
                    updates["stopLossHistory"] = hist
                    trade["stopLossHistory"] = hist

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
                        "status": "OPEN",
                        "stopLoss": float(trade.get("stopLoss")) if trade.get("stopLoss") is not None else None,
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
                
                # Actualizar estado de la alerta SL en DB
                try:
                    await self.trade_repository.update_trade_item_status(trade_id, "sl", "hit")
                except Exception as e:
                    logger.warning(f"No se pudo actualizar estado de alerta SL para {trade_id}: {e}")
                
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
                            tp["hitPrice"] = current_price
                            tp["roiAtHit"] = roi
                            tp_changed = True
                            
                            # Actualizar estado de la alerta TP en DB
                            try:
                                # Usamos el precio para identificar el TP específico en la colección telegram_trades
                                await db["telegram_trades"].update_one(
                                    {
                                        "botId": ObjectId(trade_id) if isinstance(trade_id, str) and len(trade_id) == 24 else trade_id,
                                        "kind": "tp",
                                        "targetPrice": tp["price"]
                                    },
                                    {"$set": {"status": "hit", "updatedAt": datetime.utcnow()}}
                                )
                            except Exception as e:
                                logger.warning(f"No se pudo actualizar estado de alerta TP para {trade_id}: {e}")

                            # Trailing SL by TP ladder:
                            # - After TP1 hit -> SL moves to entry (break-even)
                            # - After TP2 hit -> SL moves to TP1 price
                            # - After TP3 hit -> SL moves to TP2 price ...
                            # Implementation: on each TP hit, set stopLoss to the *previous* protection price
                            # (last TP hit price, else entry), then update lastTpHitPrice to current TP price.
                            prev_protect = trade.get("lastTpHitPrice") or trade.get("actualEntryPrice", entry_price)
                            if prev_protect:
                                new_sl = float(prev_protect)
                                old_sl = trade.get("stopLoss")

                                updates["stopLoss"] = new_sl
                                trade["stopLoss"] = new_sl
                                should_notify = True

                                # Persist SL movement history for UI charting
                                hist = list(trade.get("stopLossHistory") or [])
                                hist.append({
                                    "from": float(old_sl) if old_sl is not None else None,
                                    "to": new_sl,
                                    "trigger": "tp_hit",
                                    "tpPrice": float(tp.get("price")) if tp.get("price") is not None else None,
                                    "atPrice": current_price,
                                    "timestamp": datetime.utcnow(),
                                })
                                updates["stopLossHistory"] = hist
                                trade["stopLossHistory"] = hist

                                # Reflect SL change in live position view
                                await self.position_repository.upsert_position(trade_id, {
                                    "stopLoss": new_sl,
                                    "lastUpdate": datetime.utcnow(),
                                })

                            # record this TP as last hit
                            try:
                                last_tp_price = float(tp.get("price"))
                                updates["lastTpHitPrice"] = last_tp_price
                                trade["lastTpHitPrice"] = last_tp_price
                            except Exception:
                                pass

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
