import asyncio
import ccxt.async_support as ccxt
import ssl

async def test_fetch():
    print(f"SSL Module accessible: {ssl.OPENSSL_VERSION}")
    
    print("\n--- Test 1: Standard Connection ---")
    try:
        exchange = ccxt.binance()
        print("Fetching markets...")
        markets = await exchange.load_markets()
        print(f"Success! {len(markets)} markets loaded.")
        await exchange.close()
    except Exception as e:
        print(f"Failed: {type(e).__name__}: {e}")
        await exchange.close()

    print("\n--- Test 2: SSL Verify Disabled ---")
    try:
        # Disable SSL verification
        exchange = ccxt.binance({
            'verify': False, 
            'aiohttp_trust_env': True # Try using system trust settings
        })
        print("Fetching markets (No SSL verify)...")
        markets = await exchange.load_markets()
        print(f"Success! {len(markets)} markets loaded.")
        await exchange.close()
    except Exception as e:
        print(f"Failed: {type(e).__name__}: {e}")
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(test_fetch())
