from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import PhoneCodeExpiredError
from api.config import Config
from api.src.domain.models.schemas import TradingSignal
from api.src.adapters.driven.persistence.mongodb import db
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
        self.message_handler = None # Callback para procesar señales
        
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
                 
            # Eliminar límite para obtener TODOS los diálogos
            async for dialog in self.client.iter_dialogs():
                dialogs.append({
                    "id": str(dialog.id), 
                    "name": dialog.name or "Sin Nombre",
                    "is_channel": dialog.is_channel,
                    "is_group": dialog.is_group,
                    "is_user": dialog.is_user,
                    "unread_count": dialog.unread_count
                })
            logger.info(f"Fetched {len(dialogs)} dialogs for user {self.user_id}")
        except Exception as e:
            logger.error(f"Error fetching dialogs for user {self.user_id}: {e}")
        return dialogs

    async def start(self, message_handler=None):
        """Inicia el bot y comienza a escuchar mensajes"""
        if message_handler:
            self.message_handler = message_handler

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

                # 1. Obtener configuración y loguear/emitir siempre (si es posible)
                try:
                    user = await db.users.find_one({"openId": self.user_id})
                    if not user:
                        return
                    
                    user_id_obj = user["_id"]
                    config = await db.app_configs.find_one({"userId": user_id_obj})
                    
                    chat_title = "Privado"
                    if hasattr(event.chat, 'title'):
                        chat_title = event.chat.title
                    elif hasattr(event.chat, 'first_name'):
                        chat_title = f"{event.chat.first_name} {getattr(event.chat, 'last_name', '') or ''}".strip()

                    log_entry = {
                        "chatId": chat_id,
                        "chatName": chat_title,
                        "message": display_text,
                        "timestamp": datetime.utcnow(), # Guardar como DATETIME nativo
                        "status": "received",
                        "userId": self.user_id
                    }
                    
                    # Guardar y emitir para visualización en tiempo real
                    # await db.telegram_logs.insert_one(log_entry) # Deshabilitado por solicitud del usuario
                    from api.src.adapters.driven.notifications.socket_service import socket_service
                    await socket_service.emit_to_user(self.user_id, "telegram_log", log_entry)

                    # 2. VALIDACIÓN PARA IA: Solo si tiene texto y el procesamiento está habilitado
                    if not text:
                        return

                    if config and not config.get("isAutoEnabled", True):
                        # No logueamos el skip para no saturar si está desactivado el auto
                        return

                    # 3. FILTRADO POR CHATS AUTORIZADOS
                    allow_list = config.get("telegramChannels", {}).get("allow", []) if config else []
                    
                    # REQUISITO: Solo procesar con IA si el chat está en la lista
                    # Si la lista está vacía, NO procesamos ninguno por defecto para evitar 429
                    if chat_id not in allow_list:
                        return

                    # 4. PROCESAMIENTO DE SEÑAL
                    logger.info(f"Signal authorized for AI processing from chat {chat_id} ({chat_title})")
                    
                    # Actualizar status en log
                    # Actualizar status en log
                    # await db.telegram_logs.update_one(
                    #     {"chatId": chat_id, "message": text, "timestamp": {"$gte": log_entry["timestamp"]}},
                    #     {"$set": {"status": "signal_detected"}}
                    # )

                    if self.message_handler:
                        signal_obj = TradingSignal(
                            source=f"telegram_{chat_id}",
                            raw_text=text
                        )
                        if asyncio.iscoroutinefunction(self.message_handler):
                            asyncio.create_task(self.message_handler(signal_obj, user_id=self.user_id))
                        else:
                            self.message_handler(signal_obj, user_id=self.user_id)
                    else:
                        asyncio.create_task(self._send_http_signal(chat_id, text))

                except Exception as e:
                    logger.error(f"Error in telegram handler for {self.user_id}: {e}")

            # Configurar autostart y reconexión automática
            # El cliente de Telethon reconecta por defecto, pero start() asegura que esté activo
            await self.client.start(phone=self.phone_number if self.phone_number else None)
            
            if not await self.client.is_user_authorized():
                logger.error(f"Bot for user {self.user_id} NOT authorized")
                await self.client.disconnect()
                return
            
            logger.info(f"Telegram bot started and LISTENING for user {self.user_id}")

        except Exception as e:
            logger.error(f"Error starting bot for user {self.user_id}: {e}")
            raise
    async def _send_http_signal(self, chat_id: str, text: str):
        """Método de respaldo para enviar señal vía HTTP si no hay callback"""
        api_url = f"{Config.API_BASE_URL}/webhook/signal"
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                payload = {"source": f"telegram_{chat_id}", "raw_text": text}
                url = f"{api_url}?user_id={self.user_id}"
                response = await client.post(url, json=payload)
                if response.status_code != 200:
                    logger.error(f"HTTP Signal Error ({response.status_code}): {response.text}")
            except Exception as e:
                logger.error(f"Error connecting to local API: {e}")

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
    
    async def send_code_request(self, force_sms: bool = False) -> bool:
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

            if not self.client:
                # Usar la sesión configurada en el constructor (ya sea memoria o archivo)
                self.client = TelegramClient(self.session, api_id_int, api_hash_clean)
            
            if not self.client.is_connected():
                await self.client.connect()
            
            logger.info(f"Sending code request to Telegram via MTProto for {phone_clean} (force_sms={force_sms})...")
            # Telegram enviará el código a la app o SMS
            result = await self.client.send_code_request(phone_clean, force_sms=force_sms)
            
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
                
        except PhoneCodeExpiredError:
            logger.warning(f"Phone code expired for user {self.user_id}")
            return False, "CODE_EXPIRED"
        except Exception as e:
            logger.error(f"Error signing in user {self.user_id}: {e}")
            return False, ""


    async def send_trade_alert(self, message: str):
        """
        Tarea 6.2: Enviar alerta de trading a través del bot.
        """
        if not self.client or not self.client.is_connected():
            logger.warning("Telegram client not connected. Cannot send alert.")
            return

        try:
            # Enviar a "Saved Messages" (me)
            await self.client.send_message('me', f"🚀 **SignalKey Alert**\n{message}")
            logger.info(f"Trade alert sent to user {self.user_id}")
        except Exception as e:
            logger.error(f"Error sending trade alert for {self.user_id}: {e}")

# Mantener compatibilidad con código legacy (bot global)
# Este bot solo se usa si no hay bots de usuario configurados
class LegacyTelegramBot:
    """Bot global legacy - solo para compatibilidad temporal"""
    
    def __init__(self):
        self.api_id = Config.TELEGRAM_API_ID
        self.api_hash = Config.TELEGRAM_API_HASH
        # Ruta al archivo .session proporcionado por el usuario
        self.session_file = 'api/src/infrastructure/telegram/userbot_session'
        self.client = None
        self.api_url = f"{Config.API_BASE_URL}/webhook/signal"
        self.message_handler = None

        if not self.api_id or not self.api_hash:
            logger.warning("TELEGRAM_API_ID or TELEGRAM_API_HASH not set. Legacy bot will not start.")
    
    async def start(self, message_handler=None):
        """Inicia el bot legacy"""
        if message_handler:
            self.message_handler = message_handler

        if not self.api_id or not self.api_hash:
            logger.error("Legacy Bot: Missing API credentials (ID/HASH)")
            return

        logger.info(f"Starting LEGACY Telegram bot using session: {self.session_file}")

        try:
            # Asegurar que api_id sea int
            api_id_int = int(self.api_id)

            # Verificar si el archivo existe (Telethon añade .session)
            actual_file = f"{self.session_file}.session"
            if not os.path.exists(actual_file):
                # Intentar en el directorio raíz como respaldo
                backup_file = "userbot_session.session"
                if os.path.exists(backup_file):
                    logger.info(f"Session file not found at {actual_file}, using backup at {backup_file}")
                    self.session_file = "userbot_session"
                else:
                    logger.error(f"Telegram session file NOT FOUND. Expected at: {actual_file}")
                    return

            self.client = TelegramClient(self.session_file, api_id_int, self.api_hash)

            # Conectar sin prompt interactivo
            await self.client.connect()

            if not await self.client.is_user_authorized():
                logger.error("Legacy Bot: NOT AUTHORIZED. The session file is invalid or expired for these credentials.")
                await self.client.disconnect()
                return

            @self.client.on(events.NewMessage)
            async def handler(event):
                try:
                    chat_id = str(event.chat_id)
                    text = event.message.message

                    # Intentar obtener info del remitente para el log de consola
                    sender_name = "Unknown"
                    try:
                        sender = await event.get_sender()
                        sender_name = getattr(sender, 'username', '') or f"{getattr(sender, 'first_name', '')} {getattr(sender, 'last_name', '')}".strip()
                    except: pass

                    # REQUISITO: Mostrar todos los mensajes por consola (API logs)
                    print(f"\n[TELEGRAM MESSAGE] From: {sender_name} ({chat_id}) | Content: {text}\n")
                    logger.info(f"Global Bot received message from {chat_id}")

                    # Emitir vía Socket para visibilidad en tiempo real en Dashboard para todos
                    try:
                        from api.src.adapters.driven.notifications.socket_service import socket_service
                        log_entry = {
                            "chatId": chat_id,
                            "chatName": sender_name,
                            "message": text if text else "<Media>",
                            "timestamp": datetime.utcnow().isoformat(),
                            "status": "received",
                            "source": "global_bot"
                        }
                        await socket_service.broadcast("telegram_log", log_entry)
                    except Exception as socket_err:
                        logger.error(f"Error broadcasting global message to sockets: {socket_err}")

                    if text and self.message_handler:
                        signal_obj = TradingSignal(
                            source=f"legacy_telegram_{chat_id}",
                            raw_text=text
                        )
                        # Ejecutar procesamiento GLOBAL para todos los usuarios activos
                        if asyncio.iscoroutinefunction(self.message_handler):
                            asyncio.create_task(self.message_handler(signal_obj, user_id="ALL"))
                        else:
                            self.message_handler(signal_obj, user_id="ALL")
                except Exception as e:
                    logger.error(f"Error in legacy bot handler: {e}")

            logger.info("LEGACY Telegram bot connected and listening")

        except Exception as e:
            logger.error(f"Failed to start Legacy Bot: {e}")
    
    async def stop(self):
        if self.client:
            await self.client.disconnect()


bot_instance = LegacyTelegramBot()

async def start_userbot():
    """Función legacy para compatibilidad"""
    await bot_instance.start()
