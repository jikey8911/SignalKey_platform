import asyncio
import sys
import os
import json
import logging
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta
import random

# Add project root to path
sys.path.append(os.getcwd())

from api.src.application.services.backtest_service import BacktestService

# Mock data generator
def generate_dummy_ohlcv(length=500):
    data = []
    base_price = 50000.0
    now = datetime.now()
    for i in range(length):
        start = now - timedelta(hours=length-i)
        ts = int(start.timestamp() * 1000)
        open_p = base_price
        base_price += random.uniform(-100, 100)
        close_p = base_price
        high_p = max(open_p, close_p) + random.uniform(0, 50)
        low_p = min(open_p, close_p) - random.uniform(0, 50)
        vol = random.uniform(10, 100)
        data.append([ts, open_p, high_p, low_p, close_p, vol])
    return data

async def main():
    print("🚀 Starting Backtest Service Verification (Mocked Data)...")
    
    # Instantiate
    service = BacktestService()
    
    # Updated to patch CCXTAdapter since BacktestService now uses it
    from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service

    # Mock the adapter method
    ccxt_service.get_historical_ohlcv = AsyncMock(return_value=generate_dummy_ohlcv(1000))
    
    # We don't need to patch the internal context manager logic anymore, just the service call
    
    # Define variables
    symbol = "BTC/USDT"
    timeframe = "1h"
    days = 15
    
    print(f"Running backtest for {symbol} ({days} days)...")
    
    try:
        # Let's patch `getattr`? No, simpler to patch `ccxt.async_support.binance`.
        
        result = await service.run_backtest(
            user_id="test_verifier",
            symbol=symbol,
            days=days,
            timeframe=timeframe,
            use_ai=True,
            strategy="auto"
        )
    
        if "error" in result:
            print(f"❌ Error: {result['error']}")
            return

        print("\n✅ Backtest Completed Successfully (Simulated)!")
        print(f"Strategy: {result.get('strategy_name')}")
        
        metrics = result.get('metrics', {})
        print("\n📊 Metrics:")
        print(json.dumps(metrics, indent=2))
        
        chart_data = result.get('chart_data', [])
        print(f"\n📈 Chart Data Points: {len(chart_data)}")
        if chart_data:
            print(f"Sample First Point: {chart_data[0]}")
            print(f"Sample Last Point: {chart_data[-1]}")
            
        bot_config = result.get('bot_configuration', {})
        print("\n🤖 Bot Configuration:")
        print(json.dumps(bot_config, indent=2))
        
        trades = result.get('trades', [])
        print(f"\n💰 Total Trades Executed: {len(trades)}")
        if trades:
            print(json.dumps(trades[0], indent=2))
        
        # Validation checks
        assert len(chart_data) > 0, "Chart data should not be empty"
        assert 'bot_configuration' in result, "Bot configuration missing"
        assert 'strategy_type' in bot_config, "Bot config incomplete"
        
        print("\n✅ Verification PASSED")
        
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
