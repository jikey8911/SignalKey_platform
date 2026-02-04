import asyncio
import os
import sys
from telethon import TelegramClient
from api.config import Config

async def test_session():
    api_id = Config.TELEGRAM_API_ID
    api_hash = Config.TELEGRAM_API_HASH
    session_path = 'api/src/infrastructure/telegram/userbot_session'

    print(f"Testing session at: {session_path}.session")
    print(f"API_ID: {api_id}")

    if not api_id or not api_hash:
        print("Error: No API_ID or API_HASH in Config")
        return

    client = TelegramClient(session_path, int(api_id), api_hash)
    await client.connect()

    authorized = await client.is_user_authorized()
    print(f"Is authorized: {authorized}")

    if authorized:
        me = await client.get_me()
        print(f"Connected as: {me.username or me.first_name}")
    else:
        print("NOT AUTHORIZED. Session might be invalid or credentials don't match.")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(test_session())
