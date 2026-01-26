import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_dns_resolution():
    print("Testing OKX Connection via CCXT Adapter...")
    try:
        # Test fetch_ohlcv which was failing
        ohlcv = await ccxt_service.get_historical_ohlcv("BTC/USDT", "okx", "1h", days_back=1)
        
        if ohlcv and len(ohlcv) > 0:
            print(f"✅ SUCCESS: Fetched {len(ohlcv)} candles from OKX")
            print(f"Sample: {ohlcv[0]}")
        else:
            print("❌ FAILED: No data returned but no exception")
            
    except Exception as e:
        print(f"❌ FAILED with Exception: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await ccxt_service.close_all()

if __name__ == "__main__":
    asyncio.run(test_dns_resolution())
