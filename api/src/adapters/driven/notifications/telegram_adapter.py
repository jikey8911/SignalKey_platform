import logging
from api.src.infrastructure.telegram.telegram_bot import TelegramUserBot

logger = logging.getLogger("TelegramAdapter")

class TelegramAdapter:
    """
    Tarea 6.3: Notificaciones Telegram (Alertas Reales)
    Encargado de enviar notificaciones formateadas sobre la ejecución de operaciones.
    """
    def __init__(self, bot: TelegramUserBot = None, user_id: str = None):
        self.bot = bot
        self.user_id = user_id

    async def send_trade_alert(self, trade_data):
        """
        Envía una alerta con formato Markdown sobre una operación ejecutada.
        
        Args:
            trade_data (dict): Datos de la operación.
                - symbol: par operado (e.g. 'BTC/USDT')
                - side: 'buy' o 'sell'
                - price: precio de ejecución
                - amount: cantidad
                - pnl: (opcional) ganancia/pérdida
                - is_simulated: (opcional) bool para indicar si es simulación
        """
        if not self.bot or not self.bot.client:
            logger.warning(f"⚠️ Cannot send alert: Bot client not connected for user {self.user_id}")
            return

        try:
            # Icono según tipo
            icon = "🟢" if trade_data['side'].lower() == 'buy' else "🔴"
            mode_tag = " [SIMULADO]" if trade_data.get('is_simulated', False) else ""
            
            pnl_info = ""
            if 'pnl' in trade_data:
                pnl_val = trade_data['pnl']
                pnl_icon = "💰" if pnl_val >= 0 else "💸"
                pnl_info = f"\n{pnl_icon} PnL Estimado: {pnl_val:.2f}"

            msg = (
                f"{icon} *OPERACIÓN EJECUTADA*{mode_tag}\n"
                f"--------------------------------\n"
                f"💎 Símbolo: `{trade_data['symbol']}`\n"
                f"📉 Tipo: *{trade_data['side'].upper()}*\n"
                f"💲 Precio: {trade_data['price']}\n"
                f"⚖️ Cantidad: {trade_data['amount']}"
                f"{pnl_info}\n"
                f"⏱️ {trade_data.get('timestamp', '')}"
            )
            
            # Enviar mensaje a "Saved Messages" del propio usuario (me) o a un chat configurado
            # Por defecto enviamos a 'me' (Mensajes Guardados) para alertas personales
            await self.bot.client.send_message('me', msg, parse_mode='markdown')
            logger.info(f"✅ Trade alert sent for {trade_data['symbol']}")
            
        except Exception as e:
            logger.error(f"❌ Error sending Telegram alert: {e}")
