"""
Endpoints de autenticación y gestión de Telegram
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import logging
from bot.telegram_bot_manager import bot_manager
from src.adapters.driven.persistence.mongodb import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])


class TelegramAuthStartRequest(BaseModel):
    """Request para iniciar autenticación de Telegram"""
    phone_number: str
    api_id: str
    api_hash: str


class TelegramAuthVerifyRequest(BaseModel):
    """Request para verificar código de Telegram"""
    code: str


class TelegramStatusResponse(BaseModel):
    """Response del estado de conexión de Telegram"""
    connected: bool
    phone_number: Optional[str] = None
    last_connected: Optional[str] = None


@router.post("/auth/start")
async def start_telegram_auth(request: TelegramAuthStartRequest, user_id: str):
    """
    Inicia el proceso de autenticación de Telegram
    
    1. Crea un bot temporal
    2. Solicita código de verificación
    3. Telegram envía código al teléfono del usuario
    
    Args:
        request: Datos de autenticación (phone, api_id, api_hash)
        user_id: ID del usuario (openId)
    
    Returns:
        {"status": "code_sent", "message": "..."}
    """
    try:
        logger.info(f"Starting Telegram auth for user {user_id}")
        logger.info(f"Received Telegram auth request for user_id: {user_id}")
        logger.info(f"Request data: phone={request.phone_number}, api_id={request.api_id}")
        
        # Importar aquí para evitar circular imports
        from bot.telegram_bot import TelegramUserBot
        
        # Crear bot temporal para autenticación (usar sesión en memoria para evitar conflictos)
        temp_bot = TelegramUserBot(
            user_id=user_id,
            api_id=request.api_id,
            api_hash=request.api_hash,
            phone_number=request.phone_number,
            use_memory_session=True
        )
        
        # Solicitar código
        logger.info(f"--- Telegram Auth Step 2: Requesting code from Telegram API ---")
        success = await temp_bot.send_code_request()
        
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
async def verify_telegram_code(request: TelegramAuthVerifyRequest, user_id: str):
    """
    Verifica el código de autenticación de Telegram
    
    1. Usa el bot temporal creado en /auth/start
    2. Verifica el código
    3. Guarda la sesión en BD
    4. Inicia el bot permanente
    
    Args:
        request: Código de verificación
        user_id: ID del usuario
    
    Returns:
        {"status": "connected", "message": "..."}
    """
    try:
        logger.info(f"Verifying Telegram code for user {user_id}")
        
        # Obtener bot temporal
        temp_bot = bot_manager.bots.get(f"temp_{user_id}")
        if not temp_bot:
            raise HTTPException(status_code=400, detail="No pending authentication found. Please start auth first.")
        
        # Verificar código
        success, session_string = await temp_bot.sign_in(request.code)
        
        if not success:
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
async def disconnect_telegram(user_id: str):
    """
    Desconecta el bot de Telegram del usuario
    
    Args:
        user_id: ID del usuario
    
    Returns:
        {"status": "disconnected"}
    """
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


@router.get("/status/{user_id}", response_model=TelegramStatusResponse)
async def get_telegram_status(user_id: str):
    """
    Obtiene el estado de conexión de Telegram del usuario
    
    Args:
        user_id: ID del usuario
    
    Returns:
        TelegramStatusResponse
    """
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


@router.get("/dialogs/{user_id}")
async def get_telegram_dialogs(user_id: str):
    """
    Obtiene la lista de chats/canales del usuario
    
    Args:
        user_id: ID del usuario
    
    Returns:
        Lista de chats/canales
    """
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


# Importar datetime aquí para evitar circular imports
from datetime import datetime
