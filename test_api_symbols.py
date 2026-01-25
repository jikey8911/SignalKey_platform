import asyncio
import aiohttp

async def test_api_symbols():
    """Test the actual API endpoint that the frontend calls"""
    base_url = "http://localhost:8000"
    user_id = "juank8911"
    exchange_id = "binance"
    
    async with aiohttp.ClientSession() as session:
        for market_type in ['spot', 'swap', 'future']:
            print(f"\n{'='*60}")
            print(f"Testing: {exchange_id} - {market_type}")
            print(f"{'='*60}")
            
            url = f"{base_url}/backtest/symbols/{user_id}/{exchange_id}?market_type={market_type}"
            print(f"URL: {url}")
            
            try:
                async with session.get(url, timeout=10) as resp:
                    print(f"Status: {resp.status}")
                    
                    if resp.status == 200:
                        data = await resp.json()
                        symbols = data.get('symbols', [])
                        print(f"Symbols returned: {len(symbols)}")
                        
                        if symbols:
                            print(f"Sample symbols:")
                            for sym in symbols[:3]:
                                print(f"  - {sym['symbol']} | Price: ${sym['price']}")
                        else:
                            print("  ⚠️ NO SYMBOLS RETURNED")
                    else:
                        text = await resp.text()
                        print(f"Error response: {text[:200]}")
                        
            except Exception as e:
                print(f"❌ Request failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_api_symbols())
