from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from api.src.domain.entities.bot_instance import BotInstance
from api.src.adapters.driven.persistence.mongodb_bot_repository import MongoBotRepository
from api.src.adapters.driven.persistence.mongodb import db 
from api.src.infrastructure.security.auth_deps import get_current_user

router = APIRouter(prefix="/bots", tags=["Bot Management sp2"])
repo = MongoBotRepository()

class CreateBotSchema(BaseModel):
    name: str
    symbol: str
    strategy_name: str
    timeframe: str
    mode: str = "simulated"

@router.post("/")
async def create_new_bot(data: CreateBotSchema, current_user: dict = Depends(get_current_user)):
    user_id = current_user["openId"]
    bot = BotInstance(
        id=None,
        user_id=user_id, 
        name=data.name,
        symbol=data.symbol,
        strategy_name=data.strategy_name,
        timeframe=data.timeframe,
        mode=data.mode,
        status="active" # Se crea activo para iniciar monitoreo
    )
    bot_id = await repo.save(bot)
    return {"id": bot_id, "status": "created"}

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
        
    return result

@router.patch("/{bot_id}/status")
async def toggle_bot_status(bot_id: str, status: str):
    if status not in ["active", "paused"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    await repo.update_status(bot_id, status)
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
    
    # 2. Procesar a través del motor dual
    result = await engine.process_signal(bot, {"signal": data.signal, "price": data.price})
    
    return {"status": "processed", "execution": result}

@router.delete("/{bot_id}")
async def delete_bot(bot_id: str):
    await repo.delete(bot_id)
    return {"message": "Bot deleted"}
