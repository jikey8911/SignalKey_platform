from telethon import TelegramClient, events
from telethon.sessions import StringSession
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
    """Bot de Telegram individual para un usuario específico"""
    
    def __init__(self, user_id: str, api_id: str, api_hash: str, phone_number: str = "", session_string: str = None, use_memory_session: bool = False):
        """
        Inicializa un bot de Telegram para un usuario específico
        
        Args:
            user_id: ID del usuario (openId)
            api_id: Telegram API ID del usuario
            api_hash: Telegram API Hash del usuario
            phone_number: Número de teléfono del usuario
            session_string: Sesión serializada (opcional, para reconexión)
            use_memory_session: Si es True, usa StringSession en lugar de archivo
        """
        self.user_id = user_id
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone_number = phone_number
        self.client = None
        self.api_url = "http://localhost:8000/webhook/signal"
        
        # Usar StringSession si se proporciona o si se solicita sesión en memoria
        if session_string:
            self.session = StringSession(session_string)
        elif use_memory_session:
            self.session = StringSession()
        else:
            # Crear directorio de sesiones si no existe
            os.makedirs('sessions', exist_ok=True)
            self.session = f'sessions/{user_id}_session'
        
        logger.info(f"TelegramUserBot initialized for user {user_id}")

    async def get_dialogs(self):
        """Obtiene la lista de chats/canales del usuario"""
        if not self.client:
            return []
        dialogs = []
        try:
            if not self.client.is_connected():
                 return []
                 
            async for dialog in self.client.iter_dialogs(limit=100):
                dialogs.append({
                    "id": str(dialog.id), 
                    "name": dialog.name,
                    "is_channel": dialog.is_channel,
                    "is_group": dialog.is_group,
                    "is_user": dialog.is_user
                })
        except Exception as e:
            logger.error(f"Error fetching dialogs for user {self.user_id}: {e}")
        return dialogs

    async def start(self):
        """Inicia el bot y comienza a escuchar mensajes"""
        if not self.api_id or not self.api_hash:
            logger.error(f"Missing API credentials for user {self.user_id}")
            return

        try:
            self.client = TelegramClient(self.session, int(self.api_id), self.api_hash)
            
            @self.client.on(events.NewMessage)
            async def handler(event):
                chat_id = str(event.chat_id)
                text = event.message.message
                
                display_text = text if text else "<Mensaje sin texto / Media>"

                # 1. Loguear SIEMPRE en telegram_logs
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
                        "status": "received",
                        "userId": self.user_id  # Asociar log con usuario
                    }
                    await db.telegram_logs.insert_one(log_entry)
                except Exception as e:
                    logger.error(f"Error saving log for user {self.user_id}: {e}")

                if not text:
                    return

                # 2. Filtrar por chats seleccionados SOLO para este usuario
                try:
                    # Obtener configuración del usuario
                    user = await db.users.find_one({"openId": self.user_id})
                    if not user:
                        logger.warning(f"User {self.user_id} not found in database")
                        return
                    
                    config = await db.app_configs.find_one({"userId": user["_id"]})
                    if not config:
                        logger.warning(f"Config not found for user {self.user_id}")
                        return
                    
                    allow_list = config.get("telegramChannels", {}).get("allow", [])
                    
                    # Si la lista está vacía, se procesan TODOS los canales
                    # Si tiene canales, solo se procesan los de la lista
                    should_process = len(allow_list) == 0 or chat_id in allow_list
                    
                    if should_process:
                        logger.info(f"Signal detected in chat {chat_id} for user {self.user_id}")
                        
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
                                url = f"{self.api_url}?user_id={self.user_id}"
                                logger.info(f"Sending signal to {url}")
                                response = await client.post(url, json=payload)
                                if response.status_code != 200:
                                     logger.error(f"Error sending signal ({response.status_code}): {response.text}")
                                else:
                                     logger.info(f"Signal successfully sent for user {self.user_id}")
                            except Exception as e:
                                logger.error(f"Error connecting to API: {e}")

                except Exception as e:
                    logger.error(f"Error processing signal for user {self.user_id}: {e}")

            # Iniciar el cliente
            await self.client.start(phone=self.phone_number if self.phone_number else None)
            
            if not await self.client.is_user_authorized():
                logger.error(f"Bot for user {self.user_id} NOT authorized")
                await self.client.disconnect()
                return
            
            logger.info(f"Telegram bot started for user {self.user_id}")

        except Exception as e:
            logger.error(f"Error starting bot for user {self.user_id}: {e}")
            raise

    async def stop(self):
        """Detiene el bot"""
        if self.client:
            try:
                await self.client.disconnect()
                logger.info(f"Bot stopped for user {self.user_id}")
            except Exception as e:
                logger.error(f"Error stopping bot for user {self.user_id}: {e}")
    
    async def get_session_string(self) -> str:
        """Obtiene la sesión serializada como string"""
        if self.client and isinstance(self.session, StringSession):
            return self.session.save()
        return ""
    
    async def send_code_request(self) -> bool:
        """
        Solicita el código de verificación de Telegram
        Retorna True si se envió correctamente
        """
        try:
            # Limpiar credenciales
            api_id_clean = str(self.api_id).strip()
            api_hash_clean = str(self.api_hash).strip()
            phone_clean = str(self.phone_number).strip()

            # Asegurar que api_id sea un entero
            try:
                api_id_int = int(api_id_clean)
            except ValueError:
                logger.error(f"Invalid API ID (not an integer): {api_id_clean}")
                return False

            print(f"\n>>> [MTPROTO] Iniciando conexión para el usuario {self.user_id}")
            print(f">>> [MTPROTO] Usando API ID: {api_id_int} y Teléfono: {phone_clean}")
            
            if not self.client:
                # Usar la sesión configurada en el constructor (ya sea memoria o archivo)
                self.client = TelegramClient(self.session, api_id_int, api_hash_clean)
            
            if not self.client.is_connected():
                print(">>> [MTPROTO] Conectando a los servidores de Telegram...")
                await self.client.connect()
                print(">>> [MTPROTO] Conexión establecida con éxito")
            
            logger.info(f"Sending code request to Telegram via MTProto for {phone_clean}...")
            print(f">>> [MTPROTO] Solicitando código de verificación a Telegram para {phone_clean}...")
            # Telegram enviará el código a la app o SMS
            result = await self.client.send_code_request(phone_clean)
            
            print(f">>> [MTPROTO] RESPUESTA DE TELEGRAM: {result}")
            logger.info(f"Telegram Response (SentCode): {result}")
            logger.info(f"Code request sent successfully to {self.phone_number} for user {self.user_id}")
            logger.info(f"Phone code hash: {result.phone_code_hash}")
            
            return True
        except Exception as e:
            # Loguear el tipo exacto de excepción
            from telethon.errors import RPCError
            if isinstance(e, RPCError):
                logger.error(f"TELEGRAM API ERROR: {e.code} - {e.message}")
            else:
                logger.error(f"GENERAL ERROR in send_code_request: {str(e)}", exc_info=True)
            return False
    
    async def sign_in(self, code: str) -> tuple[bool, str]:
        """
        Verifica el código de autenticación
        
        Args:
            code: Código de verificación recibido por el usuario
        
        Returns:
            (success: bool, session_string: str)
        """
        try:
            await self.client.sign_in(self.phone_number, code)
            
            if await self.client.is_user_authorized():
                # Obtener la sesión serializada
                session_string = self.client.session.save()
                logger.info(f"User {self.user_id} authenticated successfully")
                return True, session_string
            else:
                logger.error(f"Authentication failed for user {self.user_id}")
                return False, ""
                
        except Exception as e:
            logger.error(f"Error signing in user {self.user_id}: {e}")
            return False, ""


# Mantener compatibilidad con código legacy (bot global)
# Este bot solo se usa si no hay bots de usuario configurados
class LegacyTelegramBot:
    """Bot global legacy - solo para compatibilidad temporal"""
    
    def __init__(self):
        self.api_id = Config.TELEGRAM_API_ID
        self.api_hash = Config.TELEGRAM_API_HASH
        self.session_file = 'userbot_session'
        self.client = None
        self.api_url = "http://localhost:8000/webhook/signal"

        if not self.api_id or not self.api_hash:
            logger.warning("TELEGRAM_API_ID or TELEGRAM_API_HASH not set. Legacy bot will not start.")
    
    async def start(self):
        """Inicia el bot legacy"""
        if not self.api_id or not self.api_hash:
            return

        logger.warning("Starting LEGACY Telegram bot - This is deprecated, users should configure their own bots")
        # Implementación similar al bot original pero marcado como legacy
        # Por ahora, simplemente no hacer nada para forzar a los usuarios a configurar sus bots
        pass
    
    async def stop(self):
        if self.client:
            await self.client.disconnect()


bot_instance = LegacyTelegramBot()

async def start_userbot():
    """Función legacy para compatibilidad"""
    await bot_instance.start()
