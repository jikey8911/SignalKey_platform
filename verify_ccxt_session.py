import asyncio
import ccxt.async_support as ccxt
import aiohttp
from aiohttp.resolver import ThreadedResolver

async def test():
    print("Initializing custom session with ThreadedResolver...")
    resolver = ThreadedResolver()
    connector = aiohttp.TCPConnector(resolver=resolver)
    session = aiohttp.ClientSession(connector=connector)
    
    print("Creating exchange with injected session...")
    # CCXT allows overriding session via constructor config in some versions, 
    # or by property assignment. We try constructor first.
    try:
        # Note: CCXT constructor expects config dict. 'session' is not a standard config key 
        # but modern ccxt might handle it or we assign later.
        exchange = ccxt.binance({
            'enableRateLimit': True,
        })
        
        # Inject the session manually to be safe
        # IMPORTANT: CCXT manages closing the session if it created it. 
        # If we inject it, we might need to manage it, but let's see.
        exchange.session = session
        
        print("Loading markets...")
        markets = await exchange.load_markets()
        print(f"SUCCESS! Markets loaded: {len(markets)}")
        
        await exchange.close() 
        # Note: exchange.close() usually closes the session. 
        # Since we injected it, we verify if it's closed.
        if not session.closed:
            await session.close()
            
    except Exception as e:
        print(f"FAILED: {e}")
        if not session.closed:
            await session.close()

if __name__ == "__main__":
    asyncio.run(test())
