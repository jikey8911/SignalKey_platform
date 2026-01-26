import sys
import os
import asyncio
sys.path.append(os.getcwd()) # Ensure api module is found
from telethon import TelegramClient
from api.config import Config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    api_id = Config.TELEGRAM_API_ID
    api_hash = Config.TELEGRAM_API_HASH
    
    if not api_id or not api_hash:
        print("Error: TELEGRAM_API_ID or TELEGRAM_API_HASH not set in .env")
        return

    session_file = 'userbot_session'
    
    print(f"Connecting to Telegram with API ID: {api_id}...")
    
    client = TelegramClient(session_file, int(api_id), api_hash)
    
    # client.start() is a coroutine that handles the flow:
    # 1. Connect
    # 2. Check if authorized
    # 3. If not, ask for phone (via input())
    # 4. Ask for code (via input())
    # 5. Ask for 2FA password (via input()) if enabled
    
    await client.start()
    
    print("Successfully authenticated! Session file created.")
    print(f"Session saved to: {session_file}.session")
    
    me = await client.get_me()
    print(f"Logged in as: {me.username} ({me.first_name})")
    
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
