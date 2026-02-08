import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from api.src.adapters.driven.persistence.mongodb import db, save_trade, update_virtual_balance, get_app_config
from api.src.application.services.cex_service import CEXService
from api.src.application.services.dex_service import DEXService
from api.src.domain.models.schemas import AnalysisResult, ExecutionResult
from api.src.adapters.driven.exchange.stream_service import MarketStreamService
from api.src.application.services.buffer_service import DataBufferService
from api.src.application.services.ml_service import MLService
from api.src.adapters.driven.persistence.mongodb_signal_repository import MongoDBSignalRepository
from api.src.domain.entities.signal import Signal, SignalStatus, MarketType, Decision, TradingParameters

logger = logging.getLogger(__name__)

class SignalBotService:
    def __init__(self, cex_service: CEXService = None, dex_service: DEXService = None, ml_service: MLService = None):
        self.cex_service = cex_service or CEXService()
        self.dex_service = dex_service or DEXService()
        # MLService requires an exchange adapter, we use CEXService
        self.ml_service = ml_service or MLService(exchange_adapter=self.cex_service) 
        self.stream_service = MarketStreamService()
        self.buffer_service = DataBufferService(stream_service=self.stream_service, cex_service=self.cex_service)
        self.stream_service.add_listener(self.handle_market_update)
        self.signal_repository = MongoDBSignalRepository(db)

    async def start(self):
        """Starts the bot service, stream service, and initial monitoring."""
        await self.stream_service.start()
        await self.initialize_active_bots_monitoring()
        logger.info("SignalBotService started.")

    async def stop(self):
        """Stops the bot service."""
        await self.stream_service.stop()
        logger.info("SignalBotService stopped.")

    async def can_activate_bot(self, user_id: str, config: Dict[str, Any]) -> bool:
        """Verifica si el usuario puede activar un nuevo bot basado en su límite."""
        max_bots = config.get("botStrategy", {}).get("maxActiveBots", 5)
        active_bots_count = await db.trades.count_documents({
            "userId": user_id,
            "status": "active"
        })
        return active_bots_count < max_bots

    async def activate_bot(self, analysis: AnalysisResult, user_id: str, config: Dict[str, Any], bot_id: str = None, signal_id: str = None) -> ExecutionResult:
        """Activa un bot para una señal aprobada, manejando acumulación o cierre."""
        symbol = self.cex_service._normalize_symbol(analysis.symbol)
        
        # 1. Verificar si ya existe un bot activo para este símbolo/usuario
        existing_bot = await db.trades.find_one({
            "userId": user_id, 
            "symbol": symbol, 
            "status": "active"
        })
        
        if existing_bot:
            bot_side = existing_bot.get('side', 'BUY')
            signal_side = analysis.decision.upper()
            
            logger.info(f"Existing bot found for {symbol} ({bot_side}). Signal: {signal_side}")
            
            if bot_side == signal_side:
                # ACUMULACIÓN (Mismo lado)
                return await self._accumulate_position(existing_bot, analysis, user_id, config, bot_id)
            else:
                # CIERRE / REVERSO (Lado opuesto)
                return await self._close_position_by_signal(existing_bot, analysis, user_id, config, bot_id)

        # 2. Si no existe, lógica standard de creación (Nuevo Bot)
        if not await self.can_activate_bot(user_id, config):
            return ExecutionResult(success=False, message="Límite de bots activos alcanzado")

        demo_mode = config.get("demoMode", True)
        market_type = analysis.market_type
        
        # --- Capturar Timeframe ---
        # Prioridad: 1. Configuración explícita, 2. Parámetros del análisis, 3. Default 15m
        timeframe = config.get("timeframe") or analysis.parameters.get("timeframe", "15m")
        
        # Obtener precio actual
        current_price = await self.cex_service.get_current_price(symbol, user_id)
        if current_price <= 0:
            current_price = analysis.parameters.get("entry_price") or 0.0
            
        if current_price <= 0:
            return ExecutionResult(success=False, message=f"No se pudo obtener precio para {symbol}")

        # Determinar precios de TP y SL
        strategy = config.get("botStrategy", {})
        tp_levels_count = strategy.get("tpLevels", 3)
        tp_percent_step = strategy.get("tpPercent", 2.0)
        sl_percent = strategy.get("slPercent", 1.5)
        
        entry_price = current_price
        
        # Calcular niveles de TP
        take_profits = []
        ai_tps = analysis.parameters.get("tp", [])
        
        if ai_tps and len(ai_tps) > 0:
            for i, tp in enumerate(ai_tps):
                take_profits.append({
                    "level": i + 1,
                    "price": tp.get("price"),
                    "percent": tp.get("percent", strategy.get("sellPercentPerTP", 33.3)),
                    "status": "pending"
                })
        else:
            for i in range(1, tp_levels_count + 1):
                price = entry_price * (1 + (tp_percent_step * i / 100)) if analysis.decision.upper() == 'BUY' else entry_price * (1 - (tp_percent_step * i / 100))
                take_profits.append({
                    "level": i,
                    "price": price,
                    "percent": strategy.get("sellPercentPerTP", 33.3),
                    "status": "pending"
                })

        # Stop Loss
        stop_loss = analysis.parameters.get("sl")
        if not stop_loss:
            stop_loss = entry_price * (1 - (sl_percent / 100)) if analysis.decision.upper() == 'BUY' else entry_price * (1 + (sl_percent / 100))

        # Monto
        is_cex = market_type in ["CEX", "SPOT", "FUTURES"]
        max_amount = config.get("investmentLimits", {}).get("cexMaxAmount" if is_cex else "dexMaxAmount", 10.0)
        suggested_amount = analysis.parameters.get("amount", 0)
        amount = min(suggested_amount, max_amount) if suggested_amount > 0 else max_amount

        # Ejecutar trade inicial
        execution_result = None
        if is_cex:
            exec_analysis = AnalysisResult(
                decision=analysis.decision,
                symbol=symbol,
                market_type=analysis.market_type,
                confidence=analysis.confidence,
                reasoning=analysis.reasoning,
                parameters={
                    "entry_price": entry_price,
                    "amount": amount,
                    "tp": analysis.parameters.get("tp", []),
                    "sl": analysis.parameters.get("sl"),
                    "leverage": analysis.parameters.get("leverage", 1)
                }
            )
            # FIX: Pass exchange_id explicitly if available in config
            target_exchange = config.get("exchange_id")
            execution_result = await self.cex_service.execute_trade(exec_analysis, user_id, exchange_id=target_exchange)
        else:
            execution_result = await self.dex_service.execute_trade(analysis, user_id)

        if not execution_result.success:
            return execution_result

        trade_id = execution_result.order_id
        
        # Bot Document
        bot_doc = {
            "userId": user_id,
            "botInstanceId": bot_id, # Link to Bot Instance
            "signalId": signal_id, # Link to Signal
            "symbol": symbol,
            "timeframe": timeframe, # Timeframe para monitoreo de velas
            "side": analysis.decision.upper(),
            "entryPrice": entry_price,
            "currentPrice": current_price,
            "stopLoss": stop_loss,
            "takeProfits": take_profits,
            "amount": amount,
            "leverage": analysis.parameters.get("leverage", 1),
            "marketType": market_type,
            "isDemo": demo_mode,
            "status": "active",
            "orderId": trade_id,
            "currentTPLevel": 0,
            "pnl": 0.0,
            "createdAt": datetime.utcnow(),
            "history": [] 
        }

        # Handle CEXService double doc creation (Demo)
        inserted_id = None
        if demo_mode:
            # Buscar el trade que acaba de crear CEXService
            last_demo = await db.trades.find_one(
                {"userId": user_id, "symbol": symbol, "status": {"$in": ["open", "pending"]}, "isDemo": True},
                sort=[("createdAt", -1)]
            )
            if last_demo:
                await db.trades.update_one({"_id": last_demo["_id"]}, {"$set": bot_doc})
                inserted_id = last_demo["_id"]
            else:
                inserted_id = await save_trade(bot_doc)
        else:
            inserted_id = await save_trade(bot_doc)

        # Update Signal if exists
        if signal_id:
            await self.signal_repository.update(signal_id, {
                "status": SignalStatus.EXECUTING,
                "tradeId": str(inserted_id),
                "executionMessage": execution_result.message
            })

        # --- SAVE OPERATION LOG ---
        if bot_id:
            op_doc = {
                "botId": bot_id,
                "tradeId": str(inserted_id),
                "type": analysis.decision.upper(), # BUY/SELL
                "price": entry_price,
                "amount": amount,
                "timestamp": datetime.utcnow().isoformat(),
                "mode": "simulated" if demo_mode else "real",
                "reason": "ENTRY"
            }
            await db.bot_operations.insert_one(op_doc)
            from api.src.adapters.driven.notifications.socket_service import socket_service
            await socket_service.emit_to_user(user_id, "operation_update", op_doc)
        # --------------------------

        
        # Subscribe to WebSocket updates for this symbol
        # Assuming exchange is known or defaulting to 'binance' for now. 
        # In a real scenario, this comes from bot config or exchange service.
        exchange_id = config.get("exchange_id", "binance").lower()
        await self.stream_service.subscribe_ticker(exchange_id, symbol)

        return ExecutionResult(
            success=True, 
            message=execution_result.message,
            order_id=trade_id,
            details={"botId": str(inserted_id), "execution": execution_result.details}
        )

    async def _accumulate_position(self, existing_bot: Dict[str, Any], analysis: AnalysisResult, user_id: str, config: Dict[str, Any], bot_id: str = None) -> ExecutionResult:
        """Aumenta el tamaño de una posición existente (Dollar Cost Averaging)."""
        symbol = existing_bot['symbol']
        side = existing_bot['side'] # BUY/SELL
        demo_mode = config.get("demoMode", True)
        
        # 1. Definir Monto Adicional
        # Podríamos usar un % del balance restante o un fixed amount
        is_cex = existing_bot['marketType'] in ["CEX", "SPOT", "FUTURES"]
        max_amount = config.get("investmentLimits", {}).get("cexMaxAmount" if is_cex else "dexMaxAmount", 10.0)
        
        # Usamos el 95% del max_amount o lo que sugiera la IA
        amount_to_add = min(analysis.parameters.get("amount", max_amount), max_amount)
        
        logger.info(f"Accumulating {symbol} ({side}). Adding amount: {amount_to_add}")
        
        # 2. Ejecutar Trade
        # Reutilizamos execute_trade de CEXService para manejar balance y orden real
        exec_analysis = AnalysisResult(
            decision=analysis.decision, # SAME SIDE
            symbol=symbol,
            market_type=analysis.market_type,
            confidence=analysis.confidence,
            reasoning=f"Accumulation: {analysis.reasoning}",
            parameters={
                "amount": amount_to_add,
                "entry_price": analysis.parameters.get("entry_price"),
                "leverage": existing_bot.get("leverage", 1)
            }
        )
        
        # FIX: Pass exchange_id to accumulate on the SAME exchange
        target_exchange = existing_bot.get("exchangeId") or config.get("exchange_id")
        exec_result = await self.cex_service.execute_trade(exec_analysis, user_id, exchange_id=target_exchange)
        
        if not exec_result.success:
            return exec_result
            
        # 3. Fusionar datos
        # Si es Demo, CEXService creó un nuevo documento. Debemos absorberlo y ocultarlo.
        execution_price = 0.0
        
        if demo_mode:
            # Encontrar el trade "hijacked"
            child_trade = await db.trades.find_one(
                {"userId": user_id, "symbol": symbol, "status": {"$in": ["open", "pending"]}, "isDemo": True},
                sort=[("createdAt", -1)]
            )
            
            if child_trade and str(child_trade["_id"]) != str(existing_bot["_id"]):
                execution_price = child_trade.get("currentPrice") or child_trade.get("entryPrice")
                # Marcar child como merged para que no salga en lista activa
                await db.trades.update_one({"_id": child_trade["_id"]}, {"$set": {"status": "merged", "mergedInto": existing_bot["_id"]}})
            else:
                # Fallback weird case
                execution_price = existing_bot["currentPrice"]
        else:
            # Real mode: get price from execution details
            # TODO: Extract from exec_result.details if available
            execution_price = await self.cex_service.get_current_price(symbol, user_id)
            
        # 4. Calcular Weighted Average
        old_amount = existing_bot.get("amount", 0)
        old_entry = existing_bot.get("entryPrice", 0)
        
        total_amount = old_amount + amount_to_add
        new_entry_price = ((old_amount * old_entry) + (amount_to_add * execution_price)) / total_amount if total_amount > 0 else old_entry
        
        # 5. Actualizar Bot Principal
        history_entry = {
            "type": "ACCUMULATE",
            "amount": amount_to_add,
            "price": execution_price,
            "time": datetime.utcnow()
        }
        
        await db.trades.update_one(
            {"_id": existing_bot["_id"]},
            {
                "$set": {
                    "amount": total_amount,
                    "entryPrice": new_entry_price,
                    "lastAccumulatedAt": datetime.utcnow()
                },
                "$push": {"history": history_entry}
            }
        )

        # --- SAVE ACCUMULATE LOG ---
        if bot_id:
            op_doc = {
                "botId": bot_id,
                "tradeId": str(existing_bot["_id"]),
                "type": side, # Same side accumulation
                "price": execution_price,
                "amount": amount_to_add,
                "timestamp": datetime.utcnow().isoformat(),
                "mode": "simulated" if demo_mode else "real",
                "reason": "ACCUMULATE"
            }
            await db.bot_operations.insert_one(op_doc)
            from api.src.adapters.driven.notifications.socket_service import socket_service
            await socket_service.emit_to_user(user_id, "operation_update", op_doc)
        # ---------------------------
        
        return ExecutionResult(
            success=True,
            message=f"Posición acumulada exitosamente. Nuevo Avg Entry: {new_entry_price:.4f}",
            details={"new_entry": new_entry_price, "total_amount": total_amount}
        )

    async def _close_position_by_signal(self, existing_bot: Dict[str, Any], analysis: AnalysisResult, user_id: str, config: Dict[str, Any], bot_id: str = None) -> ExecutionResult:
        """Cierra una posición existente debido a una señal opuesta."""
        symbol = existing_bot['symbol']
        current_price = await self.cex_service.get_current_price(symbol, user_id)
        if current_price <= 0: current_price = existing_bot["currentPrice"]
        
        logger.info(f"Closing {symbol} due to opposite signal ({analysis.decision}).")
        
        # Ejecutar cierre (Venta si es BUY, Compra si es SELL)
        # Nota: execute_trade de CEXService está diseñado para ABRIR.
        # Para cerrar en REAL, necesitamos crear una orden opuesta por el monto total.
        # Para cerrar en DEMO, simplemente actualizamos estado y balance.
        
        demo_mode = config.get("demoMode", True)
        
        if demo_mode:
            # Solo actualizar DOC y Balance
            # Calcular retorno al balance
            amount = existing_bot["amount"]
            pnl_pct = 0
            
            if existing_bot["side"] == "BUY":
                 # Vender lo que se compró
                 coin_amount = amount / existing_bot["entryPrice"]
                 revenue = coin_amount * current_price
                 await update_virtual_balance(user_id, "CEX", "USDT", revenue, is_relative=True)
                 pnl_pct = ((current_price - existing_bot["entryPrice"]) / existing_bot["entryPrice"]) * 100
                 
            else: # SELL/SHORT
                 # Buy to cover
                 # Profit if Price < Entry
                 pnl_pct = ((existing_bot["entryPrice"] - current_price) / existing_bot["entryPrice"]) * 100
                 revenue = amount * (1 + (pnl_pct/100))
                 await update_virtual_balance(user_id, "CEX", "USDT", revenue, is_relative=True)

            await db.trades.update_one(
                {"_id": existing_bot["_id"]},
                {
                    "$set": {
                        "status": "closed",
                        "exitPrice": current_price,
                        "pnl": pnl_pct,
                        "closeReason": f"Opposite Signal: {analysis.decision}",
                        "executedAt": datetime.utcnow()
                    }
                }
            )

            # --- SAVE CLOSE LOG ---
            if bot_id:
                op_doc = {
                    "botId": bot_id,
                    "tradeId": str(existing_bot["_id"]),
                    "type": "SELL" if existing_bot["side"] == "BUY" else "BUY", # Opposite side
                    "price": current_price,
                    "amount": amount,
                    "timestamp": datetime.utcnow().isoformat(),
                    "mode": "simulated",
                    "reason": "CLOSE_SIGNAL"
                }
                await db.bot_operations.insert_one(op_doc)
                from api.src.adapters.driven.notifications.socket_service import socket_service
                await socket_service.emit_to_user(user_id, "operation_update", op_doc)
            # ----------------------
            
            return ExecutionResult(success=True, message=f"Posición cerrada por señal opuesta. PnL: {pnl_pct:.2f}%")
            
        else:
             # REAL MODE: CLOSE POSITION
             # Determinar lado opuesto para cerrar
             close_side = "SELL" if existing_bot["side"] == "BUY" else "BUY"

             logger.info(f"Closing REAL position for {symbol}. Side: {close_side}, Amount: {existing_bot['amount']}")

             # Crear análisis de cierre
             close_analysis = AnalysisResult(
                 decision=close_side,
                 symbol=symbol,
                 market_type=existing_bot.get("marketType", "CEX"),
                 confidence=1.0,
                 reasoning=f"Close Signal Triggered: {analysis.decision}",
                 parameters={
                     "amount": existing_bot["amount"],
                     "entry_price": current_price, # Market order
                     "leverage": existing_bot.get("leverage", 1)
                 }
             )

             # Ejecutar cierre a través de CEXService (que delega a CCXTAdapter)
             # FIX: Pass exchange_id to ensure closing on correct exchange
             target_exchange = existing_bot.get("exchangeId")
             close_result = await self.cex_service.execute_trade(close_analysis, user_id, exchange_id=target_exchange)

             if close_result.success:
                 # Actualizar DB
                 pnl = 0
                 exit_price = current_price

                 if close_result.details and "price" in close_result.details:
                      exit_price = float(close_result.details["price"])
                      entry_price = float(existing_bot["entryPrice"])
                      if existing_bot["side"] == "BUY":
                          pnl = ((exit_price - entry_price) / entry_price) * 100
                      else:
                          pnl = ((entry_price - exit_price) / entry_price) * 100

                 await db.trades.update_one(
                    {"_id": existing_bot["_id"]},
                    {
                        "$set": {
                            "status": "closed",
                            "exitPrice": exit_price,
                            "pnl": pnl,
                            "closeReason": f"Opposite Signal: {analysis.decision}",
                            "executedAt": datetime.utcnow()
                        }
                    }
                )
                 return ExecutionResult(success=True, message=f"Posición REAL cerrada. PnL: {pnl:.2f}%")
             else:
                 return ExecutionResult(success=False, message=f"Fallo al cerrar posición REAL: {close_result.message}")

    async def initialize_active_bots_monitoring(self):
        """Startup: Inicia monitoreo y WARM-UP basado en INSTANCIAS DE BOTS (Estrategias) y TRADES activos."""

        # 1. Recuperar Estrategias Activas (BotInstances) - Para generar señales de ENTRADA
        active_instances = await db.bot_instances.find({"status": "active"}).to_list(length=1000)

        # 2. Recuperar Trades Activos (Posiciones Abiertas) - Para gestionar SALIDA (TP/SL)
        # Sincronizamos 'active' (SignalBotService) vs 'open' (MonitorService)
        # MonitorService usa 'open', SignalBotService usaba 'active'. Unificamos consulta.
        active_trades = await db.trades.find({"status": {"$in": ["active", "open"]}}).to_list(length=1000)

        logger.info(f"Initializing monitoring for {len(active_instances)} active strategies and {len(active_trades)} active trades.")

        # Set para evitar duplicar suscripciones
        subscriptions = set()

        # A. Procesar Estrategias (Entradas)
        for bot in active_instances:
            # FIX: Determinar Exchange Correcto
            # Prioridad 1: 'exchangeId' (nuevo)
            # Prioridad 2: 'exchange_id' (legacy/alternativo)
            # Prioridad 3: Configuración del usuario
            exchange_id = bot.get("exchangeId") or bot.get("exchange_id")

            if not exchange_id:
                # Fallback: Consultar configuración del usuario
                try:
                    # FIX: Handle bot document keys safely (user_id vs userId)
                    u_id = bot.get("userId") or bot.get("user_id")
                    if u_id:
                        user_config = await get_app_config(u_id)
                        # Busca en 'activeExchange' o primer exchange activo
                        exchange_id = user_config.get("activeExchange")
                        if not exchange_id and user_config.get("exchanges"):
                             # Buscar el primer exchange activo
                             active_ex = next((e for e in user_config["exchanges"] if e.get("isActive")), None)
                             if active_ex:
                                 exchange_id = active_ex["exchangeId"]

                        if not exchange_id:
                             exchange_id = "binance" # Default absoluto
                    else:
                        exchange_id = "binance"
                except Exception as e:
                    logger.warning(f"Error resolving exchange for bot {bot.get('_id')}: {e}")
                    exchange_id = "binance"

            exchange_id = exchange_id.lower()
            logger.info(f"Using exchange '{exchange_id}' for bot {bot.get('name', 'Unknown')} ({bot.get('_id')})")

            symbol = bot["symbol"]
            timeframe = bot.get("timeframe", "15m")
            
            sub_key = f"{exchange_id}:{symbol}:{timeframe}"
            if sub_key not in subscriptions:
                # WARM-UP
                try:
                    await self.buffer_service.initialize_buffer(exchange_id, symbol, timeframe, limit=100)
                except Exception as e:
                    logger.error(f"Failed to initialize buffer for {sub_key}: {e}")

                # Suscribir a VELAS para señales IA
                await self.stream_service.subscribe_candles(exchange_id, symbol, timeframe)
                subscriptions.add(sub_key)

        # B. Procesar Trades (Salidas)
        for trade in active_trades:
            exchange_id = trade.get("exchangeId")
            if not exchange_id:
                # Fallback simple si no está en el trade
                exchange_id = "binance"

            symbol = trade["symbol"]
            
            # Suscribir a TICKER para TP/SL en tiempo real
            await self.stream_service.subscribe_ticker(exchange_id, symbol)

    async def handle_market_update(self, event_type: str, data: Dict[str, Any]):
        """Router de eventos centralizado."""
        
        # A. Actualización de Ticker (Para TP/SL en tiempo real)
        if event_type == "ticker_update":
            await self._handle_ticker_update(data)
            
        # B. Actualización de Vela (Para Señales IA - Solo al Cierre)
        elif event_type == "candle_update":
            await self._handle_candle_update(data)

    async def _handle_ticker_update(self, data: Dict[str, Any]):
        """Legacy logic moved here: TP/SL Checks on Price Change."""
        symbol = data.get("symbol")
        ticker = data.get("ticker", {})
        last_price = ticker.get("last")
        
        if not symbol or not last_price:
            return

        # Find bots for this symbol (Unified active/open)
        active_bots = await db.trades.find({"symbol": symbol, "status": {"$in": ["active", "open"]}}).to_list(length=None)
        
        if not active_bots:
            return
            
        # Process each bot with the new price info directly
        for bot in active_bots:
            await self._process_bot_tick(bot, current_price=last_price)

    async def _handle_candle_update(self, data: Dict[str, Any]):
        """
        Lógica Anti-Repainting: Solo dispara la IA cuando detecta una vela NUEVA.
        """
        symbol = data["symbol"]
        timeframe = data["timeframe"]
        incoming_candle = data["candle"] # {timestamp, close, ...}
        
        # 1. Buscar ESTRATEGIAS (BotInstances) activas para este símbolo
        relevant_instances = await db.bot_instances.find({
            "symbol": symbol, 
            "timeframe": timeframe, 
            "status": "active"
        }).to_list(length=None)
        
        if not relevant_instances: return

        exchange_id = data.get("exchange", "binance")
        
        # 1. Actualizar Buffer con la vela entrante (que puede ser la nueva formándose)
        await self.buffer_service.update_with_candle(exchange_id, symbol, timeframe, incoming_candle)
        full_history = self.buffer_service.get_latest_data(exchange_id, symbol, timeframe)
        
        for instance in relevant_instances:
            # RECUPERAR ESTADO DE LA ESTRATEGIA (no del trade)
            last_processed_ts = instance.get("lastCandleTimestamp", 0)
            current_candle_ts = incoming_candle["timestamp"]
            
            # --- CRITERIO DE CIERRE: Detectamos nueva vela ---
            if current_candle_ts > last_processed_ts:
                # --- FIX: Usar 'logger' global en lugar de 'self.logger' ---
                logger.info(f"⏱️ New Candle detected {current_candle_ts} vs {last_processed_ts} for {symbol}. Running AI on CLOSED candle...")
                
                # SOLUCIÓN LOOK-AHEAD / REPAINTING:
                if full_history is not None and not full_history.empty:
                    # Si el buffer tiene la nueva vela al final, la excluimos para la IA
                    last_buffer_ts = full_history.index[-1].value // 10 ** 6 # ms

                    history_for_ai = full_history
                    if last_buffer_ts >= current_candle_ts:
                         history_for_ai = full_history.iloc[:-1] # Excluir vela actual (forming)

                    if not history_for_ai.empty:
                         await self._execute_ai_pipeline(instance, history_for_ai)
                
                # 2. Actualizar Timestamp DE LA INSTANCIA para no repetir en esta vela
                await db.bot_instances.update_one(
                    {"_id": instance["_id"]},
                    {"$set": {"lastCandleTimestamp": current_candle_ts}}
                )

    async def _execute_ai_pipeline(self, instance: Dict[str, Any], candles_df: Any):
        """Llama al MLService y ejecuta operaciones si hay señal."""
        if candles_df is None or candles_df.empty:
            return

        # Convert DataFrame to list of dicts for MLService (or adapt MLService to accept DF)
        # MLService.predict takes List[Dict].
        candles_list = candles_df.reset_index().to_dict('records')
        
        # Obtener si hay posición abierta asociada para pasar al modelo (Optional)
        # Aquí buscamos si hay un trade activo para esta instancia
        active_trade = await db.trades.find_one({"botInstanceId": str(instance["_id"]), "status": "active"})

        current_pos = {
            "qty": 0.0,
            "avg_price": 0.0
        }

        if active_trade:
            current_pos = {
                "qty": active_trade.get("amount", 0) / active_trade.get("entryPrice", 1) if active_trade.get("entryPrice") else 0,
                "avg_price": active_trade.get("entryPrice", 0)
            }

        prediction = self.ml_service.predict(
            symbol=instance["symbol"],
            timeframe=instance["timeframe"],
            candles=candles_list,
            market_type=instance.get("marketType", "CEX"),
            strategy_name=instance.get("strategy_name", "auto"),
            current_position=current_pos
        )
        
        decision_str = prediction.get("decision", "HOLD")

        # --- 1. PERSIST SIGNAL ALWAYS ---
        # Map decision string to Enum
        try:
            decision_enum = Decision(decision_str.upper())
        except:
            decision_enum = Decision.HOLD

        # Prepare parameters from Analysis/Prediction
        # Nota: prediction["analysis"] podría tener detalles, pero 'activate_bot' construye AnalysisResult de nuevo.
        # Intento obtener parametros base.
        last_close = candles_list[-1]['close']

        signal_params = TradingParameters(
            entry_price=last_close,
            tp=[],
            sl=None
        )

        user_id_str = str(instance.get("userId") or instance.get("user_id") or "default_user")
        
        signal_entity = Signal(
            id=None,
            userId=user_id_str,
            source=f"BotInstance:{instance.get('_id')}",
            rawText=f"AI Prediction for {instance['symbol']} {instance['timeframe']}",
            status=SignalStatus.PROCESSING if decision_enum in [Decision.BUY, Decision.SELL] else SignalStatus.COMPLETED,
            createdAt=datetime.utcnow(),
            symbol=instance["symbol"],
            marketType=MarketType(instance.get("marketType", "CEX")),
            decision=decision_enum,
            confidence=prediction.get("confidence", 0.0), # Assuming ML service returns confidence
            reasoning=f"AI Strategy Used: {prediction.get('strategy_used', 'auto')}",
            riskScore=0.0,
            botId=str(instance["_id"]),
            parameters=signal_params
        )

        try:
            saved_signal = await self.signal_repository.save(signal_entity)
            logger.info(f"💾 Signal saved: {saved_signal.id} ({decision_enum})")
            
            # --- EMISIÓN SOCKET PARA MONITOR EN TIEMPO REAL ---
            from api.src.adapters.driven.notifications.socket_service import socket_service
            await socket_service.emit_to_user(user_id_str, "signal_update", saved_signal.to_dict())
            # --------------------------------------------------
        except Exception as e:
            logger.error(f"Error saving signal: {e}")
            saved_signal = signal_entity # Fallback without ID

        # --- 2. EXECUTE IF BUY/SELL ---
        if decision_enum in [Decision.BUY, Decision.SELL]:
             # If decision matches or reverses, activate_bot logic handles it.
             
             analysis = AnalysisResult(
                 decision=decision_str,
                 symbol=instance["symbol"],
                 market_type=instance.get("marketType", "CEX"),
                 confidence=0.0,
                 reasoning=f"Auto-Bot Signal: {decision_str}",
                 parameters={
                     "entry_price": last_close,
                     "tp": [],
                     "sl": None
                 }
             )
             
             # Call existing executor
             # We pass the saved signal ID to link it
             await self.activate_bot(analysis, user_id_str, config={}, bot_id=str(instance["_id"]), signal_id=saved_signal.id)

    async def _process_bot_tick(self, bot: Dict[str, Any], current_price: float = None) -> float:
        """
        Actualiza el estado de un bot individual basado en el precio actual.
        Retorna la distancia porcentual mínima al objetivo más cercano (TP o SL).
        """
        symbol = bot["symbol"]
        
        # Use provided price (WS) or fallback to fetch
        if current_price is None:
             current_price = await self._get_current_price(bot)
        
        if current_price <= 0:
            return 100.0 # No hay precio disponible, no aceleramos
            
        # Calcular P&L actual
        entry_price = bot["entryPrice"]
        side = bot.get("side", "BUY")
        
        if side == "BUY":
            pnl = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl = ((entry_price - current_price) / entry_price) * 100
            
        # 1. ACTUALIZAR BASE DE DATOS Y EMITIR POR SOCKET SIEMPRE
        try:
            await db.trades.update_one(
                {"_id": bot["_id"]},
                {"$set": {
                    "currentPrice": current_price,
                    "pnl": pnl,
                    "lastMonitoredAt": datetime.utcnow()
                }}
            )
            
            # Emitir actualización en tiempo real
            from api.src.adapters.driven.notifications.socket_service import socket_service
            user = await db.users.find_one({"_id": bot["userId"]})
            if user:
                await socket_service.emit_to_user(user["openId"], "bot_update", {
                    "id": str(bot["_id"]),
                    "symbol": symbol,
                    "currentPrice": current_price,
                    "pnl": pnl,
                    "status": bot["status"]
                })
        except Exception as e:
            logger.error(f"Error updating bot tick for {bot['_id']}: {e}")

        # 2. CALCULAR DISTANCIAS A OBJETIVOS PARA FRECUENCIA DINÁMICA
        # Distancia al Stop Loss
        dist_sl = abs(current_price - bot["stopLoss"]) / current_price * 100
        
        # Distancia al siguiente Take Profit pendiente
        dist_tp = 100.0
        pending_tps = [tp for tp in bot["takeProfits"] if tp["status"] == "pending"]
        if pending_tps:
            # Encontrar el TP más cercano al precio actual
            closest_tp_price = min([tp["price"] for tp in pending_tps]) if side == "BUY" else max([tp["price"] for tp in pending_tps])
            dist_tp = abs(current_price - closest_tp_price) / current_price * 100
            
        min_dist = min(dist_sl, dist_tp)

        # 3. VERIFICAR EJECUCIÓN (TP/SL)
        # Verificar Stop Loss
        if (side == "BUY" and current_price <= bot["stopLoss"]) or (side == "SELL" and current_price >= bot["stopLoss"]):
            await self._close_bot(bot, current_price, "failed", "Stop Loss alcanzado")
            return min_dist

        # Verificar Take Profits
        updated_tps = bot["takeProfits"]
        any_tp_hit = False
        for tp in updated_tps:
            is_hit = (side == "BUY" and current_price >= tp["price"]) or (side == "SELL" and current_price <= tp["price"])
            if tp["status"] == "pending" and is_hit:
                tp["status"] = "hit"
                tp["hitAt"] = datetime.utcnow()
                bot["currentTPLevel"] = tp["level"]
                any_tp_hit = True
                logger.info(f"Bot {bot['_id']} alcanzó TP Nivel {tp['level']} para {symbol} (MARKET EXECUTION)")

        if any_tp_hit:
            # Si todos los TP se alcanzaron, cerrar bot
            if all(tp["status"] == "hit" for tp in updated_tps):
                await self._close_bot(bot, current_price, "completed", "Todos los TP alcanzados")
            else:
                await db.trades.update_one(
                    {"_id": bot["_id"]},
                    {"$set": {"takeProfits": updated_tps, "currentTPLevel": bot["currentTPLevel"]}}
                )
        
        return min_dist

    async def _get_current_price(self, bot: Dict[str, Any]) -> float:
        """Obtiene el precio actual real usando CEXService."""
        user = await db.users.find_one({"_id": bot["userId"]})
        user_id = user["openId"] if user else "default_user"
        return await self.cex_service.get_current_price(bot["symbol"], user_id)

    async def _close_bot(self, bot: Dict[str, Any], exit_price: float, status: str, reason: str):
        pnl = ((exit_price - bot["entryPrice"]) / bot["entryPrice"]) * 100
        
        # Update Virtual Balance if Demo
        if bot.get("isDemo", True) or bot.get("mode") == "simulated":
            try:
                user_id_obj = bot.get("userId")
                user = await db.users.find_one({"_id": user_id_obj})
                if user:
                    amount = bot.get("amount", 0)
                    revenue = amount * (1 + (pnl/100))
                    
                    market_type = bot.get("marketType", "CEX")
                    asset = "USDT" # Default for now, ideally strictly typed in bot doc
                    
                    await update_virtual_balance(user["openId"], market_type, asset, revenue, is_relative=True)
                    logger.info(f"💰 Balance updated for {user['openId']}: +{revenue:.2f} (PnL: {pnl:.2f}%)")
            except Exception as e:
                logger.error(f"Error updating balance on close_bot: {e}")

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
