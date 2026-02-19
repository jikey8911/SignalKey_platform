from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from api.src.domain.entities.bot_instance import BotInstance
from api.src.adapters.driven.persistence.mongodb_bot_repository import MongoBotRepository
from api.src.adapters.driven.persistence.mongodb import db, get_app_config 
from api.src.infrastructure.security.auth_deps import get_current_user
from api.src.application.services.bot_feature_state_service import BotFeatureStateService

router = APIRouter(prefix="/bots", tags=["Bot Management sp2"])
repo = MongoBotRepository()
feature_state_service = BotFeatureStateService()

from api.src.domain.models.schemas import BotInstanceSchema

class CreateBotSchema(BaseModel):
    name: str = "New Bot"
    symbol: str
    strategy_name: str = "auto"
    timeframe: str = "15m"
    market_type: str = "spot"
    mode: str = "simulated"
    amount: Optional[float] = None # Optional initial override, otherwise uses default
    status: str = "active"
    exchange_id: Optional[str] = "okx"

@router.post("/")
async def create_new_bot(data: CreateBotSchema, current_user: dict = Depends(get_current_user)):
    user_id_obj = current_user["_id"]
    
    # 1. Resolver Amount inicial con consistencia financiera
    app_config = await get_app_config(str(user_id_obj))
    limit_amount = 0.0
    
    # Default limits based on user tier/config
    if app_config:
        limits = app_config.get('investmentLimits', {})
        if data.market_type in ['spot', 'cex']:
            limit_amount = limits.get('cexMaxAmount', 100.0)
        else:
            limit_amount = limits.get('dexMaxAmount', 50.0)
    else:
        limit_amount = 100.0 if data.market_type == 'spot' else 50.0

    # Determinar monto final: Si el usuario manda uno, validamos que no exceda el límite global
    # Si no manda, o es <= 0, usamos el límite como default (o una fracción segura)
    # FIX: Validar que el amount no sea 0 o negativo, incluso si viene en 'data'
    final_amount = data.amount if (data.amount is not None and data.amount > 0) else limit_amount
    
    # Validation (Financial Consistency)
    if final_amount > limit_amount:
         raise HTTPException(status_code=400, detail=f"Amount {final_amount} exceeds your limit of {limit_amount} for this market.")
    
    # Safety fallback (Double Check)
    if final_amount <= 0:
         final_amount = 100.0 # Default fallback

    # 2. Resolver modo efectivo: si el usuario está en demoMode, no permitir bots reales.
    effective_mode = data.mode
    try:
        if app_config and app_config.get('demoMode', True):
            effective_mode = 'simulated'
    except Exception:
        pass

    # 3. Crear instancia usando Schema para validación estricta
    try:
        new_bot_data = BotInstanceSchema(
            user_id=user_id_obj, # Pass ObjectId directly
            name=data.name,
            symbol=data.symbol,
            amount=final_amount,
            strategy_name=data.strategy_name,
            timeframe=data.timeframe,
            market_type=data.market_type,
            mode=effective_mode,
            status=data.status,
            exchange_id=data.exchange_id or "okx"
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Validation error: {e}")

    # 3. Guardar en DB (convert pydantic to dict)
    # Repo expects a 'BotInstance' entity or dict usually. 
    # Adapting to what `repo.save` expects. The repo implementation seems to map kwargs.
    # We'll construct the entity cleanly.
    
    bot_entity = BotInstance(
        id=None,
        user_id=new_bot_data.user_id, # Should be ObjectId
        name=new_bot_data.name,
        symbol=new_bot_data.symbol,
        strategy_name=new_bot_data.strategy_name,
        timeframe=new_bot_data.timeframe,
        market_type=new_bot_data.market_type,
        mode=new_bot_data.mode,
        status=new_bot_data.status,
        amount=new_bot_data.amount,
        exchange_id=new_bot_data.exchange_id
    )

    bot_id = await repo.save(bot_entity)

    # 3.5 Sub-wallet (solo simulado): asignar % del balance virtual global al bot
    try:
        policy = (app_config or {}).get('botWalletPolicy') or {}
        if effective_mode == 'simulated' and policy.get('enabled', False):
            pct = float(policy.get('perBotAllocationPct', 0) or 0)
            min_usdt = float(policy.get('minAllocationUSDT', 0) or 0)
            max_usdt = float(policy.get('maxAllocationUSDT', 0) or 0)

            # balance global (USDT) en CEX
            vb = await db['virtual_balances'].find_one({
                'userId': user_id_obj,
                'marketType': {'$in': ['CEX', 'cex']},
                'asset': 'USDT'
            })
            global_usdt = float((vb or {}).get('amount', 0) or 0)

            allocated = (global_usdt * pct / 100.0) if pct > 0 else 0.0
            if min_usdt > 0:
                allocated = max(allocated, min_usdt)
            if max_usdt > 0:
                allocated = min(allocated, max_usdt)

            # No permitir negativo ni exceder balance
            allocated = max(0.0, allocated)
            if allocated > global_usdt:
                allocated = global_usdt

            # Descontar del global y setear wallet en el bot
            if allocated > 0:
                from api.src.adapters.driven.persistence.mongodb import update_virtual_balance
                await update_virtual_balance(user_id_obj, 'CEX', 'USDT', -allocated, is_relative=True)

                await db['bot_instances'].update_one(
                    {'_id': ObjectId(bot_id)},
                    {'$set': {
                        'walletAllocated': allocated,
                        'walletAvailable': allocated,
                        'walletRealizedPnl': 0.0,
                        'walletCurrency': 'USDT',
                    }}
                )
    except Exception:
        pass

    # 4. Inicializar snapshot de features de estrategia para este bot
    feature_init = {"ok": False, "reason": "not_attempted"}
    try:
        feature_init = await feature_state_service.initialize_for_bot(
            bot_id=bot_id,
            user_id=user_id_obj,
            user_open_id=current_user.get("openId"),
            symbol=new_bot_data.symbol,
            timeframe=new_bot_data.timeframe,
            market_type=new_bot_data.market_type,
            exchange_id=(new_bot_data.exchange_id or "okx"),
            strategy_name=new_bot_data.strategy_name,
            candles_limit=200,
        )
    except Exception as e:
        feature_init = {"ok": False, "reason": f"feature_init_error:{e}"}

    # Emitir evento de creación
    await socket_service.emit_to_user(str(user_id_obj), "bot_created", {
        "id": bot_id,
        **new_bot_data.dict(by_alias=True, exclude={'id'})
    })

    return {
        "id": bot_id,
        "status": "created",
        "amount": final_amount,
        "feature_state": feature_init,
    }

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
    user_id_obj = current_user["_id"]
    user_open_id = current_user.get("openId")

    # Compatibilidad: bots históricos guardados con user_id como ObjectId o openId string
    bots_cursor = repo.collection.find({
        "$or": [
            {"user_id": user_id_obj},
            {"user_id": str(user_id_obj)},
            {"user_id": user_open_id},
        ]
    })
    bots = [repo._map_doc(doc) async for doc in bots_cursor]
    result = []
    
    for bot in bots:
        b_dict = bot.to_dict()
        bot_id_obj = ObjectId(b_dict["id"]) if isinstance(b_dict.get("id"), str) else b_dict.get("_id")
        
        # 1. Buscar posición activa en la nueva colección 'positions'
        active_position = await db["positions"].find_one({
            "botId": bot_id_obj,
            "status": "OPEN"
        })
        
        if active_position:
            b_dict["active_position"] = _serialize_mongo(active_position)
            # Para compatibilidad con legacy frontend:
            b_dict["pnl"] = active_position.get("roi", 0.0)
            b_dict["entryPrice"] = active_position.get("avgEntryPrice", 0.0)
            b_dict["currentQty"] = active_position.get("currentQty", 0.0)
        else:
            b_dict["active_position"] = None
            b_dict["pnl"] = 0.0
            
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
        u_id = bot_doc.get("userId") # This should be ObjectId now
        await socket_service.emit_to_user(str(u_id), "bot_update", {
            "id": bot_id,
            "status": status
        })
        
    return {"message": f"Bot {status}"}

class UpdateBotSchema(BaseModel):
    name: Optional[str] = None
    strategy_name: Optional[str] = None
    timeframe: Optional[str] = None
    amount: Optional[float] = None
    status: Optional[str] = None

@router.put("/{bot_id}")
async def update_bot(bot_id: str, data: UpdateBotSchema, current_user: dict = Depends(get_current_user)):
    user_id_obj = current_user["_id"]
    
    # 1. Recuperar bot actual
    existing_bot = await repo.collection.find_one({"_id": ObjectId(bot_id), "userId": user_id_obj}) # Ensure we query by ObjectId

    # Fallback to string openId if not found (during transition/migration just in case)
    if not existing_bot:
         existing_bot = await repo.collection.find_one({"_id": ObjectId(bot_id), "user_id": str(user_id_obj)})

    if not existing_bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # 2. Validar Amount si se está actualizando
    updates = {k: v for k, v in data.dict(exclude_unset=True).items()}
    
    if "amount" in updates:
        new_amount = updates["amount"]
        # Retrieve limits
        app_config = await get_app_config(str(user_id_obj))
        limit_amount = 100.0
        if app_config:
             limits = app_config.get('investmentLimits', {})
             market_type = existing_bot.get('market_type', 'spot')
             if market_type in ['spot', 'cex']:
                 limit_amount = limits.get('cexMaxAmount', 100.0)
             else:
                 limit_amount = limits.get('dexMaxAmount', 50.0)
        
        if new_amount > limit_amount:
            raise HTTPException(status_code=400, detail=f"Amount {new_amount} exceeds limit of {limit_amount}")
        if new_amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")

    # 3. Actualizar
    if updates:
        await repo.collection.update_one({"_id": ObjectId(bot_id)}, {"$set": updates})
        
        # Emitir
        await socket_service.emit_to_user(str(user_id_obj), "bot_updated", {
            "id": bot_id,
            **updates
        })
        
    return {"id": bot_id, "status": "updated", "updates": updates}

from api.src.application.services.execution_engine import ExecutionEngine
from bson import ObjectId
from api.src.adapters.driven.notifications.socket_service import socket_service
from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service

# Nota: Engine requiere el adaptador de DB para funcionar
# Corregido: Pasar 'db' (adaptador de persistencia global) y 'ccxt_service' (puerto de exchange)
engine = ExecutionEngine(db, socket_service, exchange_adapter=ccxt_service)

class SignalWebhook(BaseModel):
    bot_id: str
    signal: int # 1: Long, 2: Short
    price: float

class ManualBotActionSchema(BaseModel):
    action: str = Field(..., description="close|increase|reverse")
    price: Optional[float] = None
    amount: Optional[float] = None

@router.post("/{bot_id}/manual-action")
async def execute_manual_action(
    bot_id: str,
    data: ManualBotActionSchema,
    current_user: dict = Depends(get_current_user)
):
    allowed = {"close", "increase", "reverse"}
    action = (data.action or '').strip().lower()
    if action not in allowed:
        raise HTTPException(status_code=400, detail="Invalid action. Use close|increase|reverse")

    user_id_obj = current_user["_id"]
    bot = await repo.collection.find_one({"_id": ObjectId(bot_id)})
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # ownership guard (compatibilidad con legacy user_id)
    owner_ok = (
        bot.get("user_id") == user_id_obj or
        str(bot.get("user_id")) == str(user_id_obj) or
        str(bot.get("user_id")) == str(current_user.get("openId"))
    )
    if not owner_ok:
        raise HTTPException(status_code=403, detail="Not authorized")

    bot['id'] = str(bot['_id'])

    result = await engine.execute_manual_action(
        bot_instance=bot,
        action=action,
        price=data.price,
        amount=data.amount,
    )

    if not result or not result.get('success'):
        raise HTTPException(status_code=400, detail=result.get('reason', 'manual_action_failed'))

    # Refresh payload mínimo para frontend
    updated_bot = await repo.collection.find_one({"_id": ObjectId(bot_id)})
    await socket_service.emit_to_user(str(user_id_obj), "bot_update", {
        "id": bot_id,
        "side": updated_bot.get("side"),
        "position": updated_bot.get("position", {}),
    })

    return {"status": "ok", "action": action, "execution": result}

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
    user_id_obj = current_user["_id"]
    await repo.delete(bot_id)
    
    # Emitir evento de eliminación
    await socket_service.emit_to_user(str(user_id_obj), "bot_deleted", {"id": bot_id})
    
    return {"message": "Bot deleted"}
