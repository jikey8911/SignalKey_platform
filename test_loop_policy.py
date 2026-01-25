import asyncio
import aiohttp
import sys

# Workaround for Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def test():
    print("Testing with WindowsSelectorEventLoopPolicy...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.binance.com/api/v3/ping", timeout=5) as resp:
                print(f"Binance Status: {resp.status}")
                print("SUCCESS! Connectivity repaired.")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(test())
