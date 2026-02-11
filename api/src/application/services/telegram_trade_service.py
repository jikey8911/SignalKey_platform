import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
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
        Orquesta el ciclo de vida eficiente: Pasivo -> Alerta (0.5%) -> Activo -> Ejecutar o Dormir (0.7%).
        """
        trade_id = str(trade_doc["_id"])
        symbol = trade_doc["symbol"]
        exchange_id = trade_doc.get("exchangeId", "binance")
        entry_target = trade_doc["entryPrice"]

        logger.info(f"🔄 Iniciando flujo de trabajo para {symbol} ({trade_id}) - Objetivo: {entry_target}")

        try:
            while True:
                # Actualizar estado desde DB por si hubo cambios externos
                current_trade = await db.telegram_trades.find_one({"_id": trade_doc["_id"]})
                if not current_trade or current_trade.get("status") in ["closed", "cancelled"]:
                    break

                status = current_trade.get("status", "waiting_entry")

                if status == "waiting_entry":
                    # --- FASE 1: ESPERA PASIVA (Alert Manager) ---
                    # El alert manager se queda esperando hasta que el precio esté cerca (0.5%)
                    # Esto evita consumo de recursos en monedas lejos del precio
                    price_at_alert = await self.alert_manager.wait_for_proximity(
                        exchange_id, symbol, entry_target, threshold=0.005
                    )

                    logger.info(f"🔔 ALERTA ACTIVADA: {symbol} en {price_at_alert} (Cerca de {entry_target}). Iniciando monitoreo activo.")

                    # --- FASE 2: MONITOREO ACTIVO (High Frequency) ---
                    # Entramos en un bucle rápido para intentar cazar el precio exacto
                    executed = await self._active_monitoring_loop(current_trade)

                    if executed:
                        logger.info(f"✅ Orden EJECUTADA para {symbol}. Pasando a gestión de posición.")
                        # El trade ya cambió de estado a 'active' dentro del loop, el while principal lo recogerá
                    else:
                        logger.info(f"💤 Precio se alejó (0.7%). Volviendo a modo pasivo para {symbol}.")
                        # El bucle retornó False, significa que se alejó > 0.7%, volvemos al inicio del while (wait_for_proximity)
                        await asyncio.sleep(1) # Pequeña pausa antes de reactivar la alerta

                elif status == "active":
                    # Si ya está activa, monitoreamos TP/SL
                    # Aquí también podríamos usar alertas para TP/SL si están lejos,
                    # pero por seguridad de la posición solemos mantener monitoreo activo o alertas en el exchange.
                    # Para simulación, mantenemos monitoreo activo pero con sleep más relajado si quisiéramos.
                    # Por ahora, usamos el mismo loop activo para gestionar salida.
                    await self._active_monitoring_loop(current_trade)
                    break # Si sale del loop de active es porque cerró

        except asyncio.CancelledError:
            logger.info(f"Flujo de trade {trade_id} cancelado.")
        except Exception as e:
            logger.error(f"Error crítico en workflow de trade {trade_id}: {e}", exc_info=True)
        finally:
            if trade_id in self.active_monitors:
                del self.active_monitors[trade_id]

    async def _active_monitoring_loop(self, trade: Dict[str, Any]) -> bool:
        """
        Bucle de monitoreo activo. Retorna True si se ejecutó una acción de cambio de estado (Entrada/Salida),
        Retorna False si el precio se alejó del objetivo (Sleep Condition).
        """
        trade_id = str(trade["_id"])
        symbol = trade["symbol"]
        exchange_id = trade.get("exchangeId", "binance")
        entry_price = trade["entryPrice"]

        # Suscripción a updates rápidos (Ticker o Trades)
        # Para optimizar, usamos ticker pero frecuente.
        
        while True:
            try:
                # 1. Obtener precio actual
                ticker = await self.stream_service.subscribe_ticker(exchange_id, symbol)
                current_price = float(ticker.get('last', 0))
                
                if current_price == 0:
                    await asyncio.sleep(1)
                    continue

                # 2. Verificar condición de DORMIR (Solo si estamos esperando entrada)
                if trade["status"] == "waiting_entry":
                    distancia = abs(current_price - entry_price) / entry_price
                    if distancia > 0.007: # 0.7% lejos
                        return False # Volver a modo pasivo

                # 3. Ejecutar Lógica de Trading (Entrada o Salida)
                state_changed = await self._update_trade_logic(trade, current_price)

                if state_changed:
                    return True # Acción realizada

                # Si el trade se cerró externamente
                if trade.get("status") == "closed":
                    return True

                await asyncio.sleep(0.5) # Frecuencia de actualización activa

            except Exception as e:
                logger.error(f"Error en loop activo {symbol}: {e}")
                await asyncio.sleep(1)

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
            
            # Tasks de Take Profit
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
                "marketType": analysis.market_type.value, # e.g. "futures", "spot"
                "side": analysis.direction.value, # "LONG", "SHORT"
                "entryPrice": analysis.parameters.entry_price,
                "stopLoss": analysis.parameters.sl,
                "takeProfits": tp_tasks,
                "investment": analysis.parameters.investment or analysis.parameters.amount or 100.0,
                "leverage": analysis.parameters.leverage or 1,
                "pnl": 0.0,
                "status": "waiting_entry", 
                "mode": mode,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow()
            }

            result_id = await self.trade_repository.create_trade(trade_doc)
            trade_id = str(result_id)
            trade_doc["_id"] = trade_doc["_id"] # ObjectId already set by repo usually, but ensure consistency
            if not isinstance(trade_doc["_id"], ObjectId):
                 trade_doc["_id"] = ObjectId(trade_id)

            # Iniciar el flujo de trabajo
            task_key = trade_id
            if task_key not in self.active_monitors:
                self.active_monitors[task_key] = asyncio.create_task(
                    self.manage_trade_workflow(trade_doc)
                )

            logger.info(f"Telegram trade created: {trade_id} for {symbol} ({mode})")
            
            await socket_service.emit_to_user(user_id, "telegram_trade_new", {**trade_doc, "id": trade_id, "_id": trade_id})

            return ExecutionResult(success=True, message="Trade de Telegram registrado", details={"tradeId": trade_id})

        except Exception as e:
            logger.error(f"Error creating telegram trade: {e}")
            return ExecutionResult(success=False, message=str(e))

    async def _update_trade_logic(self, trade: Dict[str, Any], current_price: float) -> bool:
        """
        Ejecuta la lógica de negocio: Entradas, TP, SL.
        Retorna True si hubo un cambio de estado significativo.
        """
        trade_id = trade["_id"]
        status = trade["status"]
        side = trade["side"] # LONG / SHORT
        entry_price = trade["entryPrice"]
        sl_price = trade["stopLoss"]
        tp_levels = trade.get("takeProfits", [])
        user_id = trade["userId"]
        mode = trade.get("mode", "simulated")
        exchange_id = trade.get("exchangeId", "binance")
        market_type = trade.get("marketType", "spot")
        investment = trade.get("investment", 100.0)
        leverage = trade.get("leverage", 1)

        # Determinar asset (USDT)
        quote_asset = symbol = trade["symbol"].split("/")[1] if "/" in trade["symbol"] else "USDT"

        updates = {"updatedAt": datetime.utcnow()}
        state_changed = False

        # --- LÓGICA DE ENTRADA ---
        if status == "waiting_entry":
            hit_entry = False
            # Lógica simple de cruce o toque
            # Si es LONG y precio baja a entry (o estamos por debajo y sube? Asumimos Limit order logic: Toca precio)
            # Simplificación: Si el precio está "en rango" o cruza.
            # Al ser monitoreo activo, si current_price <= entry (LONG) o >= entry (SHORT)
            # Pero cuidado con gaps. Asumimos si toca o cruza favorablemente.

            if side == "LONG" and current_price <= entry_price * 1.001: # Margen 0.1% tolerancia arriba
                hit_entry = True
            elif side == "SHORT" and current_price >= entry_price * 0.999:
                hit_entry = True

            if hit_entry:
                logger.info(f"🚀 EJECUTANDO ENTRADA {trade_id} {symbol} @ {current_price} ({mode})")
                
                exec_success = True
                if mode == "real":
                    # ... Lógica Real ...
                    ccxt_side = "buy" if side == "LONG" else "sell"
                    amount_to_trade = (investment * leverage) / current_price
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
                            logger.error(f"Real entry failed: {res.get('message')}")
                    except Exception as e:
                        exec_success = False
                        logger.error(f"Exception real entry: {e}")
                else:
                    # --- MODO SIMULADO: DESCONTAR SALDO ---
                    # Restamos la inversión del balance virtual
                    # Asumimos margen aislado: se descuenta 'investment'
                    await update_virtual_balance(user_id, market_type, quote_asset, -investment, is_relative=True)
                    logger.info(f"💰 [SIM] Descontados {investment} {quote_asset} por entrada {symbol}")

                if exec_success:
                    updates["status"] = "active"
                    updates["executedAt"] = datetime.utcnow()
                    updates["actualEntryPrice"] = current_price
                    trade["status"] = "active"
                    trade["actualEntryPrice"] = current_price
                    state_changed = True

        # --- LÓGICA DE GESTIÓN (ACTIVE) ---
        elif status == "active":
            actual_entry = trade.get("actualEntryPrice", entry_price)
            
            # Calcular PnL %
            pnl_percent = 0.0
            if actual_entry > 0:
                if side == "LONG":
                    pnl_percent = ((current_price - actual_entry) / actual_entry) * 100
                else:
                    pnl_percent = ((actual_entry - current_price) / actual_entry) * 100

            pnl_percent = pnl_percent * leverage
            updates["pnl"] = round(pnl_percent, 2)
            updates["currentPrice"] = current_price

            # 1. Verificar Stop Loss
            hit_sl = False
            if side == "LONG" and current_price <= sl_price: hit_sl = True
            if side == "SHORT" and current_price >= sl_price: hit_sl = True

            if hit_sl:
                logger.info(f"🛑 STOP LOSS {trade_id} {symbol} @ {current_price} (PnL: {pnl_percent:.2f}%)")
                
                exec_success = True
                if mode == "real":
                    # ... Close Real ...
                    pass
                else:
                    # --- MODO SIMULADO: DEVOLVER SALDO RESTANTE ---
                    # Retorno = Inversión + (Inversión * PnL%)
                    pnl_amount = investment * (pnl_percent / 100)
                    return_amount = investment + pnl_amount
                    if return_amount < 0: return_amount = 0 # No deuda

                    await update_virtual_balance(user_id, market_type, quote_asset, return_amount, is_relative=True)
                    logger.info(f"💰 [SIM] Retorno SL: {return_amount:.2f} {quote_asset}")

                if exec_success:
                    updates["status"] = "closed"
                    updates["exitPrice"] = current_price
                    updates["exitReason"] = "stop_loss"
                    updates["closedAt"] = datetime.utcnow()
                    updates["finalPnl"] = pnl_percent
                    state_changed = True

            else:
                # 2. Verificar Take Profits
                all_tp_hit = True
                tp_changed = False

                # Calcular cuánto volumen queda (simplificado: asumimos 1 TP cierra todo por ahora o parciales)
                # Si hay múltiples TPs, necesitamos trackear cuánto se vendió.
                # Para MVP: Si toca un TP, ejecutamos su % y devolvemos esa parte al balance.

                for tp in tp_levels:
                    if tp["status"] == "pending":
                        hit_tp = False
                        if side == "LONG" and current_price >= tp["price"]: hit_tp = True
                        if side == "SHORT" and current_price <= tp["price"]: hit_tp = True

                        if hit_tp:
                            logger.info(f"✅ TAKE PROFIT {tp['price']} hit for {symbol}")

                            percent_to_close = tp.get("percent", 100)
                            # Investment part to close
                            # Ojo: si tenemos varios TPs, 'investment' es el total inicial.
                            # Deberíamos trackear 'remaining_investment'.
                            # Simplificación: Asumimos que los porcentajes de los TPs suman 100% o son relativos al total.
                            # Usaremos: amount_to_release = TotalInvestment * (TpPercent / 100)

                            part_investment = investment * (percent_to_close / 100)

                            # Calcular ganancia de ESTA parte
                            # PnL actual aplicado a esta parte
                            pnl_amount = part_investment * (pnl_percent / 100)
                            return_amount = part_investment + pnl_amount

                            exec_success = True
                            if mode == "real":
                                # ... Close Part Real ...
                                pass
                            else:
                                await update_virtual_balance(user_id, market_type, quote_asset, return_amount, is_relative=True)
                                logger.info(f"💰 [SIM] Retorno TP: {return_amount:.2f} {quote_asset} ({percent_to_close}%)")

                            if exec_success:
                                tp["status"] = "hit"
                                tp["hitAt"] = datetime.utcnow()
                                tp_changed = True
                        else:
                            all_tp_hit = False

                if tp_changed:
                    updates["takeProfits"] = tp_levels
                    state_changed = True
                    if all_tp_hit:
                        updates["status"] = "closed"
                        updates["exitPrice"] = current_price
                        updates["exitReason"] = "take_profit"
                        updates["closedAt"] = datetime.utcnow()
                        updates["finalPnl"] = pnl_percent

        # Persistir
        await self.trade_repository.update_trade(trade_id, updates)

        # Actualizar objeto en memoria para el loop
        if state_changed:
            trade.update(updates)

        # Notificar Socket
        if state_changed or abs(updates.get("pnl", 0) - trade.get("last_pnl_emitted", 0)) > 0.5:
            await socket_service.emit_to_user(user_id, "telegram_trade_update", {
                "id": str(trade_id),
                "currentPrice": current_price,
                "pnl": updates.get("pnl", 0),
                "status": updates.get("status", status),
                "takeProfits": tp_levels,
                "exitReason": updates.get("exitReason")
            })
            trade["last_pnl_emitted"] = updates.get("pnl", 0)

        return state_changed
