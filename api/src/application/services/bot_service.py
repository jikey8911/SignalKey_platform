import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional

import pandas as pd
from api.src.adapters.driven.persistence.mongodb import db, save_trade, update_virtual_balance, get_app_config
from api.src.application.services.cex_service import CEXService
from api.src.application.services.dex_service import DEXService
from api.src.domain.models.schemas import AnalysisResult, ExecutionResult
from api.src.adapters.driven.exchange.stream_service import MarketStreamService
from api.src.application.services.buffer_service import DataBufferService
from api.src.application.services.ml_service import MLService
from api.src.application.services.execution_engine import ExecutionEngine
from api.src.adapters.driven.persistence.mongodb_signal_repository import MongoDBSignalRepository
from api.src.application.services.bot_feature_state_service import BotFeatureStateService

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
        self.feature_state_service = BotFeatureStateService()
        self.stream_service.add_listener(self.handle_market_update)
        # Diccionario para trackear la última vela analizada por stream
        self._last_analyzed_per_bot: Dict[str, Any] = {}

        # Candle stream heuristic:
        # Algunos exchanges mandan velas "closed-only" (1 update por timestamp), otros mandan velas en formación.
        # Trackeamos cuántas veces vimos el mismo timestamp; si solo lo vimos 1 vez, asumimos que esa vela ya venía cerrada.
        self._last_seen_candle_ts: Dict[str, Any] = {}
        self._seen_count_for_ts: Dict[str, int] = {}

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
            
            market_type = str(bot.get("market_type") or bot.get("marketType") or "spot").lower()

            await self.buffer_service.initialize_buffer(ex_id, symbol, tf, limit=100, market_type=market_type)
            await self.stream_service.subscribe_candles(ex_id, symbol, tf, market_type=market_type)
            await self.stream_service.subscribe_ticker(ex_id, symbol, market_type=market_type)

        # 2. Trades activos (Salidas)
        active_trades = await db.trades.find({"status": {"$in": ["active", "open"]}}).to_list(length=1000)
        for trade in active_trades:
            ex_id = (trade.get("exchangeId") or "binance").lower()
            market_type = str(trade.get("marketType") or trade.get("market_type") or "spot").lower()
            await self.stream_service.subscribe_ticker(ex_id, trade["symbol"], market_type=market_type)

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

        # 2) Evaluación intravela usando el MODELO de la estrategia (MLService.predict)
        # La regla es: en tick solo ejecutamos/persistimos cuando hay BUY/SELL (HOLD no escribe trades).
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

                # Construir dataset intravela: usar buffer de velas y ajustar la última vela con el precio live
                tf = bot.get("timeframe") or "15m"
                ex_id = (bot.get("exchangeId") or bot.get("exchange_id") or exchange_id).lower()

                mt = bot.get("marketType") or bot.get("market_type") or "spot"
                df = self.buffer_service.get_latest_data(ex_id, symbol, tf, market_type=str(mt))
                if df is None or df.empty:
                    continue

                df_live = df.copy()
                # Ajustar último candle (en formación)
                try:
                    last_idx = df_live.index[-1]
                    last_close = float(df_live.loc[last_idx, "close"])
                    price_f = float(last_price)
                    df_live.loc[last_idx, "close"] = price_f
                    # high/low intravela
                    df_live.loc[last_idx, "high"] = max(float(df_live.loc[last_idx, "high"]), price_f)
                    df_live.loc[last_idx, "low"] = min(float(df_live.loc[last_idx, "low"]), price_f)
                except Exception:
                    pass

                candles_list = df_live.reset_index().to_dict("records")
                market_type = bot.get("marketType") or bot.get("market_type") or "spot"
                strategy_name = bot.get("strategy_name") or "auto"
                current_pos = bot.get("position") or {"qty": 0, "avg_price": 0}

                pred = self.ml_service.predict(
                    symbol=symbol,
                    timeframe=tf,
                    candles=candles_list,
                    market_type=market_type,
                    strategy_name=strategy_name,
                    current_position=current_pos,
                )

                decision = str(pred.get("decision") or "HOLD").upper()
                if decision not in {"BUY", "SELL"}:
                    continue

                bot_with_exchange = bot.copy()
                bot_with_exchange["exchangeId"] = exchange_id

                await self.engine.process_signal(bot_with_exchange, {
                    "signal": 1 if decision == "BUY" else 2,
                    "price": float(last_price),
                    "confidence": float(pred.get("confidence") or 0.51),
                    "reasoning": pred.get("reasoning") or "tick:model",
                    "is_alert": True,
                    "source": "tick:model",
                    "context": {"prev_price": prev_price},
                })

                self._last_tick_exec_per_bot[bot_id] = now_ts
            except Exception as e:
                logger.debug(f"tick model evaluation skipped for bot {bot.get('_id')}: {e}")

    async def _handle_candle_update(self, data: Dict[str, Any]):
        symbol = data["symbol"]
        timeframe = data["timeframe"]
        ex_id = data.get("exchange", "binance")
        incoming_candle = data["candle"]
        current_ts = incoming_candle["timestamp"]
        market_type = str(data.get("marketType") or data.get("market_type") or "spot").lower()

        # Track por bot individual ya que pueden tener diferentes timeframes o estrategias
        # Usamos b["_id"] en el loop pero aquí necesitamos una base
        # Realmente CCXT Pro manda una vela por (exchange, symbol, timeframe)
        stream_key = f"{ex_id}:{market_type}:{symbol}:{timeframe}"
        last_ts = self._last_analyzed_per_bot.get(stream_key)
        
        is_new_candle = last_ts != current_ts

        # Heurística: contar updates del mismo timestamp para decidir si el stream trae velas en formación.
        # Importante: cuando el timestamp cambia, el conteo que importa para clasificar el stream es el del timestamp ANTERIOR.
        prev_seen = self._last_seen_candle_ts.get(stream_key)
        prev_count = int(self._seen_count_for_ts.get(stream_key, 1))

        if prev_seen == current_ts:
            self._seen_count_for_ts[stream_key] = prev_count + 1
        else:
            # timestamp avanzó: guardamos el conteo del ts anterior para usarlo en el close
            self._prev_closed_ts_count = getattr(self, '_prev_closed_ts_count', {})
            if prev_seen is not None:
                self._prev_closed_ts_count[stream_key] = prev_count
            self._last_seen_candle_ts[stream_key] = current_ts
            self._seen_count_for_ts[stream_key] = 1
        
        # Buscar bots para este exchange específico
        relevant_bots = await db.bot_instances.find({
            "symbol": symbol,
            "timeframe": timeframe,
            "status": "active",
        }).to_list(length=None)

        if not relevant_bots: return
        
        bots_for_exchange = [
            b for b in relevant_bots
            if (b.get("exchangeId") or b.get("exchange_id") or "binance").lower() == ex_id
            and str(b.get("marketType") or b.get("market_type") or "spot").lower() == market_type
        ]
        
        if not bots_for_exchange: return

        # Actualizar buffer
        await self.buffer_service.update_with_candle(ex_id, symbol, timeframe, incoming_candle, market_type=market_type)
        
        # --- EMISION DE VELA POR TOPIC ---
        from api.src.adapters.driven.notifications.socket_service import socket_service
        
        candle_msg = {
            "symbol": symbol,
            "timeframe": timeframe,
            "exchange": ex_id,
            "marketType": market_type,
            "candle": {
                "time": int(current_ts / 1000),
                "open": incoming_candle["open"],
                "high": incoming_candle["high"],
                "low": incoming_candle["low"],
                "close": incoming_candle["close"],
                "volume": incoming_candle["volume"],
            },
        }
        
        market_topic = f"candles:{ex_id.lower()}:{symbol}:{timeframe}"
        await socket_service.emit_to_topic(market_topic, "candle_update", candle_msg)

        # Lógica de IA (cierre de vela): cuando cambia el timestamp, la vela ANTERIOR se considera cerrada.
        if is_new_candle:
            full_history = self.buffer_service.get_latest_data(ex_id, symbol, timeframe, market_type=market_type)
            if full_history is not None and not full_history.empty:
                # Primera vez: no sabemos cuál fue la vela anterior cerrada => solo inicializamos.
                if last_ts is None:
                    self._last_analyzed_per_bot[stream_key] = current_ts
                    return

                # Construir DF de velas cerradas hasta el timestamp anterior (incluyéndolo)
                logger.info(
                    f"🕯️ CANDLE_CLOSE stream={stream_key} closed_ts={int(last_ts)} new_ts={int(current_ts)}"
                )
                try:
                    closed_end = pd.to_datetime(int(last_ts), unit='ms')
                    closed_df = full_history.loc[:closed_end]
                except Exception:
                    closed_df = full_history.iloc[:-1]

                if closed_df is not None and not closed_df.empty:
                    for bot in bots_for_exchange:
                        try:
                            await self.feature_state_service.update_on_candle_close(bot=bot, candles_df=closed_df)
                        except Exception as e:
                            logger.debug(f"feature state update skipped for bot {bot.get('_id')}: {e}")

                        await self._execute_ai_pipeline(bot, closed_df)
                        # Guardar last candle CLOSED (ms)
                        await db.bot_instances.update_one({"_id": bot["_id"]}, {"$set": {"lastCandleTimestamp": int(last_ts)}})

            # Avanzar marcador al nuevo timestamp (vela en formación o siguiente vela)
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
        
        decision = str(prediction.get("decision", "HOLD") or "HOLD").upper()

        # En cierre de vela: siempre persistimos la decisión (BUY/SELL/HOLD) como "signal".
        # Para BUY/SELL, además pasamos al ExecutionEngine (simulado/real según bot.mode).
        try:
            from api.src.domain.entities.signal import Signal, SignalStatus, Decision as SigDecision
            from api.src.adapters.driven.persistence.mongodb_signal_repository import MongoDBSignalRepository

            repo = MongoDBSignalRepository(db)
            sig_dec = SigDecision.HOLD
            if decision == "BUY":
                sig_dec = SigDecision.BUY
            elif decision == "SELL":
                sig_dec = SigDecision.SELL

            new_sig = Signal(
                id=None,
                userId=bot.get('user_id') or bot.get('userId'),
                source=f"AUTO_{(bot.get('strategy_name') or 'AUTO').upper()}_CANDLE_CLOSE",
                rawText=f"CLOSE {bot.get('symbol')} {bot.get('timeframe')} -> {decision}",
                status=SignalStatus.COMPLETED if decision == "HOLD" else SignalStatus.EXECUTING,
                createdAt=datetime.utcnow(),
                symbol=bot.get('symbol'),
                marketType=bot.get('marketType', 'SPOT'),
                decision=sig_dec,
                confidence=float(prediction.get('confidence', 0) or 0),
                botId=str(bot.get('_id')),
            )
            saved = await repo.save(new_sig)

            # Emitir para top "últimas 5 señales" (incluye HOLD)
            try:
                from api.src.adapters.driven.notifications.socket_service import socket_service
                # WS usa user_id=openId (no ObjectId). Resolver openId.
                u_oid = bot.get('user_id') or bot.get('userId')
                u_doc = None
                try:
                    u_doc = await db.users.find_one({"_id": u_oid}) if u_oid else None
                except Exception:
                    u_doc = None
                ws_user = (u_doc.get("openId") if u_doc else None) or str(u_oid)

                await socket_service.emit_to_user(
                    ws_user,
                    "signal_update",
                    saved.to_dict() if hasattr(saved, "to_dict") else {
                        "id": saved.id,
                        "botId": str(bot.get('_id')),
                        "symbol": bot.get('symbol'),
                        "decision": decision,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    },
                )
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"candle-close signal persist skipped for bot {bot.get('_id')}: {e}")

        if decision in ["BUY", "SELL"]:
            logger.info(f"🤖 IA Señal {decision} para {bot['symbol']} en {exchange_id}")

            bot_with_exchange = bot.copy()
            bot_with_exchange["exchangeId"] = exchange_id

            await self.engine.process_signal(bot_with_exchange, {
                "signal": 1 if decision == "BUY" else 2,
                "price": candles_list[-1]['close'],
                "confidence": prediction.get('confidence', 0),
                "reasoning": prediction.get('reasoning', ''),
                "is_alert": False,
                "source": "candle_close:model",
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