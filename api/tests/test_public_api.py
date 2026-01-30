"""
Test script to verify public API data fetching for ML training.
This script tests that the new get_public_historical_data method works correctly
without requiring exchange credentials.
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service

async def test_public_api():
    """Test public API data fetching"""
    print("=" * 60)
    print("Testing Public API Data Fetching (No Credentials)")
    print("=" * 60)
    
    # Test parameters
    test_symbols = ['BTC/USDT', 'ETH/USDT']
    timeframe = '1h'
    limit = 100
    
    for symbol in test_symbols:
        print(f"\n📊 Testing {symbol}...")
        try:
            # Fetch data using public API
            df = await ccxt_service.get_public_historical_data(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                use_random_date=False,
                exchange_id='binance'
            )
            
            if df.empty:
                print(f"  ❌ Failed: Received empty DataFrame for {symbol}")
            else:
                print(f"  ✅ Success: Fetched {len(df)} candles")
                print(f"  📅 Date range: {df.index[0]} to {df.index[-1]}")
                print(f"  💰 Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")
                print(f"  📈 Columns: {list(df.columns)}")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    # Test with random date
    print(f"\n🎲 Testing with random historical date...")
    try:
        df = await ccxt_service.get_public_historical_data(
            symbol='BTC/USDT',
            timeframe='1h',
            limit=100,
            use_random_date=True,
            exchange_id='binance'
        )
        
        if not df.empty:
            print(f"  ✅ Success: Fetched {len(df)} candles from random period")
            print(f"  📅 Date range: {df.index[0]} to {df.index[-1]}")
        else:
            print(f"  ❌ Failed: Received empty DataFrame")
            
    except Exception as e:
        print(f"  ❌ Error: {e}")
    
    # Close connections
    await ccxt_service.close_all()
    
    print("\n" + "=" * 60)
    print("Test Complete!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_public_api())
