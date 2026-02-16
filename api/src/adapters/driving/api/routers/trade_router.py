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
    user_id_obj = current_user["_id"]
    
    # Búsqueda usando ObjectId directamente
    cursor = db.trades.find({"userId": user_id_obj}).sort("createdAt", -1).limit(limit)
    trades = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        trades.append(doc)
    
    return _serialize_mongo(trades)

@router.get("/trades/bot/{bot_id}")
async def list_trades_by_bot(
    bot_id: str,
    current_user: dict = Depends(get_current_user),
    limit: int = 300
):
    """Lista trades de un bot específico del usuario autenticado."""
    user_id_obj = current_user["_id"]
    q = {
        "userId": user_id_obj,
        "$or": [
            {"botId": bot_id},
            {"botId": str(bot_id)},
        ]
    }

    # También intentar ObjectId por compatibilidad
    try:
        q["$or"].append({"botId": ObjectId(bot_id)})
    except Exception:
        pass

    cursor = db.trades.find(q).sort("createdAt", -1).limit(limit)
    trades = []
    async for doc in cursor:
        doc["id"] = str(doc.get("_id"))
        trades.append(doc)

    return _serialize_mongo(trades)

@router.get("/balances")
async def get_user_balances(current_user: dict = Depends(get_current_user)):
    """
    Obtiene balances virtuales o reales dependiendo del modo demo.
    Ahora usa el usuario autenticado, no un parámetro user_id.
    """
    user_id_str = current_user["openId"] # Para config y servicios externos que usan openId
    user_id_obj = current_user["_id"]    # Para consultas internas a DB

    # Config retrieval uses openId or ObjectId inside get_app_config helper
    # Here we pass the string ID for compatibility with the helper if it expects string,
    # but strictly we should move to ObjectId everywhere.
    # checking get_app_config implementation: it handles both string (openId) and string(ObjectId).
    # Ideally we refactor get_app_config to take ObjectId directly but for now let's pass ObjectId as string.
    config = await get_app_config(str(user_id_obj))
    if not config:
        return []

    demo_mode = config.get("demoMode", True)
    
    if demo_mode:
        # Balance Virtual
        # Primero intentar leer de la colección dedicada virtual_balances
        virtual_cex = await db.virtual_balances.find_one({"userId": user_id_obj, "marketType": "cex", "asset": "USDT"})
        virtual_dex = await db.virtual_balances.find_one({"userId": user_id_obj, "marketType": "dex", "asset": "SOL"})
        
        # Fallback a configuración inicial si no existen registros
        config_virtual = config.get("virtualBalances", {})
        
        cex_amount = virtual_cex["amount"] if virtual_cex else config_virtual.get("USDT", config_virtual.get("cex", 1000.0))
        dex_amount = virtual_dex["amount"] if virtual_dex else config_virtual.get("SOL", config_virtual.get("dex", 1.0))

        res = []
        # CEX Balance (USDT)
        res.append({
            "asset": "USDT",
            "amount": cex_amount,
            "marketType": "CEX",
            "isDemo": True
        })
        # DEX Balance (SOL)
        res.append({
            "asset": "SOL",
            "amount": dex_amount,
            "marketType": "DEX",
            "isDemo": True
        })
        return res
    else:
        # Balance Real (Vía CCXT)
        try:
            from api.main import cex_service
            # CEX Service expects user_id as string (openId usually for keys lookup).
            # We decided to use ObjectId. Let's pass ObjectId string.
            balances = await cex_service.fetch_balance(str(user_id_obj))
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
