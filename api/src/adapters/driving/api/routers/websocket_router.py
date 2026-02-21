from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Dict, Any, Set, Tuple
import logging
import json
import time
import asyncio
from bson import ObjectId

# Imports de tus servicios (Ajusta las rutas según tu estructura real)
from api.src.adapters.driven.notifications.socket_service import SocketService
from api.src.domain.ports.output.BotRepository import IBotRepository
from api.src.domain.ports.output.signal_repository import ISignalRepository
# from api.src.domain.ports.output.trade_repository import TradeRepository 

from api.src.infrastructure.di.container import container

logger = logging.getLogger(__name__)

router = APIRouter()

# Instancias globales
from api.src.adapters.driven.notifications.socket_service import socket_service
from api.src.adapters.driven.persistence.mongodb_bot_repository import MongoBotRepository
from api.src.adapters.driven.persistence.mongodb_signal_repository import MongoDBSignalRepository
from api.src.adapters.driven.persistence.mongodb import db
from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service

bot_repo = MongoBotRepository()
signal_repo = MongoDBSignalRepository(db)

# Track per-websocket active price topics so we can diff subscriptions.
_ws_price_topics: Dict[int, Set[str]] = {}

# Track bot subscriptions meta per websocket so we can cleanly unsubscribe candles/price topics.
# _ws_bot_meta[id(websocket)][bot_id] = {exchange_id, symbol, timeframe, market_type}
_ws_bot_meta: Dict[int, Dict[str, Dict[str, Any]]] = {}

# Throttle ticker emits per topic to <= 1 update / 2 seconds.
_last_price_emit: Dict[str, float] = {}
_THROTTLE_SECONDS = 2.0

# Global tracker for active batch tasks per user to allow cancellation
_active_batch_tasks: Dict[str, asyncio.Task] = {}

async def _stream_listener(event_type: str, payload: Dict[str, Any]):
    """Listen to MarketStreamService events and fan-out to subscribed sockets."""
    if event_type != "ticker_update":
        return

    try:
        exchange_id = (payload.get("exchange") or "").lower()
        symbol = payload.get("symbol")
        ticker = payload.get("ticker") or {}
        last = ticker.get("last") if isinstance(ticker, dict) else None
        if last is None:
            return

        market_type = payload.get("marketType") or payload.get("market_type") or "SPOT"
        market_type = str(market_type).upper()
        if market_type == "CEX":
            market_type = "SPOT"
        symbol = str(symbol).strip().replace("#", "")
        topic = f"price:{exchange_id}:{market_type}:{symbol}"

        now = time.time()
        last_ts = _last_price_emit.get(topic, 0.0)
        if (now - last_ts) < _THROTTLE_SECONDS:
            return
        _last_price_emit[topic] = now

        await socket_service.emit_to_topic(topic, "price_update", {
            "exchangeId": exchange_id,
            "marketType": market_type,
            "symbol": symbol,
            "price": float(last),
            "ts": int(now * 1000),
        })
    except Exception as e:
        logger.error(f"Error in stream listener: {e}")

# Attach listener once
try:
    container.stream_service.add_listener(_stream_listener)
except Exception as e:
    logger.error(f"Failed to attach market stream listener: {e}")

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await socket_service.connect(websocket, user_id)

    # On connect: send a snapshot of recent telegram logs (if any)
    try:
        cursor = db.telegram_logs.find({"userId": user_id}).sort("timestamp", -1).limit(100)
        logs = await cursor.to_list(length=100)
        for log in logs:
            if "_id" in log:
                log["_id"] = str(log["_id"])
        await websocket.send_text(json.dumps({"event": "telegram_logs_snapshot", "data": logs}, default=str))
    except Exception as e:
        logger.debug(f"No telegram log snapshot for {user_id}: {e}")

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            action = message.get("action")
            
            if action == "SUBSCRIBE_BOT":
                bot_id = message.get("bot_id")
                if bot_id:
                    await handle_bot_subscription(websocket, bot_id)
            
            elif action == "UNSUBSCRIBE_BOT":
                bot_id = message.get("bot_id")
                if bot_id:
                    await handle_bot_unsubscription(websocket, bot_id)

            elif action == "PRICES_SUBSCRIBE":
                items = message.get("items") or []
                await handle_prices_subscribe(websocket, user_id, items)

            elif action == "PING":
                await websocket.send_json({"type": "PONG"})

            elif action == "run_batch_backtest":
                # [STABLE/BLOCKED] Flow: BACKTEST WS
                # Stop previous if running
                if user_id in _active_batch_tasks:
                    logger.info(f"Cancelando tarea previa de batch para {user_id}")
                    _active_batch_tasks[user_id].cancel()
                
                payload = message.get("data") or {}
                # Create and track task
                task = asyncio.create_task(run_batch_backtest_ws(user_id, payload))
                _active_batch_tasks[user_id] = task
                # Cleanup callback when done (to avoid leak)
                task.add_done_callback(lambda t: _active_batch_tasks.pop(user_id, None))

            elif action == "stop_batch_backtest":
                if user_id in _active_batch_tasks:
                    logger.info(f"🛑 Batch backtest detenido manualmente para user={user_id}")
                    _active_batch_tasks[user_id].cancel()
                    _active_batch_tasks.pop(user_id, None)
                    await socket_service.emit_to_user(user_id, "backtest_error", {"message": "Escaneo detenido por el usuario", "Critical": True})

            elif action == "run_single_backtest":
                # [STABLE/BLOCKED] Flow: BACKTEST WS
                payload = message.get("data") or {}
                asyncio.create_task(run_single_backtest_ws(user_id, payload))

    except WebSocketDisconnect:
        # Unsubscribe prices for this websocket
        await handle_prices_subscribe(websocket, user_id, [])
        socket_service.disconnect(websocket, user_id)
    except Exception as e:
        logger.error(f"Error en websocket: {e}")
        try:
            await websocket.close()
        except:
            pass

async def handle_bot_subscription(websocket: WebSocket, bot_id: str):
    """
    1. Obtiene datos completos del bot.
    2. Envía SNAPSHOT al cliente.
    3. Suscribe al cliente a los topics de actualizaciones.
    """
    logger.info(f"Cliente suscribiéndose al bot {bot_id}")
    
    # A) OBTENER DATOS REALES
    bot_doc = await bot_repo.collection.find_one({"_id": ObjectId(bot_id)})
    if not bot_doc:
        logger.warning(f"Suspensión fallida: Bot {bot_id} no encontrado.")
        return

    # Mapear para el frontend
    bot_id_str = str(bot_doc["_id"])
    symbol = bot_doc.get("symbol", "BTC/USDT")
    timeframe = bot_doc.get("timeframe", "1h")
    exchange_id = (bot_doc.get("exchangeId") or bot_doc.get("exchange_id") or "binance").lower()

    # Obtener señales recientes
    signals = await signal_repo.find_by_bot_id(bot_id)

    # Obtener trades del bot (fuente canónica para marcadores)
    trade_query = {"$or": [{"botId": bot_id_str}, {"botId": bot_doc.get("_id")}]}
    trades_docs = await db["trades"].find(trade_query).sort("createdAt", -1).limit(400).to_list(length=400)

    # Obtener velas históricas: preferir bot_feature_states.windowCandles (features precomputadas)
    # Fallback: CCXT histórico si no existe estado (p.ej. bot recién creado sin bootstrap).
    candles: list = []
    feature_candles: list = []

    try:
        state = await db["bot_feature_states"].find_one({"botId": bot_doc.get("_id")})
        if state and state.get("windowCandles"):
            feature_candles = state.get("windowCandles") or []

            # Map al formato de lightweight-charts: time en segundos
            for c in feature_candles:
                try:
                    ts = c.get("timestamp")
                    # ts viene iso string (UTC) en bot_feature_states
                    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    candles.append({
                        "time": int(dt.timestamp()),
                        "open": float(c.get("open", 0) or 0),
                        "high": float(c.get("high", 0) or 0),
                        "low": float(c.get("low", 0) or 0),
                        "close": float(c.get("close", 0) or 0),
                        "volume": float(c.get("volume", 0) or 0),
                    })
                except Exception:
                    continue

        if not candles:
            market_type = (bot_doc.get("marketType") or bot_doc.get("market_type") or "spot")
            df = await ccxt_service.get_historical_data(
                symbol=symbol,
                timeframe=timeframe,
                limit=120,
                exchange_id=exchange_id,
                market_type=market_type,
            )
            if df is not None and not df.empty:
                candles = [
                    {
                        "time": int(ts.timestamp()),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": float(row["volume"]),
                    }
                    for ts, row in df.iterrows()
                ]

    except Exception as e:
        logger.warning(f"No se pudo cargar histórico para snapshot {exchange_id}:{symbol}:{timeframe}: {e}")

    # Obtener posición activa (colección canónica para dashboard)
    active_position = await db["positions"].find_one({
        "botId": bot_doc["_id"],
        "status": "OPEN"
    })

    # Normalizar forma de posición para Cards del frontend.
    # (Bots.tsx lee: avgEntryPrice/entryPrice, currentQty/amount, side/direction)
    positions_payload = []
    if active_position:
        ap = _serialize_mongo(active_position)
        positions_payload = [{
            **ap,
            "symbol": ap.get("symbol") or symbol,
            "side": ap.get("side") or ap.get("direction") or ap.get("positionSide") or ap.get("posSide") or "LONG",
            "avgEntryPrice": ap.get("avgEntryPrice") or ap.get("entryPrice") or ap.get("entry") or 0,
            "entryPrice": ap.get("avgEntryPrice") or ap.get("entryPrice") or ap.get("entry") or 0,
            "currentQty": ap.get("currentQty") or ap.get("amount") or ap.get("qty") or 0,
            "amount": ap.get("currentQty") or ap.get("amount") or ap.get("qty") or 0,
            # opcional: ROI/PnL si existe
            "roi": ap.get("roi") or ap.get("pnl") or 0,
        }]

    snapshot_data = {
        "type": "bot_snapshot",
        "bot_id": bot_id_str,
        "config": {
            "id": bot_id_str,
            "name": bot_doc.get("name"),
            "symbol": symbol,
            "timeframe": timeframe,
            "exchange_id": exchange_id,
            "status": bot_doc.get("status")
        },
        # Raw doc por si UI lo quiere mostrar/depurar
        "active_position": _serialize_mongo(active_position) if active_position else None,
        # Array normalizado usado por cards
        "positions": positions_payload,
        "signals": [s.to_dict() for s in signals],
        "trades": _serialize_mongo(trades_docs),
        "candles": candles,
        # Extra: candles con features (para overlays/diagnóstico). La UI puede ignorarlo si no lo usa.
        "featureCandles": feature_candles,
    }
    
    # B) ENVIAR SNAPSHOT (avoid datetime serialization issues)
    await websocket.send_text(json.dumps(snapshot_data, default=str))
    
    # C) GESTIONAR SUSCRIPCIÓN EN EL SOCKET MANAGER
    await socket_service.subscribe_to_topic(websocket, topic=f"bot:{bot_id}")

    # D) SUSCRIBIR A VELAS (histórico + live por timeframe del bot)
    bot_market_type = str(bot_doc.get("marketType") or bot_doc.get("market_type") or "spot")

    market_topic = f"candles:{exchange_id}:{symbol}:{timeframe}"
    logger.info(f"Suscribiendo socket a stream de mercado: {market_topic} ({bot_market_type})")
    await socket_service.subscribe_to_topic(websocket, topic=market_topic)
    try:
        # Esto NO crea una suscripción duplicada: MarketStreamService ya normaliza market_type y es idempotente.
        await container.stream_service.subscribe_candles(exchange_id, symbol, timeframe, market_type=bot_market_type)
    except Exception as e:
        logger.warning(f"No se pudo suscribir velas en vivo para {symbol} {timeframe}: {e}")

    # E) SUSCRIBIR A TICKER EN VIVO PARA ESTE BOT
    price_topic = f"price:{exchange_id}:{str(bot_market_type).upper() if bot_market_type else 'SPOT'}:{symbol}"
    await socket_service.subscribe_to_topic(websocket, topic=price_topic)
    try:
        await container.stream_service.subscribe_ticker(exchange_id, symbol, market_type=bot_market_type)
    except Exception as e:
        logger.warning(f"No se pudo suscribir ticker en vivo para {symbol}: {e}")

    # Guardar meta para poder desuscribir limpio al cambiar de bot.
    ws_key = id(websocket)
    if ws_key not in _ws_bot_meta:
        _ws_bot_meta[ws_key] = {}
    _ws_bot_meta[ws_key][bot_id_str] = {
        "exchange_id": exchange_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "market_type": bot_market_type,
        "market_topic": market_topic,
        "price_topic": price_topic,
    }

async def handle_bot_unsubscription(websocket: WebSocket, bot_id: str):
    logger.info(f"Cliente desuscribiéndose del bot {bot_id}")
    await socket_service.unsubscribe_from_topic(websocket, topic=f"bot:{bot_id}")

    # Desuscribir también de candles/price para evitar mezclar streams al cambiar de bot.
    ws_key = id(websocket)
    meta = (_ws_bot_meta.get(ws_key) or {}).pop(bot_id, None)

    if meta:
        try:
            if meta.get("market_topic"):
                await socket_service.unsubscribe_from_topic(websocket, topic=meta["market_topic"])
        except Exception:
            pass
        try:
            if meta.get("price_topic"):
                await socket_service.unsubscribe_from_topic(websocket, topic=meta["price_topic"])
        except Exception:
            pass

    # Cleanup container
    if ws_key in _ws_bot_meta and not _ws_bot_meta[ws_key]:
        _ws_bot_meta.pop(ws_key, None)


async def handle_prices_subscribe(websocket: WebSocket, user_id: str, items: list[dict]):
    """Subscribe this websocket to a set of ticker topics.

    items: [{exchangeId, marketType, symbol}]
    """
    ws_key = id(websocket)
    current = _ws_price_topics.get(ws_key, set())

    wanted: Set[str] = set()

    for it in items or []:
        try:
            exchange_id = (it.get("exchangeId") or it.get("exchange") or "").lower()
            market_type = (it.get("marketType") or it.get("market_type") or "SPOT")
            market_type = str(market_type).upper()
            if market_type == "CEX":
                market_type = "SPOT"
            symbol = it.get("symbol")
            if not exchange_id or not symbol:
                continue

            # sanitize symbol (remove hashtags / spaces)
            symbol = str(symbol).strip().replace("#", "")
            if "/" not in symbol:
                continue

            topic = f"price:{exchange_id}:{market_type}:{symbol}"
            wanted.add(topic)
        except Exception:
            continue

    to_add = wanted - current
    to_remove = current - wanted

    # Add new
    for topic in to_add:
        await socket_service.subscribe_to_topic(websocket, topic=topic)
        try:
            parts = topic.split(":", 3)
            exchange_id = parts[1]
            market_type = parts[2]
            symbol = parts[3]
            await container.stream_service.subscribe_ticker(exchange_id, symbol, market_type=market_type)
        except Exception as e:
            logger.error(f"Failed subscribe_ticker for {topic}: {e}")

    # Remove old
    for topic in to_remove:
        await socket_service.unsubscribe_from_topic(websocket, topic=topic)
        # If no one else is subscribed, cancel the CCXT task
        try:
            subs = socket_service.topic_subscriptions.get(topic)
            if not subs:
                parts = topic.split(":", 3)
                exchange_id = parts[1]
                market_type = parts[2]
                symbol = parts[3]
                await container.stream_service.unsubscribe(f"ticker:{exchange_id}:{market_type}:{symbol}")
        except Exception as e:
            logger.error(f"Failed unsubscribe ticker for {topic}: {e}")

    if wanted:
        _ws_price_topics[ws_key] = wanted
    else:
        _ws_price_topics.pop(ws_key, None)

async def run_single_backtest_ws(user_id: str, data: Dict[str, Any]):
    """Runs a single-symbol backtest in background and returns full details by WS."""
    try:
        symbol = (data.get("symbol") or "").strip()
        exchange_id = (data.get("exchangeId") or data.get("exchange_id") or "okx").strip()
        market_type = (data.get("marketType") or data.get("market_type") or "spot").strip()
        timeframe = (data.get("timeframe") or "1h").strip()
        days = int(data.get("days") or 7)
        strategy = (data.get("strategy") or "auto").strip()
        use_ai = bool(data.get("useAi", True))
        model_id = data.get("modelId")

        requested_initial_balance = float(data.get("initialBalance") or data.get("initial_balance") or 10000)
        requested_trade_amount = data.get("tradeAmount") or data.get("trade_amount")
        requested_trade_amount = float(requested_trade_amount) if requested_trade_amount not in (None, "") else None

        if not symbol:
            await socket_service.emit_to_user(user_id, "single_backtest_error", {"message": "Missing symbol"})
            return

        user_doc = await db.users.find_one({"openId": user_id})
        cfg = await db.app_configs.find_one({"userId": user_doc.get("_id")}) if user_doc else None

        market_norm = (market_type or "spot").lower()
        vb_market = "cex" if market_norm in {"spot", "cex", "futures", "future", "swap"} else "dex"
        vb_asset = "USDT" if vb_market == "cex" else "SOL"

        market_candidates = list({vb_market, vb_market.upper(), vb_market.capitalize()})
        asset_candidates = list({vb_asset, vb_asset.upper(), vb_asset.lower()})

        vb_doc = None
        if user_doc:
            vb_doc = await db.virtual_balances.find_one({
                "userId": user_doc.get("_id"),
                "marketType": {"$in": market_candidates},
                "asset": {"$in": asset_candidates},
            })

        resolved_initial_balance = float(vb_doc.get("amount", requested_initial_balance)) if vb_doc else float(requested_initial_balance)

        if resolved_initial_balance <= 0:
            resolved_initial_balance = 10000.0
        if resolved_initial_balance > 1_000_000:
            resolved_initial_balance = 10000.0

        trade_amount = requested_trade_amount
        if trade_amount is None or trade_amount <= 0:
            limits = (cfg or {}).get("investmentLimits") or {}
            if vb_market == "cex":
                trade_amount = float(limits.get("cexMaxAmount") or 0)
            else:
                trade_amount = float(limits.get("dexMaxAmount") or 0)
            if trade_amount <= 0:
                trade_amount = max(10.0, resolved_initial_balance * 0.2)

        if trade_amount > resolved_initial_balance:
            trade_amount = max(10.0, resolved_initial_balance * 0.2)

        await socket_service.emit_to_user(user_id, "single_backtest_start", {
            "symbol": symbol,
            "exchangeId": exchange_id,
            "marketType": market_type,
        })

        from api.src.application.services.backtest_service import BacktestService
        backtest_service = BacktestService(exchange_adapter=ccxt_service)

        details = await backtest_service.run_backtest(
            symbol=symbol,
            days=days,
            timeframe=timeframe,
            market_type=market_type,
            use_ai=use_ai,
            user_config=None,
            strategy=strategy,
            user_id=user_id,
            exchange_id=exchange_id,
            model_id=model_id,
            initial_balance=resolved_initial_balance,
            trade_amount=trade_amount,
        )

        details["resolved_initial_balance"] = resolved_initial_balance
        details["resolved_trade_amount"] = trade_amount

        await socket_service.emit_to_user(user_id, "single_backtest_result", details)

    except Exception as e:
        logger.error(f"Single backtest error: {e}")
        await socket_service.emit_to_user(user_id, "single_backtest_error", {"message": str(e)})


async def run_batch_backtest_ws(user_id: str, data: Dict[str, Any]):
    """Runs a batch backtest and streams progress/results to the user via WS.

    Expected data:
      { exchangeId, marketType, timeframe, days, initialBalance, tradeAmount, topN }
    """
    try:
        exchange_id = (data.get("exchangeId") or data.get("exchange_id") or "").strip()
        market_type = (data.get("marketType") or data.get("market_type") or "spot").strip()
        timeframe = (data.get("timeframe") or "1h").strip()
        days = int(data.get("days") or 7)
        requested_initial_balance = float(data.get("initialBalance") or data.get("initial_balance") or 10000)
        requested_trade_amount = data.get("tradeAmount") or data.get("trade_amount")
        requested_trade_amount = float(requested_trade_amount) if requested_trade_amount not in (None, "") else None
        top_n = int(data.get("topN") or 10)

        # Resolver balance/inversión de forma CONSISTENTE con /backtest/run
        user_doc = await db.users.find_one({"openId": user_id})
        cfg = await db.app_configs.find_one({"userId": user_doc.get("_id")}) if user_doc else None

        market_norm = (market_type or "spot").lower()
        vb_market = "cex" if market_norm in {"spot", "cex", "futures", "future", "swap"} else "dex"
        vb_asset = "USDT" if vb_market == "cex" else "SOL"

        market_candidates = list({vb_market, vb_market.upper(), vb_market.capitalize()})
        asset_candidates = list({vb_asset, vb_asset.upper(), vb_asset.lower()})

        vb_doc = None
        if user_doc:
            vb_doc = await db.virtual_balances.find_one({
                "userId": user_doc.get("_id"),
                "marketType": {"$in": market_candidates},
                "asset": {"$in": asset_candidates},
            })

        initial_balance = float(vb_doc.get("amount", requested_initial_balance)) if vb_doc else float(requested_initial_balance)

        if initial_balance <= 0:
            logger.warning(f"Batch backtest non-positive balance {initial_balance} for user={user_id}. Using 10000")
            initial_balance = 10000.0
        if initial_balance > 1_000_000:
            logger.warning(f"Batch backtest suspicious balance {initial_balance} for user={user_id}. Clamping to 10000")
            initial_balance = 10000.0

        trade_amount = requested_trade_amount
        if trade_amount is None or trade_amount <= 0:
            limits = (cfg or {}).get("investmentLimits") or {}
            if vb_market == "cex":
                trade_amount = float(limits.get("cexMaxAmount") or 0)
            else:
                trade_amount = float(limits.get("dexMaxAmount") or 0)
            if trade_amount <= 0:
                trade_amount = max(10.0, initial_balance * 0.2)

        if trade_amount > initial_balance:
            trade_amount = max(10.0, initial_balance * 0.2)

        # Muy verboso en ambientes con muchos usuarios/backtests; bajar a DEBUG
        logger.debug(
            f"🧪 BATCH BACKTEST RUN user={user_id} exchange={exchange_id} market={market_type} initial_balance={initial_balance} trade_amount={trade_amount} days={days} timeframe={timeframe}"
        )

        if not exchange_id:
            await socket_service.emit_to_user(user_id, "backtest_error", {"message": "Missing exchangeId"})
            return

        # Resolve ACTIVE symbols only (CcxtAdapter.get_symbols already filters market.active)
        symbols = await ccxt_service.get_symbols(exchange_id, market_type)
        symbols = [s for s in symbols if isinstance(s, str) and "/" in s]

        total = len(symbols)
        await socket_service.emit_to_user(user_id, "backtest_start", {"total": total})

        # Lazy import to avoid circulars at module load
        from api.src.application.services.backtest_service import BacktestService

        backtest_service = BacktestService(exchange_adapter=ccxt_service)

        # OPTIMIZACIÓN: Ejecución concurrente con Semaphore (Batch Paralelo)
        concurrency = 10
        semaphore = asyncio.Semaphore(concurrency)
        completed_count = 0
        
        async def process_symbol(sym):
            nonlocal completed_count
            async with semaphore:
                try:
                    details = await backtest_service.run_backtest(
                        symbol=sym,
                        days=days,
                        timeframe=timeframe,
                        market_type=market_type,
                        use_ai=True,
                        user_config=None,
                        strategy="auto",
                        user_id=user_id,
                        exchange_id=exchange_id,
                        initial_balance=initial_balance,
                        trade_amount=trade_amount,
                        verbose=False
                    )

                    # WS payload shape expected by the web mapper in Backtest.tsx
                    await socket_service.emit_to_user(user_id, "backtest_result", {
                        "symbol": sym,
                        "pnl": float(details.get("profit_pct") or 0),
                        "win_rate": float(details.get("win_rate") or 0),
                        "trades": int(details.get("total_trades") or 0),
                        "strategy": details.get("strategy_name") or details.get("winner", {}).get("strategy"),
                        "resolved_initial_balance": initial_balance,
                        "resolved_trade_amount": trade_amount,
                        "details": details,
                        "topN": top_n,
                    })

                except Exception as e:
                    # SILENCIO: Bajar nivel de log para errores individuales de batch
                    logger.debug(f"Batch backtest symbol error {sym}: {e}")
                    await socket_service.emit_to_user(user_id, "backtest_symbol_error", {
                        "symbol": sym,
                        "error": str(e)
                    })
                finally:
                    completed_count += 1
                    percent = int((completed_count / max(total, 1)) * 100)
                    
                    # THROTTLING: Reducir ruido de WS. Emitir cada 5 items o al completar
                    if completed_count % 5 == 0 or completed_count == total:
                        await socket_service.emit_to_user(user_id, "backtest_progress", {
                            "current": completed_count,
                            "total": total,
                            "percent": percent,
                            "symbol": sym
                        })

        # Lanzar tareas en paralelo
        tasks = [process_symbol(s) for s in symbols]
        await asyncio.gather(*tasks)

        logger.info(f"✅ BATCH COMPLETADO | Total analizados: {total} | Exchange: {exchange_id} | Market: {market_type}")
        await socket_service.emit_to_user(user_id, "backtest_complete", {"total": total})

    except asyncio.CancelledError:
        logger.info(f"🛑 Batch backtest cancelado limpiamente para user={user_id}")
        # Opcional: avisar front si no fue él quien canceló (pero aquí fue él)
        raise

    except Exception as e:
        logger.error(f"Batch backtest critical error: {e}")
        await socket_service.emit_to_user(user_id, "backtest_error", {"message": str(e), "Critical": True})


def _serialize_mongo(obj):
    from bson import ObjectId
    if isinstance(obj, list): return [_serialize_mongo(i) for i in obj]
    if isinstance(obj, dict): return {k: _serialize_mongo(v) for k, v in obj.items()}
    if isinstance(obj, ObjectId): return str(obj)
    return obj

from bson import ObjectId
