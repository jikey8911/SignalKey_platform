from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from api.src.domain.entities.bot_instance import BotInstance
from api.src.adapters.driven.persistence.mongodb_bot_repository import MongoBotRepository
from api.src.adapters.driven.persistence.mongodb import db, get_app_config 
from api.src.infrastructure.security.auth_deps import get_current_user

router = APIRouter(prefix="/bots", tags=["Bot Management sp2"])
repo = MongoBotRepository()

class CreateBotSchema(BaseModel):
    name: str
    symbol: str
    strategy_name: str
    timeframe: str
    market_type: str = "spot"
    mode: str = "simulated"

@router.post("/")
async def create_new_bot(data: CreateBotSchema, current_user: dict = Depends(get_current_user)):
    user_id = current_user["openId"]
    
    # Obtener configuración del usuario para limites de inversión
    app_config = await get_app_config(user_id)
    default_amount = 0.0
    
    if app_config:
        limits = app_config.get('investmentLimits', {})
        if data.market_type == 'spot' or data.market_type == 'cex':
            default_amount = limits.get('cexMaxAmount', 100.0)
        else:
            default_amount = limits.get('dexMaxAmount', 10.0)
    else:
        default_amount = 100.0 # Fallback default
        
    bot = BotInstance(
        id=None,
        user_id=user_id, 
        name=data.name,
        symbol=data.symbol,
        strategy_name=data.strategy_name,
        timeframe=data.timeframe,
        market_type=data.market_type,
        mode=data.mode,
        status="active", # Se crea activo para iniciar monitoreo
        amount=float(default_amount)
    )
    bot_id = await repo.save(bot)
    
    # Emitir evento de creación
    await socket_service.emit_to_user(user_id, "bot_created", {
        "id": bot_id,
        "name": data.name,
        "symbol": data.symbol,
        "strategy_name": data.strategy_name,
        "timeframe": data.timeframe,
        "market_type": data.market_type,
        "mode": data.mode,
        "status": "active",
        "amount": float(default_amount)
    })
    
    return {"id": bot_id, "status": "created"}

def get_signal_repository():
    from api.src.adapters.driven.persistence.mongodb_signal_repository import MongoDBSignalRepository
    return MongoDBSignalRepository(db)

@router.get("/{bot_id}/signals")
async def get_bot_signals(
    bot_id: str,
    current_user: dict = Depends(get_current_user),
    signal_repo = Depends(get_signal_repository)
):
    """
    Recupera el historial de señales para un bot específico.
    """
    signals = await signal_repo.find_by_bot_id(bot_id)
    return [s.to_dict() for s in signals]

@router.get("/")
async def list_user_bots(current_user: dict = Depends(get_current_user)): 
    user_id = current_user["openId"]
    
    bots = await repo.get_all_by_user(user_id)
    result = []
    
    for bot in bots:
        b_dict = bot.to_dict()
        
        # Enrich with active trade data if exists
        # We assume one active trade per symbol/user context usually
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
        
    return _serialize_mongo(result)

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

@router.patch("/{bot_id}/status")
async def toggle_bot_status(bot_id: str, status: str):
    if status not in ["active", "paused"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    await repo.update_status(bot_id, status)
    
    # Emitir actualización de estado
    bot_doc = await repo.collection.find_one({"_id": ObjectId(bot_id)})
    if bot_doc:
        u_id = bot_doc.get("userId")
        await socket_service.emit_to_user(u_id, "bot_update", {
            "id": bot_id,
            "status": status
        })
        
    return {"message": f"Bot {status}"}

from api.src.application.services.execution_engine import ExecutionEngine
from bson import ObjectId
from api.src.adapters.driven.notifications.socket_service import socket_service

# Nota: Engine requiere el adaptador de DB para funcionar
engine = ExecutionEngine(repo, socket_service) 

class SignalWebhook(BaseModel):
    bot_id: str
    signal: int # 1: Long, 2: Short
    price: float

@router.post("/webhook-signal")
async def receive_external_signal(data: SignalWebhook):
    """
    Endpoint sp3 para recibir señales (ej: de Telegram o Modelos) 
    y disparar el motor de ejecución.
    """
    # 1. Buscar la instancia en la DB para conocer su estado (Active/Paused) y modo (Sim/Real)
    # repo.collection accesses the motor collection
    bot = await repo.collection.find_one({"_id": ObjectId(data.bot_id)})
    if not bot:
        raise HTTPException(status_code=404, detail="Instancia de bot no encontrada")

    bot['id'] = str(bot['_id'])

    # 2. Procesar a través del motor dual (La persistencia se maneja en el engine)
    result = await engine.process_signal(bot, {"signal": data.signal, "price": data.price})
    
    return {"status": "processed", "execution": result}

@router.delete("/{bot_id}")
async def delete_bot(bot_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["openId"]
    await repo.delete(bot_id)
    
    # Emitir evento de eliminación
    await socket_service.emit_to_user(user_id, "bot_deleted", {"id": bot_id})
    
    return {"message": "Bot deleted"}
