import pandas as pd
from api.src.application.services.backtest_service import BacktestService
from api.strategies.base import BaseStrategy

class MockExchange:
    pass

def verify_fidelity():
    print("🧪 Verifying Task 5.2: Backtest Fidelity (High/Low)...")
    
    # 1. Setup Service (Mocking dependencies)
    bs = BacktestService(exchange_adapter=MockExchange())
    
    # 2. Test Case 1: High Wick Entry (TP)
    # Row 0: Init (Signal 0)
    # Row 1: Entry (Signal 1) -> Opens Position
    # Row 2: Wick Test (Signal 0/1) -> Logic Checks TP/SL
    idx = pd.date_range("2023-01-01", periods=3, freq="1H")
    data_tp = {
        'close': [100, 100, 101],
        'high':  [100, 100, 105], # Hit 103 on T=2
        'low':   [100, 100, 99],
        'ai_signal': [0, BaseStrategy.SIGNAL_BUY, 0] 
    }
    df_tp = pd.DataFrame(data_tp, index=idx)
    
    # Needs trade_amount logic to work (default 20% balance)
    res_tp = bs.simulate_dca_logic(df_tp, initial_balance=1000, trade_amount=100, tp=0.03, sl=0.10)
    print("\n--- TP Test ---")
    
    trades = res_tp['trades']
    # Expect: 
    # 1. OPEN_LONG at T=1
    # 2. TP_HIT_LONG at T=2
    found_tp = any(t['label'] == "TP_HIT_LONG" for t in trades)
    if found_tp:
        print("✅ TP Hit on High Wick confirmed.")
    else:
        print(f"❌ Failed TP Hit. Trades: {[t['label'] for t in trades]}")

    # 3. Test Case 2: Pessimistic Conflict (SL vs TP)
    # Entry at 100. TP 3% (103). SL 2% (98).
    # Wick goes High 110 (TP hit) AND Low 90 (SL hit).
    data_conflict = {
        'close': [100, 100, 100],
        'high':  [100, 100, 110], 
        'low':   [100, 100, 90],  
        'ai_signal': [0, BaseStrategy.SIGNAL_BUY, 0] 
    }
    df_conflict = pd.DataFrame(data_conflict, index=idx)
    
    res_conflict = bs.simulate_dca_logic(df_conflict, initial_balance=1000, trade_amount=100, tp=0.03, sl=0.02)
    print("\n--- Conflict Test (Pessimistic) ---")
    trades = res_conflict['trades']
    
    # Expect:
    # 1. OPEN_LONG
    # 2. SL_HIT_LONG (Priority)
    found_sl = any(t['label'] == "SL_HIT_LONG" for t in trades)
    found_tp = any(t['label'] == "TP_HIT_LONG" for t in trades)
    
    if found_sl:
        print("✅ SL Priority confirmed (Pessimistic Execution).")
    elif found_tp:
        print("❌ Optimistic Execution detected (TP hit instead of SL).")
    else:
        print(f"❌ Failed Conflict Logic. Trades: {[t['label'] for t in trades]}")

if __name__ == "__main__":
    verify_fidelity()
