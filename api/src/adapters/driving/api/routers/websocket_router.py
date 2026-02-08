from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from api.src.adapters.driven.notifications.socket_service import socket_service
import logging
import json
import asyncio
from bson import ObjectId
from api.src.adapters.driven.persistence.mongodb_bot_repository import MongoBotRepository
from api.src.adapters.driven.persistence.mongodb import db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

repo = MongoBotRepository()

def _serialize_mongo(obj):
    """
    Recursively convert ObjectId to string to make data JSON serializable.
    """
    if isinstance(obj, list):
        return [_serialize_mongo(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _serialize_mongo(v) for k, v in obj.items()}
    if isinstance(obj, ObjectId):
        return str(obj)
    return obj

async def _run_batch_backtest(user_id: str, params: dict):
    """
    Ejecuta el backtest en lote para todos los símbolos activos.
    """
    exchange_id = params.get("exchangeId", "binance").lower()
    market_type = params.get("marketType", "spot").upper()
    timeframe = params.get("timeframe", "1h")
    days = int(params.get("days", 7))
    initial_balance = float(params.get("initialBalance", 10000))
    trade_amount = float(params.get("tradeAmount", 1000)) if params.get("tradeAmount") else None

    # Importación local para evitar dependencias circulares
    from api.main import backtest_service, cex_service

    try:
        # 1. Obtener símbolos activos del exchange
        # Usamos cex_service para cargar mercados si es necesario
        # TODO: CEXService debería tener un método para listar símbolos activos sin necesidad de una instancia específica si son públicos
        # Por ahora, usamos una instancia genérica o reusamos la existente

        # Primero intentamos obtener la lista de mercados cacheados o cargarlos
        try:
             # Necesitamos un cliente autenticado o público.
             # BacktestService tiene exchange adapter.
             # Asumimos que podemos obtener los símbolos del exchange adapter.
             # Pero ccxt_adapter.load_markets requiere credenciales a veces o es público? load_markets es público generalmente.

             # Vamos a usar el exchange adapter del backtest_service
             markets = await backtest_service.exchange.load_markets(exchange_id)

             # Filtrar por market_type y active
             active_symbols = []
             for symbol, market in markets.items():
                 # Verificar tipo de mercado (spot/swap/future)
                 m_type = market.get('type', 'spot').upper()
                 if market_type == 'SPOT' and m_type == 'SPOT':
                     if market.get('active'): active_symbols.append(symbol)
                 elif market_type == 'FUTURES' and m_type in ['SWAP', 'FUTURE']:
                     if market.get('active'): active_symbols.append(symbol)

             # Limitar para no explotar si hay miles (ej: top 50 por volumen sería ideal, pero por ahora primeros 20 para prueba)
             # O mejor, todos, pero reportando progreso.
             # Para la demo, limitemos a 10 para rapidez.
             # active_symbols = active_symbols[:10]

             total_symbols = len(active_symbols)
             logger.info(f"Found {total_symbols} active symbols for {exchange_id} {market_type}")

             if total_symbols == 0:
                 await socket_service.emit_to_user(user_id, "backtest_error", {"message": f"No active symbols found for {exchange_id} {market_type}"})
                 return

             await socket_service.emit_to_user(user_id, "backtest_start", {"total": total_symbols, "symbols": active_symbols})

             for i, symbol in enumerate(active_symbols):
                 try:
                     # Reportar progreso
                     await socket_service.emit_to_user(user_id, "backtest_progress", {
                         "current": i + 1,
                         "total": total_symbols,
                         "symbol": symbol,
                         "percent": round(((i+1)/total_symbols)*100, 1)
                     })

                     # Ejecutar Backtest para este símbolo
                     # Esto prueba TODAS las estrategias y devuelve la mejor
                     result = await backtest_service.run_backtest(
                         symbol=symbol,
                         days=days,
                         timeframe=timeframe,
                         market_type=market_type,
                         user_id=user_id,
                         exchange_id=exchange_id,
                         initial_balance=initial_balance,
                         trade_amount=trade_amount
                     )

                     # Emitir resultado individual
                     best_strat = result.get("strategy_name", "Unknown")
                     pnl = result.get("profit_pct", 0)
                     win_rate = result.get("win_rate", 0)
                     trades = result.get("total_trades", 0)

                     await socket_service.emit_to_user(user_id, "backtest_result", {
                         "symbol": symbol,
                         "strategy": best_strat,
                         "pnl": pnl,
                         "win_rate": win_rate,
                         "trades": trades,
                         "details": _serialize_mongo(result) # Full details just in case
                     })

                 except Exception as e:
                     logger.error(f"Error backtesting {symbol}: {e}")
                     # Emitir error para este símbolo pero continuar
                     await socket_service.emit_to_user(user_id, "backtest_symbol_error", {
                         "symbol": symbol,
                         "error": str(e)
                     })

             await socket_service.emit_to_user(user_id, "backtest_complete", {"message": "Batch backtest finished"})

        except Exception as e:
             logger.error(f"Error loading markets or running batch: {e}")
             await socket_service.emit_to_user(user_id, "backtest_error", {"message": str(e)})

    except Exception as e:
        logger.error(f"Critical error in batch backtest task: {e}")
        await socket_service.emit_to_user(user_id, "backtest_error", {"message": f"Critical error: {str(e)}"})


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    logger.info(f"New WebSocket connection request from user: {user_id}")
    try:
        await socket_service.connect(websocket, user_id)
        while True:
            # Mantener conexión viva y escuchar mensajes
            data_text = await websocket.receive_text()

            try:
                # Intentar parsear como JSON
                message = json.loads(data_text)

                if isinstance(message, dict):
                    action = message.get("action")

                    if action == "get_bots":
                        # Recuperar bots del usuario
                        bots = await repo.get_all_by_user(user_id)
                        result = []

                        for bot in bots:
                            b_dict = bot.to_dict()

                            # Enrich with active trade data if exists
                            active_trade = await db.trades.find_one({
                                "userId": user_id,
                                "symbol": bot.symbol,
                                "status": "active"
                            })

                            if active_trade:
                                b_dict["active_trade_id"] = str(active_trade["_id"])
                                b_dict["pnl"] = active_trade.get("pnl", 0.0)
                                b_dict["current_price"] = active_trade.get("currentPrice", 0.0)
                                b_dict["status"] = "active" # Force active status if trade is running
                            else:
                                b_dict["active_trade_id"] = None
                                b_dict["pnl"] = 0.0
                                b_dict["current_price"] = 0.0

                            result.append(b_dict)

                        # Enviar respuesta serializada
                        serialized_result = _serialize_mongo(result)
                        await socket_service.emit_to_user(user_id, "all_bots_list", serialized_result)

                    elif action == "run_batch_backtest":
                        # Lanzar backtest masivo en background
                        params = message.get("data", {})
                        logger.info(f"Starting batch backtest for {user_id} with params: {params}")
                        # Usar asyncio.create_task para no bloquear el loop del WS
                        asyncio.create_task(_run_batch_backtest(user_id, params))


            except json.JSONDecodeError:
                # Mantener compatibilidad con mensajes de texto simple como "ping"
                if data_text == "ping":
                    await websocket.send_text("pong")
                
    except WebSocketDisconnect:
        socket_service.disconnect(websocket, user_id)
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        socket_service.disconnect(websocket, user_id)
