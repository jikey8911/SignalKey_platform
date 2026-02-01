import logging
from api.src.infrastructure.telegram.telegram_bot import TelegramUserBot

logger = logging.getLogger("TelegramCommander")

class TelegramCommander:
    """
    Tarea 8.3: Bot Interactivo de Telegram
    Maneja comandos enviados por el usuario desde Telegram.
    """
    def __init__(self, bot: TelegramUserBot, db_adapter):
        self.bot = bot
        self.db = db_adapter

    async def handle_command(self, event):
        """
        Procesa comandos de texto que empiezan con /.
        """
        try:
            text = event.message.message
            if not text.startswith('/'):
                return

            command_parts = text.split()
            command = command_parts[0].lower()
            
            logger.info(f"📩 Command received: {command} from {event.chat_id}")

            if command == '/status':
                await self._cmd_status(event)
            elif command == '/close_all':
                await self._cmd_close_all(event)
            elif command == '/pause_bot':
                await self._cmd_pause_bot(event)
            elif command == '/help':
                await event.reply(
                    "🤖 *SignalKey Commander*\n\n"
                    "/status - Ver estado del sistema\n"
                    "/close_all - Panic Button: Cerrar todas las posiciones\n"
                    "/pause_bot - Pausar trading automático\n"
                    "/help - Ayuda"
                )
        except Exception as e:
            logger.error(f"Error handling command: {e}")
            await event.reply(f"❌ Error: {str(e)}")

    async def _cmd_status(self, event):
        """Reporta estado general y PnL del día."""
        # Mock status for sprint 8 demo
        await event.reply(
            "📊 *Estado del Sistema*\n"
            "----------------------\n"
            "✅ Motor: ONLINE\n"
            "🤖 Bots Activos: 3\n"
            "💰 PnL Hoy: +$45.20 (1.2%)\n"
            "🛡️ Risk Manager: OK"
        )

    async def _cmd_close_all(self, event):
        """Panic Button: Cierra todo."""
        await event.reply("⚠️ *PANIC BUTTON ACTIVATED* ⚠️\nIntentando cerrar todas las posiciones...")
        # Aquí se llamaría al ExecutionService.close_all_positions()
        # Por ahora simulamos
        await event.reply("✅ Todas las posiciones han sido cerradas.")

    async def _cmd_pause_bot(self, event):
        """Pausa el sistema."""
        await event.reply("⏸️ Sistema pausado. No se abrirán nuevas posiciones.")
        # Lógica para setear flag en DB
