from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from crypto_bot_api.models.schemas import TradingSignal
from crypto_bot_api.models.mongodb import db
import httpx
import logging
import asyncio

logger = logging.getLogger(__name__)

class TelegramSignalBotManager:
    def __init__(self):
        self.active_bots = {} # token -> application
        self.api_url = "http://localhost:8000/webhook/signal"

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return

        signal_text = update.message.text
        chat_id = str(update.effective_chat.id)
        
        # Verificar si este chat_id está autorizado para este bot en la DB
        # (Opcional: podrías filtrar por telegramChatId guardado en app_configs)
        
        logger.info(f"Nueva señal recibida de Telegram (Chat: {chat_id}): {signal_text[:50]}...")

        async with httpx.AsyncClient() as client:
            try:
                payload = {
                    "source": f"telegram_{chat_id}",
                    "raw_text": signal_text
                }
                response = await client.post(self.api_url, json=payload)
                if response.status_code == 200:
                    logger.info("Señal enviada correctamente a la API")
                else:
                    logger.error(f"Error enviando señal a la API: {response.text}")
            except Exception as e:
                logger.error(f"Error de conexión con la API: {e}")

    async def start_bot(self, token: str):
        if token in self.active_bots:
            return

        try:
            application = ApplicationBuilder().token(token).build()
            message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_message)
            application.add_handler(message_handler)
            
            # Iniciar en modo no bloqueante
            await application.initialize()
            await application.start()
            await application.updater.start_polling()
            
            self.active_bots[token] = application
            logger.info(f"Bot con token {token[:10]}... iniciado")
        except Exception as e:
            logger.error(f"Error iniciando bot {token[:10]}...: {e}")

    async def sync_with_db(self):
        """Sincroniza los bots activos con los tokens en la base de datos"""
        while True:
            try:
                # Obtener todos los tokens únicos de la colección app_configs
                cursor = db.app_configs.find({"telegramBotToken": {"$ne": None}})
                configs = await cursor.to_list(length=100)
                tokens = {c["telegramBotToken"] for c in configs if c.get("telegramBotToken")}
                
                # Iniciar nuevos bots
                for token in tokens:
                    if token not in self.active_bots:
                        await self.start_bot(token)
                
                # (Opcional) Detener bots que ya no están en la DB
                
            except Exception as e:
                logger.error(f"Error sincronizando bots con DB: {e}")
            
            await asyncio.sleep(60) # Sincronizar cada minuto

async def run_manager():
    manager = TelegramSignalBotManager()
    await manager.sync_with_db()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_manager())
