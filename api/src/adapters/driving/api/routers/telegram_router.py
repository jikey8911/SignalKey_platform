"""
Endpoints de autenticación y gestión de Telegram
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query
from pydantic import BaseModel
from typing import Optional, Any, List, Dict
import logging
from datetime import datetime
from bson import ObjectId

from api.src.infrastructure.telegram.telegram_bot_manager import bot_manager
from api.src.adapters.driven.persistence.mongodb import db
from api.src.infrastructure.security.auth_deps import get_current_user


def _oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ObjectId")


def _serialize_mongo(doc: Any) -> Any:
    if isinstance(doc, list):
        return [_serialize_mongo(x) for x in doc]
    if isinstance(doc, dict):
        out = {}
        for k, v in doc.items():
            if k == "_id":
                out["id"] = str(v)
            elif isinstance(v, ObjectId):
                out[k] = str(v)
            elif isinstance(v, datetime):
                out[k] = v.isoformat() + "Z"
            else:
                out[k] = _serialize_mongo(v)
        return out
    return doc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])


class TelegramAuthStartRequest(BaseModel):
    """Request para iniciar autenticación de Telegram"""
    phone_number: str
    api_id: str
    api_hash: str
    force_sms: Optional[bool] = False


class TelegramAuthVerifyRequest(BaseModel):
    """Request para verificar código de Telegram"""
    code: str


class TelegramStatusResponse(BaseModel):
    """Response del estado de conexión de Telegram"""
    connected: bool
    phone_number: Optional[str] = None
    last_connected: Optional[str] = None


@router.post("/auth/start")
async def start_telegram_auth(request: TelegramAuthStartRequest, current_user: dict = Depends(get_current_user)):
    """
    Inicia el proceso de autenticación de Telegram
    
    1. Crea un bot temporal
    2. Solicita código de verificación
    3. Telegram envía código al teléfono del usuario
    
    Args:
        request: Datos de autenticación (phone, api_id, api_hash)
        current_user: Usuario autenticado (JWT)
    
    Returns:
        {"status": "code_sent", "message": "..."}
    """
    user_id = current_user["openId"]
    try:
        logger.info(f"Starting Telegram auth for user {user_id}")
        logger.info(f"Received Telegram auth request for user_id: {user_id}")
        logger.info(f"Request data: phone={request.phone_number}, api_id={request.api_id}")
        
        # Importar aquí para evitar circular imports
        from api.src.infrastructure.telegram.telegram_bot import TelegramUserBot
        
        # Crear bot temporal para autenticación (usar sesión en memoria para evitar conflictos)
        temp_bot = TelegramUserBot(
            user_id=user_id,
            api_id=request.api_id,
            api_hash=request.api_hash,
            phone_number=request.phone_number,
            use_memory_session=True
        )
        
        # Solicitar código
        logger.info(f"--- Telegram Auth Step 2: Requesting code from Telegram API (force_sms={request.force_sms}) ---")
        success = await temp_bot.send_code_request(force_sms=request.force_sms)
        
        if not success:
            logger.error("Step 2 FAILED: Telegram API did not send the code. Check backend logs for errors.")
            raise HTTPException(status_code=400, detail="Telegram no pudo enviar el código. Revisa tus credenciales (API ID/Hash) y el formato del teléfono (+57...)")
        
        # Guardar bot temporal en el manager para usarlo en verify
        bot_manager.bots[f"temp_{user_id}"] = temp_bot
        logger.info(f"Step 3: Temp bot stored for user {user_id}. Waiting for verification code...")
        
        # Actualizar config con datos parciales para persistencia
        user = await db.users.find_one({"openId": user_id})
        if user:
            logger.info(f"Step 4: Updating app_config for user {user['_id']} with Telegram credentials")
            await db.app_configs.update_one(
                {"userId": user["_id"]},
                {"$set": {
                    "telegramApiId": request.api_id,
                    "telegramApiHash": request.api_hash,
                    "telegramPhoneNumber": request.phone_number,
                    "telegramIsConnected": False # Aún no verificado
                }},
                upsert=True
            )
        else:
            logger.warning(f"Step 4 WARNING: User with openId {user_id} not found in DB. Config not updated.")
        
        return {
            "status": "code_sent",
            "message": f"Petición enviada a servidores de Telegram. Revisa tu app de Telegram o SMS para el código enviado a {request.phone_number}.",
            "user_id": user_id
        }
        
    except Exception as e:
        logger.error(f"Error starting Telegram auth for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auth/verify")
async def verify_telegram_code(request: TelegramAuthVerifyRequest, current_user: dict = Depends(get_current_user)):
    """
    Verifica el código de autenticación de Telegram
    
    1. Usa el bot temporal creado en /auth/start
    2. Verifica el código
    3. Guarda la sesión en BD
    4. Inicia el bot permanente
    
    Args:
        request: Código de verificación
        current_user: Usuario autenticado
    
    Returns:
        {"status": "connected", "message": "..."}
    """
    user_id = current_user["openId"]
    try:
        logger.info(f"Verifying Telegram code for user {user_id}")
        
        # Obtener bot temporal
        temp_bot = bot_manager.bots.get(f"temp_{user_id}")
        if not temp_bot:
            raise HTTPException(status_code=400, detail="No pending authentication found. Please start auth first.")
        
        # Verificar código
        success, session_string = await temp_bot.sign_in(request.code)
        
        if not success:
            if session_string == "CODE_EXPIRED":
                raise HTTPException(status_code=400, detail="CODE_EXPIRED")
            if session_string == "PASSWORD_NEEDED":
                return {
                    "status": "password_needed",
                    "message": "Two-step verification is enabled. Please provide your 2FA password."
                }
            raise HTTPException(status_code=400, detail="Invalid verification code")
        
        # Guardar sesión en BD
        user = await db.users.find_one({"openId": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        await db.app_configs.update_one(
            {"userId": user["_id"]},
            {"$set": {
                "telegramSessionString": session_string,
                "telegramIsConnected": True,
                "telegramLastConnected": datetime.utcnow()
            }},
            upsert=True
        )
        
        # Limpiar bot temporal
        await temp_bot.stop()
        del bot_manager.bots[f"temp_{user_id}"]
        
        # Obtener config actualizada
        config = await db.app_configs.find_one({"userId": user["_id"]})
        
        # Iniciar bot permanente
        await bot_manager.start_user_bot(
            user_id=user_id,
            api_id=config["telegramApiId"],
            api_hash=config["telegramApiHash"],
            phone_number=config["telegramPhoneNumber"],
            session_string=session_string
        )
        
        logger.info(f"Telegram bot connected successfully for user {user_id}")
        
        return {
            "status": "connected",
            "message": "Telegram connected successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying Telegram code for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disconnect")
async def disconnect_telegram(current_user: dict = Depends(get_current_user)):
    """
    Desconecta el bot de Telegram del usuario
    """
    user_id = current_user["openId"]
    try:
        logger.info(f"Disconnecting Telegram for user {user_id}")
        
        # Detener bot
        await bot_manager.stop_user_bot(user_id)
        
        # Actualizar BD
        user = await db.users.find_one({"openId": user_id})
        if user:
            await db.app_configs.update_one(
                {"userId": user["_id"]},
                {"$set": {
                    "telegramIsConnected": False,
                    "telegramSessionString": ""  # Limpiar sesión
                }}
            )
        
        return {"status": "disconnected"}
        
    except Exception as e:
        logger.error(f"Error disconnecting Telegram for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=TelegramStatusResponse)
async def get_telegram_status(current_user: dict = Depends(get_current_user)):
    """
    Obtiene el estado de conexión de Telegram del usuario
    """
    user_id = current_user["openId"]
    try:
        # Verificar si el bot está activo
        is_connected = bot_manager.is_bot_active(user_id)
        
        # Obtener info de BD
        user = await db.users.find_one({"openId": user_id})
        if not user:
            return TelegramStatusResponse(connected=False)
        
        config = await db.app_configs.find_one({"userId": user["_id"]})
        if not config:
            return TelegramStatusResponse(connected=False)
        
        return TelegramStatusResponse(
            connected=is_connected and config.get("telegramIsConnected", False),
            phone_number=config.get("telegramPhoneNumber"),
            last_connected=str(config.get("telegramLastConnected")) if config.get("telegramLastConnected") else None
        )
        
    except Exception as e:
        logger.error(f"Error getting Telegram status for user {user_id}: {e}")
        return TelegramStatusResponse(connected=False)


@router.get("/dialogs")
async def get_telegram_dialogs(current_user: dict = Depends(get_current_user)):
    """
    Obtiene la lista de chats/canales del usuario
    """
    user_id = current_user["openId"]
    try:
        bot = bot_manager.get_user_bot(user_id)
        if not bot:
            raise HTTPException(status_code=404, detail="Telegram bot not connected")
        
        dialogs = await bot.get_dialogs()
        return {"dialogs": dialogs}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dialogs for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auth/reconnect")
async def reconnect_telegram(current_user: dict = Depends(get_current_user)):
    """
    Intenta reconectar la sesión de Telegram usando la session string guardada en DB.
    """
    user_id = current_user["openId"]
    try:
        logger.info(f"Attempting to reconnect Telegram for user {user_id}")
        
        # Verificar si el usuario existe
        user = await db.users.find_one({"openId": user_id})
        if not user:
             raise HTTPException(status_code=404, detail="User not found")
        
        config = await db.app_configs.find_one({"userId": user["_id"]})
        if not config:
             raise HTTPException(status_code=400, detail="Configuration not found")
             
        # Verificar credenciales necesarias
        api_id = config.get("telegramApiId")
        api_hash = config.get("telegramApiHash")
        phone_number = config.get("telegramPhoneNumber")
        session_string = config.get("telegramSessionString")
        
        if not all([api_id, api_hash, session_string]):
             raise HTTPException(status_code=400, detail="Missing Telegram credentials in config. Please authenticate first.")
             
        # Intentar iniciar el bot
        try:
             await bot_manager.start_user_bot(
                user_id=user_id,
                api_id=api_id,
                api_hash=api_hash,
                phone_number=phone_number,
                session_string=session_string
            )
        except Exception as bot_error:
             # Si falla (ej: sesión inválida), limpiar sesión y notificar
             logger.error(f"Failed to restore session for {user_id}: {bot_error}")
             await db.app_configs.update_one(
                {"userId": user["_id"]},
                {"$set": {"telegramIsConnected": False}}
             )
             raise HTTPException(status_code=401, detail="Saved session is invalid or expired. Please re-authenticate.")

        # Si tiene éxito, asegurar status en DB
        await db.app_configs.update_one(
             {"userId": user["_id"]},
             {"$set": {
                 "telegramIsConnected": True,
                 "telegramLastConnected": datetime.utcnow()
             }}
        )
        
        return {
            "status": "connected", 
            "message": "Session restored successfully",
            "phone_number": phone_number
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reconnecting Telegram: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@router.get("/logs")
async def get_telegram_logs(limit: int = 100, current_user: dict = Depends(get_current_user)):
    """
    Obtiene los logs de Telegram del usuario actual.
    Nota: La persistencia está deshabilitada, este endpoint puede devolver datos vacíos o históricos.
    """
    user_id = current_user["openId"]
    try:
        # Recuperar logs históricos solo del usuario actual
        cursor = db.telegram_logs.find({"userId": user_id}).sort("timestamp", -1).limit(limit)
        logs = await cursor.to_list(length=limit)
        
        # Convertir ObjectId a string
        for log in logs:
            if "_id" in log:
                log["_id"] = str(log["_id"])
                
        return logs
    except Exception as e:
        logger.error(f"Error fetching telegram logs: {e}")
        return []

@router.get("/signals")
async def get_telegram_signals(limit: int = 100, current_user: dict = Depends(get_current_user)):
    """Obtiene el historial de señales de Telegram (aprobadas y rechazadas) para el usuario actual."""
    user_id = current_user["openId"]
    try:
        cursor = db.telegram_signals.find({"userId": user_id}).sort("timestamp", -1).limit(limit)
        signals = await cursor.to_list(length=limit)

        # Serializar ObjectId
        for s in signals:
            if "_id" in s:
                s["_id"] = str(s["_id"])
        return signals
    except Exception as e:
        logger.error(f"Error fetching telegram signals for {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bots")
async def get_telegram_bots(
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """Lista los bots de Telegram (1 doc por señal/bot) para el usuario actual."""
    user_oid = current_user.get("_id")
    if not isinstance(user_oid, ObjectId):
        raise HTTPException(status_code=500, detail="Invalid user _id")

    cursor = db.telegram_bots.find({"userId": user_oid}).sort("createdAt", -1).limit(limit)
    bots = await cursor.to_list(length=limit)

    # Add countdown fields (derived) for UI
    now = datetime.utcnow()
    for b in bots:
        try:
            exp = b.get("expiresAt")
            if isinstance(exp, datetime):
                remaining = int((exp - now).total_seconds() // 60)
                if (exp - now).total_seconds() > 0 and ((exp - now).total_seconds() % 60) > 0:
                    remaining += 1  # ceil
                if remaining < 0:
                    remaining = 0
                b["remainingMinutes"] = remaining
        except Exception:
            pass

    return _serialize_mongo(bots)


@router.get("/trades")
async def get_telegram_trades(
    botId: str = Query(..., description="Telegram bot id (ObjectId)"),
    limit: int = Query(200, ge=1, le=1000),
    current_user: dict = Depends(get_current_user),
):
    """Lista los 'trades' (TP/SL docs) de un bot de Telegram. Se usa para el expand y para gráficas."""
    user_oid = current_user.get("_id")
    if not isinstance(user_oid, ObjectId):
        raise HTTPException(status_code=500, detail="Invalid user _id")

    bot_oid = _oid(botId)

    cursor = (
        db.telegram_trades
        .find({"userId": user_oid, "botId": bot_oid})
        .sort("createdAt", 1)
        .limit(limit)
    )
    trades = await cursor.to_list(length=limit)
    return _serialize_mongo(trades)
