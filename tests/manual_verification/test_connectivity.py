import asyncio
import aiohttp
import ccxt.async_support as ccxt

async def check_url(session, url, name):
    print(f"Checking {name} ({url})...")
    try:
        async with session.get(url, timeout=5) as response:
            print(f"  [{name}] Status: {response.status}")
    except Exception as e:
        print(f"  [{name}] Failed: {type(e).__name__}: {e}")

async def check_exchange(exchange_id):
    print(f"\nChecking CCXT ({exchange_id})...")
    try:
        ex = getattr(ccxt, exchange_id)()
        await ex.load_markets()
        print(f"  [{exchange_id}] Success! Markets: {len(ex.markets)}")
        await ex.close()
    except Exception as e:
        print(f"  [{exchange_id}] CCXT Failed: {e}")
        if 'ex' in locals(): await ex.close()

async def main():
    async with aiohttp.ClientSession() as session:
        await check_url(session, "https://www.google.com", "Google")
        await check_url(session, "https://api.binance.com/api/v3/ping", "Binance API")
        await check_url(session, "https://api.kraken.com/0/public/Time", "Kraken API")

    await check_exchange('binance')
    await check_exchange('kraken')

if __name__ == "__main__":
    asyncio.run(main())
