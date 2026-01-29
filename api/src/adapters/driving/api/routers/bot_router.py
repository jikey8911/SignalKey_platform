from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from api.src.domain.entities.bot_instance import BotInstance
from api.src.adapters.driven.persistence.mongodb_bot_repository import MongoBotRepository

router = APIRouter(prefix="/bots", tags=["Bot Management sp2"])
repo = MongoBotRepository()

class CreateBotSchema(BaseModel):
    name: str
    symbol: str
    strategy_name: str
    timeframe: str
    mode: str = "simulated"

@router.post("/")
async def create_new_bot(data: CreateBotSchema):
    bot = BotInstance(
        id=None,
        user_id="default_user", 
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
async def list_user_bots():
    bots = await repo.get_all_by_user("default_user")
    return [b.to_dict() for b in bots]

@router.patch("/{bot_id}/status")
async def toggle_bot_status(bot_id: str, status: str):
    if status not in ["active", "paused"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    await repo.update_status(bot_id, status)
    return {"message": f"Bot {status}"}

@router.delete("/{bot_id}")
async def delete_bot(bot_id: str):
    await repo.delete(bot_id)
    return {"message": "Bot deleted"}
