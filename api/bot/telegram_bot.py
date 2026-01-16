from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from crypto_bot_api.config import Config
from crypto_bot_api.models.schemas import TradingSignal
import httpx
import logging

logger = logging.getLogger(__name__)

class TelegramSignalBot:
    def __init__(self):
        self.token = Config.TELEGRAM_BOT_TOKEN
        self.api_url = f"http://localhost:{Config.PORT}/webhook/signal"

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return

        signal_text = update.message.text
        logger.info(f"Nueva señal recibida de Telegram: {signal_text[:50]}...")

        # Enviar la señal a la API interna
        async with httpx.AsyncClient() as client:
            try:
                payload = TradingSignal(
                    source=f"telegram_{update.effective_chat.id}",
                    raw_text=signal_text
                )
                response = await client.post(self.api_url, json=payload.dict())
                if response.status_code == 200:
                    logger.info("Señal enviada correctamente a la API")
                else:
                    logger.error(f"Error enviando señal a la API: {response.text}")
            except Exception as e:
                logger.error(f"Error de conexión con la API: {e}")

    def run(self):
        if not self.token:
            logger.error("TELEGRAM_BOT_TOKEN no configurado")
            return

        application = ApplicationBuilder().token(self.token).build()
        
        # Escuchar todos los mensajes de texto
        message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_message)
        application.add_handler(message_handler)
        
        logger.info("Bot de Telegram iniciado y escuchando señales...")
        application.run_polling()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bot = TelegramSignalBot()
    bot.run()
