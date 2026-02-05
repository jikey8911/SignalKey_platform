from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from api.src.adapters.driven.persistence.mongodb import db
from api.src.infrastructure.security.auth_deps import get_current_user
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trades", tags=["Trades Management"])

@router.get("/")
async def list_user_trades(
    current_user: dict = Depends(get_current_user),
    limit: int = 100
):
    """
    Lista los trades para el usuario actual.
    """
    user_id = current_user["openId"]
    
    cursor = db.trades.find({"userId": user_id}).sort("timestamp", -1).limit(limit)
    trades = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        trades.append(doc)
    
    return _serialize_mongo(trades)

def _serialize_mongo(obj):
    if isinstance(obj, list):
        return [_serialize_mongo(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _serialize_mongo(v) for k, v in obj.items()}
    if isinstance(obj, ObjectId):
        return str(obj)
    return obj
