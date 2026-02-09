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
from api.src.application.services.execution_engine import ExecutionEngine
from api.src.adapters.driven.persistence.mongodb_signal_repository import MongoDBSignalRepository

logger = logging.getLogger(__name__)

class SignalBotService:
    def __init__(self, cex_service=None, dex_service=None, ml_service=None, stream_service=None, engine=None):
        self.cex_service = cex_service or CEXService()
        self.dex_service = dex_service or DEXService()
        self.ml_service = ml_service or MLService(exchange_adapter=self.cex_service) 
        self.stream_service = stream_service or MarketStreamService()
        self.engine = engine or ExecutionEngine(db, exchange_adapter=self.cex_service.ccxt_provider)
        
        self.buffer_service = DataBufferService(stream_service=self.stream_service, cex_service=self.cex_service)
        self.stream_service.add_listener(self.handle_market_update)
        self._last_analyzed_key = None

    async def start(self):
        """Inicializa el monitoreo al arrancar."""
        await self.initialize_active_bots_monitoring()
        logger.info("SignalBotService operativo.")

    async def initialize_active_bots_monitoring(self):
        """Suscribe a los flujos necesarios para bots y posiciones activas."""
        # 1. Estrategias activas (Generación de Señales)
        active_instances = await db.bot_instances.find({"status": "active"}).to_list(length=1000)
        for bot in active_instances:
            ex_id = (bot.get("exchangeId") or bot.get("exchange_id") or "okx").lower()
            symbol = bot["symbol"]
            tf = bot.get("timeframe", "15m")
            
            await self.buffer_service.initialize_buffer(ex_id, symbol, tf, limit=100)
            await self.stream_service.subscribe_candles(ex_id, symbol, tf)
            # También ticker para ver el precio live en el dashboard
            await self.stream_service.subscribe_ticker(ex_id, symbol)

        # 2. Trades activos (Gestión de Salida TP/SL)
        active_trades = await db.trades.find({"status": {"$in": ["active", "open"]}}).to_list(length=1000)
        for trade in active_trades:
            ex_id = (trade.get("exchangeId") or "okx").lower()
            await self.stream_service.subscribe_ticker(ex_id, trade["symbol"])

    async def handle_market_update(self, event_type: str, data: Dict[str, Any]):
        if event_type == "ticker_update":
            await self._handle_ticker_update(data)
        elif event_type == "candle_update":
            await self._handle_candle_update(data)

    async def _handle_ticker_update(self, data: Dict[str, Any]):
        symbol = data.get("symbol")
        last_price = data.get("ticker", {}).get("last")
        if not symbol or not last_price: return

        active_trades = await db.trades.find({"symbol": symbol, "status": {"$in": ["active", "open"]}}).to_list(length=None)
        for trade in active_trades:
            # _process_bot_tick gestiona los TP/SL
            await self._process_bot_tick(trade, current_price=last_price)

    async def _handle_candle_update(self, data: Dict[str, Any]):
        """Lógica Anti-Repainting: Solo analiza velas CERRADAS."""
        symbol = data["symbol"]
        timeframe = data["timeframe"]
        ex_id = data.get("exchange", "okx")
        incoming_candle = data["candle"]
        current_ts = incoming_candle["timestamp"]

        # 1. Guard para evitar doble procesamiento en el mismo tick de WS
        analysis_key = f"{ex_id}:{symbol}:{timeframe}:{current_ts}"
        if self._last_analyzed_key == analysis_key: return

        # 2. Buscar instancias de bot que usen este par/TF
        relevant_bots = await db.bot_instances.find({
            "symbol": symbol, "timeframe": timeframe, "status": "active"
        }).to_list(length=None)

        if not relevant_bots: return

        # 3. Actualizar Buffer
        await self.buffer_service.update_with_candle(ex_id, symbol, timeframe, incoming_candle)
        full_history = self.buffer_service.get_latest_data(ex_id, symbol, timeframe)
        
        if full_history is None or full_history.empty: return

        # Solo procesar si detectamos que la vela anterior CERRÓ (el timestamp cambió)
        for bot in relevant_bots:
            last_processed = bot.get("lastCandleTimestamp", 0)
            if current_ts > last_processed:
                logger.info(f"Vela cerrada detectada para {symbol}. Ejecutando IA...")
                
                # Excluimos la vela actual (que es la que se acaba de abrir en el exchange)
                history_for_ai = full_history.iloc[:-1]
                if not history_for_ai.empty:
                    await self._execute_ai_pipeline(bot, history_for_ai)
                    
                # Actualizar bot para no repetir esta vela
                await db.bot_instances.update_one({"_id": bot["_id"]}, {"$set": {"lastCandleTimestamp": current_ts}})
        
        self._last_analyzed_key = analysis_key

    async def _execute_ai_pipeline(self, bot: Dict[str, Any], candles_df: Any):
        """Predice y ejecuta usando el ExecutionEngine (DCA/Flip compatible)."""
        candles_list = candles_df.reset_index().to_dict('records')
        
        # Pasar estado actual de posición a la IA
        current_pos = bot.get('position', {"qty": 0, "avg_price": 0})
        
        prediction = self.ml_service.predict(
            symbol=bot["symbol"],
            timeframe=bot["timeframe"],
            candles=candles_list,
            market_type=bot.get("marketType", "spot"),
            strategy_name=bot.get("strategy_name", "auto"),
            current_position=current_pos
        )
        
        decision = prediction.get("decision", "HOLD")
        if decision in ["BUY", "SELL"]:
            logger.info(f"🤖 IA emite señal {decision} para Bot {bot['_id']}")
            
            # Usar el MOTOR CENTRAL para ejecutar (Maneja DCA, Flip, ROI, etc.)
            await self.engine.process_signal(bot, {
                "signal": 1 if decision == "BUY" else 2,
                "price": candles_list[-1]['close'],
                "confidence": prediction.get('confidence', 0),
                "reasoning": prediction.get('reasoning', ''),
                "is_alert": False
            })

    async def can_activate_bot(self, user_id: str, config: Dict[str, Any]) -> bool:
        """Verifica si el usuario puede activar un nuevo bot basado en su límite."""
        max_bots = config.get("botStrategy", {}).get("maxActiveBots", 5)
        active_bots_count = await db.trades.count_documents({
            "userId": user_id,
            "status": "active"
        })
        return active_bots_count < max_bots

    async def activate_bot(self, analysis: AnalysisResult, user_id: str, config: Dict[str, Any], bot_id: str = None, signal_id: str = None) -> ExecutionResult:
        """Activa un bot para una señal aprobada (Manual o vía API)."""
        symbol = self.cex_service._normalize_symbol(analysis.symbol)
        
        # 1. Buscar instancia de bot activa
        bot_instance = await db.bot_instances.find_one({"_id": db.to_object_id(bot_id)}) if bot_id else None
        if not bot_instance:
            bot_instance = await db.bot_instances.find_one({"userId": user_id, "symbol": symbol, "status": "active"})

        if bot_instance:
            res = await self.engine.process_signal(bot_instance, {
                "signal": 1 if analysis.decision.upper() == "BUY" else 2,
                "price": analysis.parameters.get("entry_price", 0),
                "confidence": analysis.confidence,
                "reasoning": analysis.reasoning,
                "is_alert": False
            })
            if res and res.get("success"):
                return ExecutionResult(success=True, message="Señal procesada por Engine", order_id=res.get("order_id"))
            return ExecutionResult(success=False, message=res.get("reason", "Error en Engine"))

        return ExecutionResult(success=False, message="No se encontró instancia de bot activa")

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
