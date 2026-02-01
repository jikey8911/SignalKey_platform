import asyncio
import aiohttp
from aiohttp.resolver import ThreadedResolver

async def test():
    print("Testing with ThreadedResolver...")
    resolver = ThreadedResolver()
    connector = aiohttp.TCPConnector(resolver=resolver)
    
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get("https://api.binance.com/api/v3/ping", timeout=5) as resp:
                print(f"Binance Status: {resp.status}")
                print("SUCCESS! ThreadedResolver works.")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(test())
