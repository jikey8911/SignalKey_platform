import asyncio
from api.services.ccxt_service import ccxt_service

async def test_ccxt_types():
    print("--- Testing Binance Markets ---")
    markets = await ccxt_service.get_markets("binance")
    print(f"Available Markets: {markets}")
    
    if 'swap' in markets:
        print("\n--- Testing Binance Symbols (Swap) ---")
        symbols = await ccxt_service.get_symbols_with_tickers("binance", "swap")
        print(f"Swap Symbols found: {len(symbols)}")
        if symbols:
            print(f"Sample: {symbols[0]['symbol']} | Price: {symbols[0]['price']}")
    else:
        print("\n'swap' market not found in available markets.")

    print("\n--- Testing Binance Symbols (Spot) ---")
    symbols = await ccxt_service.get_symbols_with_tickers("binance", "spot")
    print(f"Spot Symbols found: {len(symbols)}")

if __name__ == "__main__":
    asyncio.run(test_ccxt_types())
