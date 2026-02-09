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
    exchange_id = params.get("exchangeId", "okx").lower()
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

        # Primero intentamos obtener la lista de símbolos usando el CCXT adapter
        try:
             # Usamos el nuevo método get_symbols del adaptador
             # market_type viene en UPPER (SPOT, FUTURES) pero CcxtAdapter espera lower (spot, swap)
             ccxt_market_type = market_type.lower()
             if ccxt_market_type == 'futures':
                 ccxt_market_type = 'swap' # CCXT suele usar 'swap' para perpetuos
             
             active_symbols = await backtest_service.exchange.get_symbols(exchange_id, ccxt_market_type)
             
             total_symbols = len(active_symbols)
             logger.info(f"Found {total_symbols} active symbols for {exchange_id} {ccxt_market_type}")

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
                            bot_id_obj = ObjectId(b_dict["id"]) if isinstance(b_dict.get("id"), str) else b_dict.get("_id")

                            # 1. Buscar posición activa en 'positions'
                            active_position = await db.db["positions"].find_one({
                                "botId": bot_id_obj,
                                "status": "OPEN"
                            })

                            if active_position:
                                b_dict["active_position"] = _serialize_mongo(active_position)
                                b_dict["pnl"] = active_position.get("roi", 0.0)
                                b_dict["entryPrice"] = active_position.get("avgEntryPrice", 0.0)
                                b_dict["currentQty"] = active_position.get("currentQty", 0.0)
                            else:
                                b_dict["active_position"] = None
                                b_dict["pnl"] = 0.0

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
