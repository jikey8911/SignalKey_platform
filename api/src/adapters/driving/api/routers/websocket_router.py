from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Dict, Any, Set, Tuple
import logging
import json
import time
import asyncio

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

bot_repo = MongoBotRepository()
signal_repo = MongoDBSignalRepository(db)

# Track per-websocket active price topics so we can diff subscriptions.
_ws_price_topics: Dict[int, Set[str]] = {}

# Throttle ticker emits per topic to <= 1 update / 2 seconds.
_last_price_emit: Dict[str, float] = {}
_THROTTLE_SECONDS = 2.0

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
                # Batch backtest for Semi-Auto tab (server resolves active symbols).
                payload = message.get("data") or {}
                asyncio.create_task(run_batch_backtest_ws(user_id, payload))

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
    
    # Obtener posición activa
    active_position = await db["positions"].find_one({
        "botId": bot_doc["_id"],
        "status": "OPEN"
    })

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
        "positions": [_serialize_mongo(active_position)] if active_position else [],
        "signals": [s.to_dict() for s in signals]
    }
    
    # B) ENVIAR SNAPSHOT (avoid datetime serialization issues)
    await websocket.send_text(json.dumps(snapshot_data, default=str))
    
    # C) GESTIONAR SUSCRIPCIÓN EN EL SOCKET MANAGER
    await socket_service.subscribe_to_topic(websocket, topic=f"bot:{bot_id}")
    
    # D) SUSCRIBIR A VELAS
    market_topic = f"candles:{exchange_id}:{symbol}:{timeframe}"
    logger.info(f"Suscribiendo socket a stream de mercado: {market_topic}")
    await socket_service.subscribe_to_topic(websocket, topic=market_topic)

async def handle_bot_unsubscription(websocket: WebSocket, bot_id: str):
    logger.info(f"Cliente desuscribiéndose del bot {bot_id}")
    await socket_service.unsubscribe_from_topic(websocket, topic=f"bot:{bot_id}")
    # Nota: También deberíamos desuscribir de las velas, pero esto requiere 
    # saber qué velas estaba viendo este bot.
    # Por ahora simplificado.


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
        initial_balance = float(data.get("initialBalance") or data.get("initial_balance") or 10000)
        trade_amount = data.get("tradeAmount") or data.get("trade_amount")
        trade_amount = float(trade_amount) if trade_amount not in (None, "") else None
        top_n = int(data.get("topN") or 10)

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

        for idx, symbol in enumerate(symbols, start=1):
            try:
                percent = int((idx / max(total, 1)) * 100)
                await socket_service.emit_to_user(user_id, "backtest_progress", {
                    "current": idx,
                    "total": total,
                    "percent": percent,
                    "symbol": symbol
                })

                details = await backtest_service.run_backtest(
                    symbol=symbol,
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
                )

                # WS payload shape expected by the web mapper in Backtest.tsx
                await socket_service.emit_to_user(user_id, "backtest_result", {
                    "symbol": symbol,
                    "pnl": float(details.get("profit_pct") or 0),
                    "win_rate": float(details.get("win_rate") or 0),
                    "trades": int(details.get("total_trades") or 0),
                    "strategy": details.get("strategy_name") or details.get("winner", {}).get("strategy"),
                    "details": details,
                    "topN": top_n,
                })

            except Exception as e:
                logger.error(f"Batch backtest symbol error {symbol}: {e}")
                await socket_service.emit_to_user(user_id, "backtest_symbol_error", {
                    "symbol": symbol,
                    "error": str(e)
                })

        await socket_service.emit_to_user(user_id, "backtest_complete", {"total": total})

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
