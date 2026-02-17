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
        # Inyectar el engine correctamente
        self.engine = engine or ExecutionEngine(db, socket_service=None, exchange_adapter=self.cex_service.ccxt_provider)
        
        self.buffer_service = DataBufferService(stream_service=self.stream_service, cex_service=self.cex_service)
        self.stream_service.add_listener(self.handle_market_update)
        # Diccionario para trackear la última vela analizada por par:timeframe
        self._last_analyzed_per_bot: Dict[str, Any] = {}
        # Tick runtime state
        self._prev_price_per_stream: Dict[str, float] = {}
        self._last_tick_exec_per_bot: Dict[str, float] = {}

    async def start(self):
        await self.initialize_active_bots_monitoring()
        logger.info("SignalBotService operativo.")

    async def stop(self):
        await self.stream_service.stop()

    async def initialize_active_bots_monitoring(self):
        # 1. Estrategias (Entradas)
        active_instances = await db.bot_instances.find({"status": "active"}).to_list(length=1000)
        for bot in active_instances:
            ex_id = (bot.get("exchangeId") or bot.get("exchange_id") or "binance").lower()
            symbol = bot["symbol"]
            tf = bot.get("timeframe", "15m")
            
            await self.buffer_service.initialize_buffer(ex_id, symbol, tf, limit=100)
            await self.stream_service.subscribe_candles(ex_id, symbol, tf)
            await self.stream_service.subscribe_ticker(ex_id, symbol)

        # 2. Trades activos (Salidas)
        active_trades = await db.trades.find({"status": {"$in": ["active", "open"]}}).to_list(length=1000)
        for trade in active_trades:
            ex_id = (trade.get("exchangeId") or "binance").lower()
            await self.stream_service.subscribe_ticker(ex_id, trade["symbol"])

    async def handle_market_update(self, event_type: str, data: Dict[str, Any]):
        if event_type == "ticker_update":
            await self._handle_ticker_update(data)
        elif event_type == "candle_update":
            await self._handle_candle_update(data)

    async def _handle_ticker_update(self, data: Dict[str, Any]):
        symbol = data.get("symbol")
        last_price = data.get("ticker", {}).get("last")
        exchange_id = data.get("exchange")

        if not symbol or not last_price:
            return

        # 1) Gestión de trades abiertos (PnL live / monitor)
        active_trades = await db.trades.find({
            "symbol": symbol,
            "status": {"$in": ["active", "open"]}
        }).to_list(length=None)

        for trade in active_trades:
            bot_exchange = (trade.get("exchangeId") or "binance").lower()
            if bot_exchange == exchange_id:
                await self._process_bot_tick(trade, current_price=last_price)

                from api.src.adapters.driven.notifications.socket_service import socket_service

                bot_id = str(trade.get("botId"))
                entry_price = trade.get("entryPrice", 0)
                side = trade.get("side", "BUY")
                pnl = 0
                if entry_price > 0:
                    pnl = ((last_price - entry_price) / entry_price) * 100 if side == "BUY" else ((entry_price - last_price) / entry_price) * 100

                await socket_service.emit_to_topic(f"bot:{bot_id}", "bot_update", {
                    "id": bot_id,
                    "symbol": symbol,
                    "currentPrice": last_price,
                    "pnl": round(pnl, 2),
                    "timestamp": datetime.utcnow().isoformat()
                })

        # 2) Evaluación intravela por estrategia base (on_price_tick)
        stream_key = f"{exchange_id}:{symbol}"
        prev_price = float(self._prev_price_per_stream.get(stream_key) or 0)
        self._prev_price_per_stream[stream_key] = float(last_price)

        active_bots = await db.bot_instances.find({
            "symbol": symbol,
            "status": "active"
        }).to_list(length=None)

        for bot in active_bots:
            try:
                bot_exchange = (bot.get("exchangeId") or bot.get("exchange_id") or "binance").lower()
                if bot_exchange != exchange_id:
                    continue

                bot_id = str(bot.get("_id"))
                now_ts = datetime.utcnow().timestamp()
                min_tick_sec = float((bot.get("config") or {}).get("tickMinIntervalSec", 5))
                if now_ts - float(self._last_tick_exec_per_bot.get(bot_id, 0.0)) < min_tick_sec:
                    continue

                strategy_name = bot.get("strategy_name") or ""
                market_type = str(bot.get("marketType") or bot.get("market_type") or "spot").lower()
                StrategyClass = self.ml_service.trainer.load_strategy_class(strategy_name, market_type)
                if not StrategyClass:
                    continue

                strategy = StrategyClass(bot.get("config") or {})
                pos = bot.get("position") or {}
                tick_signal = strategy.on_price_tick(
                    float(last_price),
                    current_position=pos,
                    context={"prev_price": prev_price}
                )

                if tick_signal == 0:
                    continue

                bot_with_exchange = bot.copy()
                bot_with_exchange["exchangeId"] = exchange_id

                await self.engine.process_signal(bot_with_exchange, {
                    "signal": int(tick_signal),
                    "price": float(last_price),
                    "confidence": 0.51,
                    "reasoning": "tick:on_price_tick",
                    "is_alert": True,
                })

                self._last_tick_exec_per_bot[bot_id] = now_ts
            except Exception as e:
                logger.debug(f"tick evaluation skipped for bot {bot.get('_id')}: {e}")

    async def _handle_candle_update(self, data: Dict[str, Any]):
        symbol = data["symbol"]
        timeframe = data["timeframe"]
        ex_id = data.get("exchange", "binance")
        incoming_candle = data["candle"]
        current_ts = incoming_candle["timestamp"]

        # Track por bot individual ya que pueden tener diferentes timeframes o estrategias
        # Usamos b["_id"] en el loop pero aquí necesitamos una base
        # Realmente CCXT Pro manda una vela por (exchange, symbol, timeframe)
        stream_key = f"{ex_id}:{symbol}:{timeframe}"
        last_ts = self._last_analyzed_per_bot.get(stream_key)
        
        is_new_candle = last_ts != current_ts
        
        # Buscar bots para este exchange específico
        relevant_bots = await db.bot_instances.find({
            "symbol": symbol, 
            "timeframe": timeframe, 
            "status": "active"
        }).to_list(length=None)

        if not relevant_bots: return
        
        bots_for_exchange = [
            b for b in relevant_bots 
            if (b.get("exchangeId") or b.get("exchange_id") or "binance").lower() == ex_id
        ]
        
        if not bots_for_exchange: return

        # Actualizar buffer
        await self.buffer_service.update_with_candle(ex_id, symbol, timeframe, incoming_candle)
        
        # --- EMISION DE VELA POR TOPIC ---
        from api.src.adapters.driven.notifications.socket_service import socket_service
        
        candle_msg = {
            "symbol": symbol,
            "timeframe": timeframe,
            "exchange": ex_id,
            "candle": {
                "time": int(current_ts / 1000),
                "open": incoming_candle["open"],
                "high": incoming_candle["high"],
                "low": incoming_candle["low"],
                "close": incoming_candle["close"],
                "volume": incoming_candle["volume"]
            }
        }
        
        market_topic = f"candles:{ex_id.lower()}:{symbol}:{timeframe}"
        await socket_service.emit_to_topic(market_topic, "candle_update", candle_msg)

        # Lógica de IA (solo en cambio de timestamp: la vela anterior acaba de cerrar)
        if is_new_candle:
            # Si last_ts es None es la primera vez que recibimos data, analizamos.
            # Si no es None, significa que current_ts avanzó, por lo que analizamos la vela que acaba de cerrar.
            full_history = self.buffer_service.get_latest_data(ex_id, symbol, timeframe)
            if full_history is not None and not full_history.empty:
                for bot in bots_for_exchange:
                    # Analizamos el dataframe excluyendo la vela actual (en formación)
                    await self._execute_ai_pipeline(bot, full_history.iloc[:-1])
                    await db.bot_instances.update_one({"_id": bot["_id"]}, {"$set": {"lastCandleTimestamp": current_ts}})
            
            self._last_analyzed_per_bot[stream_key] = current_ts

    async def _execute_ai_pipeline(self, bot: Dict[str, Any], candles_df: Any):
        candles_list = candles_df.reset_index().to_dict('records')
        current_pos = bot.get('position', {"qty": 0, "avg_price": 0})
        # USAR ID DEL BOT
        exchange_id = (bot.get("exchangeId") or bot.get("exchange_id") or "binance").lower()
        
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
            logger.info(f"🤖 IA Señal {decision} para {bot['symbol']} en {exchange_id}")
            
            # Aseguramos que el engine reciba el exchange correcto
            bot_with_exchange = bot.copy()
            bot_with_exchange["exchangeId"] = exchange_id
            
            await self.engine.process_signal(bot_with_exchange, {
                "signal": 1 if decision == "BUY" else 2,
                "price": candles_list[-1]['close'],
                "confidence": prediction.get('confidence', 0),
                "reasoning": prediction.get('reasoning', ''),
                "is_alert": False
            })

    async def _process_bot_tick(self, bot: Dict[str, Any], current_price: float = None) -> float:
        symbol = bot["symbol"]
        if current_price is None:
            # FIX: Pasar exchange_id explícito
            ex_id = bot.get("exchangeId") or bot.get("exchange_id") or "binance"
            current_price = await self._get_current_price(bot, ex_id)
        
        if current_price <= 0: return 100.0

        entry_price = bot.get("entryPrice", 0)
        if entry_price == 0: return 0.0

        side = bot.get("side", "BUY")
        pnl = ((current_price - entry_price) / entry_price) * 100 if side == "BUY" else ((entry_price - current_price) / entry_price) * 100
        
        await db.trades.update_one(
            {"_id": bot["_id"]},
            {"$set": {"currentPrice": current_price, "pnl": pnl, "lastMonitoredAt": datetime.utcnow()}}
        )
        return 0.0

    async def _get_current_price(self, bot: Dict[str, Any], exchange_id: str) -> float:
        """Obtiene precio del exchange específico del bot."""
        user = await db.users.find_one({"_id": bot.get("userId")})
        user_id = user["openId"] if user else "default_user"
        return await self.cex_service.get_current_price(bot["symbol"], user_id, exchange_id=exchange_id)

    async def can_activate_bot(self, user_id, config): return True
    async def activate_bot(self, analysis, user_id, config, bot_id=None, signal_id=None): pass