
import pytest
import sys
import os
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

# Add api to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from api.src.application.services.backtest_service import BacktestService
from api.strategies.rsi_reversion import RsiReversion as RSIReversion

@pytest.mark.asyncio
async def test_run_backtest_accumulation():
    # 1. Prepare Mock OHLCV Data (List of Lists for CCXT)
    # Format: [timestamp, open, high, low, close, volume]
    base_price = 100
    start_time = 1600000000000 # dummy ms timestamp
    
    ohlcv_data = []
    
    # Phase 1: Gradual Drop (Accumulation Zone)
    # Price drops slowly, should trigger RSI oversold MULTIPLE times
    for i in range(50):
        ohlcv_data.append([
            start_time + (i * 3600000), 
            base_price, 
            base_price + 2, 
            base_price - 2, 
            base_price - (i * 0.5), # Drop 0.5 each hour 
            1000
        ])
        
    last_price = ohlcv_data[-1][4]
    last_time = ohlcv_data[-1][0]
    
    # Phase 2: Pump (Reversal Zone)
    # Price shoots up, triggers RSI overbought -> SELL -> Close Position
    for i in range(1, 40):
        ohlcv_data.append([
            last_time + (i * 3600000),
            last_price,
            last_price + 2,
            last_price - 2,
            200, # Sharp Pump to 200
            1000
        ])

    # 2. Mock Exchange Adapter
    mock_exchange = AsyncMock()
    
    # Mock get_historical_data to return DataFrame
    df_data = pd.DataFrame(ohlcv_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df_data['timestamp'] = pd.to_datetime(df_data['timestamp'], unit='ms')
    mock_exchange.get_historical_data = AsyncMock(return_value=df_data)

    service = BacktestService(exchange_adapter=mock_exchange)
    # 3. Mock Strategy Trainer / Discovery
    # We want strict logic: RSI < 30 BUY, RSI > 70 SELL
    strategy = RSIReversion(config={'oversold': 40, 'overbought': 60}) # Relaxed to ensure accumulation
        
    service.ml_service.select_best_strategy = MagicMock(return_value={
        'strategy_name': 'RSIReversion',
        'model_used': 'TEST_MOCK',
        'confidence': 0.99
    })
    
    # Ensure our specific strategy instance is used
    service.strategies = {'RSIReversion': strategy}

    # 4. Run Backtest
    print("🚀 Starting Backtest Run...")
    result = await service.run_backtest(
        user_id="integration_test_user",
        symbol="BTC/USDT",
        days=7,
        timeframe="1h",
        initial_balance=10000
    )
        
    # 5. Analyze Results
    if 'error' in result:
        pytest.fail(f"Backtest returned error: {result['error']}")
        
    trades = result.get('trades', [])
    print(f"✅ Backtest Finished. Trades found: {len(trades)}")
    
    buy_trades = [t for t in trades if t['type'] == 'BUY']
    sell_trades = [t for t in trades if t['type'] == 'SELL_TO_CLOSE']
    
    print("\n--- Trade Log ---")
    for t in trades:
        print(f"{t['time']} | {t['type']} | Price: {t['price']} | Amt: {t['amount']} | Pos#: {t.get('position_number', 'N/A')}")
        
    # Assertions
    assert len(trades) > 0, "No trades executed"
    
    # Check Accumulation: Should have multiple BUYS
    # With the drop pattern, RSI should stay low for a while
    assert len(buy_trades) >= 2, f"Expected accumulation (>=2 buys), got {len(buy_trades)}"
    
    # Check Exit: Should have CLOSED the position
    assert len(sell_trades) >= 1, "Position was not closed on reversal"
    
    # Check Profitability
    final_balance = result['metrics']['final_balance']
    print(f"Final Balance: {final_balance}")
    assert final_balance > 10000, "Strategy failed to profit on evident pump"

if __name__ == "__main__":
    # Allow running directly script
    os.system("pytest api/tests/test_backtest_integration.py -v -s")
