from telethon import TelegramClient, events
from api.config import Config
from api.models.schemas import TradingSignal
from api.models.mongodb import db
from datetime import datetime
import httpx
import logging
import asyncio
import os

logger = logging.getLogger(__name__)

class TelegramUserBot:
    def __init__(self):
        self.api_id = Config.TELEGRAM_API_ID
        self.api_hash = Config.TELEGRAM_API_HASH
        self.session_file = 'userbot_session' # Session name
        self.client = None
        self.api_url = "http://localhost:8001/webhook/signal"

        if not self.api_id or not self.api_hash:
            logger.warning("TELEGRAM_API_ID or TELEGRAM_API_HASH not set. UserBot will not start.")

    async def get_dialogs(self):
        if not self.client:
            return []
        dialogs = []
        try:
            if not self.client.is_connected():
                 return []
                 
            async for dialog in self.client.iter_dialogs(limit=100):
                # Incluimos todos los tipos de chats para la consola
                dialogs.append({
                    "id": str(dialog.id), 
                    "name": dialog.name,
                    "is_channel": dialog.is_channel,
                    "is_group": dialog.is_group,
                    "is_user": dialog.is_user
                })
        except Exception as e:
            logger.error(f"Error fetching dialogs: {e}")
        return dialogs

    async def start(self):
        if not self.api_id or not self.api_hash:
            return

        self.client = TelegramClient(self.session_file, int(self.api_id), self.api_hash)

        @self.client.on(events.NewMessage)
        async def handler(event):
            chat_id = str(event.chat_id)
            text = event.message.message
            
            # Capturamos todos los mensajes, incluso si no tienen texto (pueden ser media)
            # Pero para el log y procesamiento, preferimos los que tienen contenido
            display_text = text if text else "<Mensaje sin texto / Media>"

            # 1. Loguear SIEMPRE en telegram_logs (Consola de Telegram)
            try:
                chat_title = "Privado"
                if hasattr(event.chat, 'title'):
                    chat_title = event.chat.title
                elif hasattr(event.chat, 'first_name'):
                    chat_title = f"{event.chat.first_name} {getattr(event.chat, 'last_name', '') or ''}".strip()

                log_entry = {
                    "chatId": chat_id,
                    "chatName": chat_title,
                    "message": display_text,
                    "timestamp": datetime.utcnow(),
                    "status": "received" # Estado inicial para la consola
                }
                await db.telegram_logs.insert_one(log_entry)
            except Exception as e:
                logger.error(f"Error saving log to telegram_logs: {e}")

            if not text:
                return

            # 2. Filtrar por chats seleccionados para procesar como SEÑALES
            try:
                # Obtenemos todas las configuraciones que tengan canales permitidos
                cursor = db.app_configs.find({"telegramChannels.allow": {"$exists": True, "$ne": []}})
                configs = await cursor.to_list(length=100)
                
                # Si no hay configuraciones con allow list, por ahora no procesamos como señal
                # (El usuario pidió filtrar por chats seleccionados)
                
                for config in configs:
                    user_id = str(config.get("userId"))
                    # Buscamos el openId del usuario para la API
                    user = await db.users.find_one({"_id": config.get("userId")})
                    user_open_id = user.get("openId") if user else "default_user"
                    
                    allow_list = config.get("telegramChannels", {}).get("allow", [])
                    
                    if chat_id in allow_list:
                        logger.info(f"Signal detected in allowed chat {chat_id} for user {user_open_id}")
                        
                        # Actualizar el log para indicar que fue procesado como señal
                        await db.telegram_logs.update_one(
                            {"chatId": chat_id, "message": text, "timestamp": {"$gte": log_entry["timestamp"]}},
                            {"$set": {"status": "signal_detected"}}
                        )

                        # Enviar a procesar
                        async with httpx.AsyncClient(timeout=10.0) as client:
                            try:
                                payload = {
                                    "source": f"telegram_{chat_id}",
                                    "raw_text": text
                                }
                                # Aseguramos que la URL sea correcta (localhost:8000/webhook/signal)
                                # y pasamos el user_id como parámetro de consulta
                                url = f"{self.api_url}?user_id={user_open_id}"
                                logger.info(f"Sending signal to {url}")
                                response = await client.post(url, json=payload)
                                if response.status_code != 200:
                                     logger.error(f"Error sending signal to API ({response.status_code}): {response.text}")
                                else:
                                     logger.info(f"Signal successfully sent to API for user {user_open_id}")
                            except Exception as e:
                                logger.error(f"Error connecting to API at {self.api_url}: {e}")

            except Exception as e:
                logger.error(f"Error checking permissions for signals: {e}")

        try:
            await self.client.start()
            logger.info("Telegram UserBot started and listening to ALL messages!")
            if not await self.client.is_user_authorized():
                logger.error("UserBot NOT authorized. Run the setup script manually first.")
                await self.client.disconnect()
                return

        except Exception as e:
            logger.error(f"Error starting UserBot: {e}")

    async def stop(self):
        if self.client:
            await self.client.disconnect()

bot_instance = TelegramUserBot()

async def start_userbot():
    await bot_instance.start()
