from fastapi import APIRouter, Depends
from api.src.adapters.driven.persistence.mongodb import db, get_app_config
from api.src.infrastructure.security.auth_deps import get_current_user
from bson import ObjectId
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Trading & Balances"])


@router.get("/trades")
async def list_user_trades(
    current_user: dict = Depends(get_current_user),
    limit: int = 100
):
    user_id_obj = current_user["_id"]
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
    user_id_obj = current_user["_id"]
    q = {
        "userId": user_id_obj,
        "$or": [
            {"botId": bot_id},
            {"botId": str(bot_id)},
        ]
    }

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
    """Balances via CCXT-only path (no hardcoded exchange API calls)."""
    user_id_str = current_user["openId"]
    user_id_obj = current_user["_id"]

    config = await get_app_config(str(user_id_obj))
    if not config:
        return []

    demo_mode = config.get("demoMode", True)

    if demo_mode:
        virtual_cex = await db.virtual_balances.find_one({"userId": user_id_obj, "marketType": "cex", "asset": "USDT"})
        virtual_dex = await db.virtual_balances.find_one({"userId": user_id_obj, "marketType": "dex", "asset": "SOL"})

        config_virtual = config.get("virtualBalances", {})
        cex_amount = virtual_cex["amount"] if virtual_cex else config_virtual.get("USDT", config_virtual.get("cex", 1000.0))
        dex_amount = virtual_dex["amount"] if virtual_dex else config_virtual.get("SOL", config_virtual.get("dex", 1.0))

        real_cex_usdt = 0.0
        try:
            from api.main import cex_service
            balances = await cex_service.fetch_balance(user_id_str)
            real_cex_usdt = float((balances.get("total") or {}).get("USDT") or 0.0)
        except Exception as e:
            logger.warning(f"Could not fetch real CEX balance in demo mode for {user_id_str}: {e}")

        return [
            {
                "asset": "USDT",
                "amount": cex_amount,
                "realBalance": real_cex_usdt,
                "marketType": "CEX",
                "isDemo": True
            },
            {
                "asset": "SOL",
                "amount": dex_amount,
                "marketType": "DEX",
                "isDemo": True
            }
        ]

    try:
        from api.main import cex_service
        balances = await cex_service.fetch_balance(user_id_str)
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
        if not res:
            res.append({"asset": "USDT", "amount": 0, "realBalance": 0, "marketType": "CEX", "isDemo": False})
        return res
    except Exception as e:
        logger.error(f"Error fetching real balances: {e}")
        return [{"asset": "USDT", "amount": 0, "realBalance": 0, "marketType": "CEX", "isDemo": False}]


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
