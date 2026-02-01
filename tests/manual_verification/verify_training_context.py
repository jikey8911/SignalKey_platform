import pandas as pd
from api.ml.strategy_trainer import StrategyTrainer

def verify_position_context():
    print("🧪 Verifying Task 5.1: Position Context Logic...")
    
    # 1. Create Mock Data
    data = {
        'close': [100, 100, 95, 90, 85, 110, 120, 120],
        'signal': [0,   1,   1,  0,  0,   2,   0,   0] 
        # Index:   0    1    2   3   4    5    6    7
        # Actions:
        # 0: Hold
        # 1: BUY (Open / Start DCA)
        # 2: BUY (DCA at 95)
        # 3: Hold (in pos, price 90 -> PnL -)
        # 4: Hold (in pos, price 85 -> PnL --)
        # 5: SELL (Close at 110)
        # 6: Hold (No pos)
    }
    df = pd.DataFrame(data)
    
    trainer = StrategyTrainer()
    
    # 2. Apply Logic
    df_processed = trainer._apply_position_context(df)
    
    print("\n📊 Processed Data Preview:")
    print(df_processed[['close', 'signal', 'in_position', 'dca_count', 'current_pnl']])
    
    # 3. Assertions
    # T=0: Init (No pos)
    
    # T=2: Validating Row 2 (After T=1 Signal=1)
    # At T=1 signal was 1 (BUY). So at T=2 we should be IN POS.
    # Entry Price = Close at T=2 (Simulated execution on close/next open) -> 95
    # Wait, the loop uses current_close as execution price if signal was previous. 
    # Logic: if prev_signal == 1: pos_avg = current_close.
    
    # Row 2 (Index 2): Prev=1. New Pos. PosAvg=95. InPos=1. PnL=0.
    row2 = df_processed.iloc[2]
    assert row2['in_position'] == 1, f"Row 2 should be in position. Got {row2['in_position']}"
    assert row2['dca_count'] == 1, f"Row 2 DCA count should be 1. Got {row2['dca_count']}"
    
    # Row 3 (Index 3): Prev=1 (DCA). Close=90.
    # Previous PosAvg=95. Signal at T=2 was 1 (BUY).
    # New calculation: ((95 * 1) + 90) / 2 = 92.5 Avg.
    # In Pos = 1. DCA = 2.
    # PnL = (90 - 92.5) / 92.5 = -0.027
    row3 = df_processed.iloc[3]
    assert row3['in_position'] == 1, "Row 3 should be in position"
    assert row3['dca_count'] == 2, f"Row 3 DCA count should be 2. Got {row3['dca_count']}"
    expected_pnl = (90 - 92.5) / 92.5
    assert abs(row3['current_pnl'] - expected_pnl) < 0.001, f"PnL mismatch. Expected {expected_pnl}, got {row3['current_pnl']}"

    # Row 5 (Index 5): Prev=0. Close=110. Signal=2 (SELL).
    # We are still in pos from previous.
    # Avg is still 92.5.
    # PnL = (110 - 92.5) / 92.5 = 0.189
    row5 = df_processed.iloc[5]
    assert row5['in_position'] == 1, "Row 5 should be in position before close"
    
    # Row 6 (Index 6): Prev=2 (SELL). Close=120.
    # Should be closed. InPos=0.
    row6 = df_processed.iloc[6]
    assert row6['in_position'] == 0, "Row 6 should be closed"
    
    print("\n✅ Verification Passed: Position Context Logic is correct.")

if __name__ == "__main__":
    verify_position_context()
