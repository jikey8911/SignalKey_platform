from telethon import TelegramClient, events
from api.config import Config
from api.models.schemas import TradingSignal
from api.models.mongodb import db
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
        self.api_url = "http://localhost:8000/webhook/signal"

        if not self.api_id or not self.api_hash:
            logger.warning("TELEGRAM_API_ID or TELEGRAM_API_HASH not set. UserBot will not start.")

    async def get_dialogs(self):
        if not self.client:
            return []
        dialogs = []
        try:
            # We need to ensure we are connected before fetching dialogs.
            # Usually start() is called at startup.
            if not self.client.is_connected():
                 # Maybe we shouldn't force connect here if start failed.
                 return []
                 
            async for dialog in self.client.iter_dialogs(limit=50):
                if dialog.is_channel or dialog.is_group:
                    # Provide ID as string to match JS expectations and avoid bigInt issues
                    dialogs.append({"id": str(dialog.id), "name": dialog.name})
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
            
            if not text:
                return

            try:
                # Fetch all configs (optimization needed for prod)
                # TODO: This pulls ALL configs. In production, we need to map to specific user.
                cursor = db.app_configs.find({})
                configs = await cursor.to_list(length=10)
                
                allowed = False
                for config in configs:
                    channels = config.get("telegramChannels", {})
                    allow_list = channels.get("allow", [])
                    deny_list = channels.get("deny", [])
                    
                    if chat_id in deny_list:
                        # Explicit deny always wins for this config
                        continue
                    
                    if not allow_list: 
                        # If allow list is missing or empty, LEGACY mode: ALLOW ALL
                        # UNLESS 'telegramChannels' key exists and is empty list?
                        # Let's say: If 'allow' is empty, we allow.
                        allowed = True
                        break

                    if chat_id in allow_list:
                        allowed = True
                        break
                
                # If after checking all configs, allowed is still False
                if not allowed:
                    return

            except Exception as e:
                logger.error(f"Error checking permissions: {e}")

            logger.info(f"Processing Signal from {chat_id}")
            
            async with httpx.AsyncClient() as client:
                try:
                    payload = {
                        "source": f"telegram_{chat_id}",
                        "raw_text": text
                    }
                    response = await client.post(self.api_url, json=payload)
                    if response.status_code != 200:
                         logger.error(f"Error sending signal to API: {response.text}")
                except Exception as e:
                    logger.error(f"Error connection to API: {e}")

        try:
            await self.client.start()
            logger.info("Telegram UserBot started!")
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
