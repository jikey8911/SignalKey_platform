"""
Telegram Bot Manager - Gestiona múltiples instancias de bots de Telegram por usuario
"""
from typing import Dict, Optional
import logging
from api.bot.telegram_bot import TelegramUserBot
from api.src.adapters.driven.persistence.mongodb import db

logger = logging.getLogger(__name__)


class TelegramBotManager:
    """Gestiona múltiples instancias de bots de Telegram, uno por usuario"""
    
    def __init__(self):
        self.bots: Dict[str, TelegramUserBot] = {}
        self.signal_processor = None # Referencia global a la función de procesamiento
        logger.info("TelegramBotManager initialized")
    
    async def start_user_bot(
        self, 
        user_id: str, 
        api_id: str, 
        api_hash: str,
        phone_number: str,
        session_string: Optional[str] = None,
        message_handler = None
    ) -> TelegramUserBot:
        """
        Inicia un bot de Telegram para un usuario específico
        
        Args:
            user_id: ID del usuario (openId)
            api_id: Telegram API ID del usuario
            api_hash: Telegram API Hash del usuario
            phone_number: Número de teléfono del usuario
            session_string: Sesión serializada (opcional, para reconexión)
            message_handler: Callback para procesar señales detectadas
        
        Returns:
            TelegramUserBot instance
        """
        # Si ya existe un bot para este usuario, detenerlo primero
        if user_id in self.bots:
            logger.info(f"Stopping existing bot for user {user_id}")
            await self.stop_user_bot(user_id)
        
        logger.info(f"Starting Telegram bot for user {user_id}")
        
        # Crear nueva instancia del bot
        bot = TelegramUserBot(
            user_id=user_id,
            api_id=api_id,
            api_hash=api_hash,
            phone_number=phone_number,
            session_string=session_string
        )
        
        # Iniciar el bot con el manejador de mensajes (usar el global si no se pasa uno)
        handler = message_handler or self.signal_processor
        await bot.start(message_handler=handler)
        
        # Guardar en el diccionario de bots activos
        self.bots[user_id] = bot
        
        logger.info(f"Bot started successfully and listening for user {user_id}")
        return bot
    
    async def stop_user_bot(self, user_id: str) -> bool:
        """
        Detiene el bot de un usuario específico
        
        Args:
            user_id: ID del usuario
        
        Returns:
            True si se detuvo correctamente, False si no existía
        """
        if user_id not in self.bots:
            logger.warning(f"No bot found for user {user_id}")
            return False
        
        logger.info(f"Stopping bot for user {user_id}")
        bot = self.bots[user_id]
        
        try:
            await bot.stop()
            del self.bots[user_id]
            logger.info(f"Bot stopped successfully for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error stopping bot for user {user_id}: {e}")
            return False
    
    def get_user_bot(self, user_id: str) -> Optional[TelegramUserBot]:
        """
        Obtiene el bot de un usuario si existe
        
        Args:
            user_id: ID del usuario
        
        Returns:
            TelegramUserBot instance o None
        """
        return self.bots.get(user_id)
    
    def is_bot_active(self, user_id: str) -> bool:
        """
        Verifica si el bot de un usuario está activo
        
        Args:
            user_id: ID del usuario
        
        Returns:
            True si está activo, False si no
        """
        return user_id in self.bots
    
    async def restart_all_bots(self, message_handler=None):
        """
        Reinicia todos los bots desde la base de datos
        Útil al iniciar la aplicación
        
        Args:
            message_handler: Callback para procesar señales detectadas
        """
        logger.info("Restarting all bots from database...")
        
        try:
            # Buscar todas las configuraciones con Telegram conectado
            configs = await db.app_configs.find({
                "telegramIsConnected": True,
                "telegramApiId": {"$exists": True, "$ne": ""},
                "telegramApiHash": {"$exists": True, "$ne": ""},
                "telegramSessionString": {"$exists": True, "$ne": ""}
            }).to_list(length=100)
            
            logger.info(f"Found {len(configs)} users with Telegram configured")
            
            for config in configs:
                try:
                    # Obtener el usuario
                    user = await db.users.find_one({"_id": config.get("userId")})
                    if not user:
                        logger.warning(f"User not found for config {config.get('_id')}")
                        continue
                    
                    user_id = user.get("openId")
                    
                    # Iniciar el bot con el handler
                    await self.start_user_bot(
                        user_id=user_id,
                        api_id=config.get("telegramApiId"),
                        api_hash=config.get("telegramApiHash"),
                        phone_number=config.get("telegramPhoneNumber", ""),
                        session_string=config.get("telegramSessionString"),
                        message_handler=message_handler
                    )
                    
                    logger.info(f"Restarted bot for user {user_id}")
                    
                except Exception as e:
                    logger.error(f"Error restarting bot for config {config.get('_id')}: {e}")
                    continue
            
            logger.info(f"Successfully restarted {len(self.bots)} bots")
            
        except Exception as e:
            logger.error(f"Error restarting bots from database: {e}")
    
    async def stop_all_bots(self):
        """Detiene todos los bots activos"""
        logger.info("Stopping all bots...")
        
        user_ids = list(self.bots.keys())
        for user_id in user_ids:
            try:
                await self.stop_user_bot(user_id)
            except Exception as e:
                logger.error(f"Error stopping bot for user {user_id}: {e}")
        
        logger.info("All bots stopped")
    
    def get_active_bots_count(self) -> int:
        """Retorna el número de bots activos"""
        return len(self.bots)
    
    def get_active_users(self) -> list:
        """Retorna lista de user_ids con bots activos"""
        return list(self.bots.keys())


# Instancia global del manager
bot_manager = TelegramBotManager()
