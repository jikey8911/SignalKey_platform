import asyncio
from api.services.ccxt_service import ccxt_service

async def test_ccxt():
    print("Testing Binance Markets...")
    markets = await ccxt_service.get_markets("binance")
    print(f"Markets: {markets}")
    
    print("\nTesting Binance Symbols (Spot)...")
    symbols = await ccxt_service.get_symbols_with_tickers("binance", "spot")
    print(f"Symbols found: {len(symbols)}")
    if symbols:
        print(f"Sample: {symbols[0]}")

if __name__ == "__main__":
    asyncio.run(test_ccxt())
