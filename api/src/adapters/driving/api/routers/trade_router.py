from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from api.src.adapters.driven.persistence.mongodb import db, get_app_config
from api.src.infrastructure.security.auth_deps import get_current_user
from bson import ObjectId
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
print("DEBUG: trade_router.py loaded and router initialized")

router = APIRouter(tags=["Trading & Balances"])

@router.get("/trades")
async def list_user_trades(
    current_user: dict = Depends(get_current_user),
    limit: int = 100
):
    """
    Lista los trades para el usuario actual.
    """
    user_id = current_user["openId"]
    
    # Búsqueda flexible (sin slash final o con slash manejado por FastAPI)
    cursor = db.trades.find({"userId": user_id}).sort("createdAt", -1).limit(limit)
    trades = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        trades.append(doc)
    
    return _serialize_mongo(trades)

@router.get("/balances/{user_id}")
async def get_user_balances(user_id: str, current_user: dict = Depends(get_current_user)):
    """
    Obtiene balances virtuales o reales dependiendo del modo demo.
    """
    if current_user["openId"] != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    config = await get_app_config(user_id)
    if not config:
        return []

    demo_mode = config.get("demoMode", True)
    
    if demo_mode:
        # Balance Virtual
        virtual = config.get("virtualBalances", {})
        res = []
        # CEX Balance (USDT)
        res.append({
            "asset": "USDT",
            "amount": virtual.get("USDT", virtual.get("cex", 1000.0)),
            "marketType": "CEX",
            "isDemo": True
        })
        # DEX Balance (SOL)
        res.append({
            "asset": "SOL",
            "amount": virtual.get("SOL", virtual.get("dex", 1.0)),
            "marketType": "DEX",
            "isDemo": True
        })
        return res
    else:
        # Balance Real (Vía CCXT)
        try:
            from api.main import cex_service
            balances = await cex_service.fetch_balance(user_id)
            res = []
            if balances and "total" in balances:
                for asset, total in balances["total"].items():
                    if total > 0:
                        res.append({
                            "asset": asset,
                            "amount": total,
                            "realBalance": total,
                            "marketType": "CEX",
                            "isDemo": False
                        })
            # Si el array está vacío, meter un placeholder para que el UI no se rompa
            if not res:
                res.append({"asset": "USDT", "amount": 0, "marketType": "CEX", "isDemo": False})
            return res
        except Exception as e:
            logger.error(f"Error fetching real balances: {e}")
            return [{"asset": "USDT", "amount": 0, "marketType": "CEX", "isDemo": False}]

def _serialize_mongo(obj):
    if isinstance(obj, list):
        return [_serialize_mongo(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _serialize_mongo(v) for k, v in obj.items()}
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj
