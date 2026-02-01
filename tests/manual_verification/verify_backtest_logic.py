
import pandas as pd
from datetime import datetime, timedelta

# Mocking the essential logic from BacktestService.run_backtest for verification
def run_simulation():
    # Synthetic Data:
    # 1. Buy (100)
    # 2. DCA Buy (90) -> Avg Entry 95
    # 3. SELL FLIP (110) -> Should Close Long at 110, Open Short at 110.
    # 4. DCA Short (120) -> Avg Entry 115
    # 5. BUY FLIP (105) -> Should Close Short at 105, Open Long at 105.
    
    data = [
        {"time": datetime(2026, 1, 1, 10, 0), "close": 100.0, "ai_signal": 1}, # OPEN LONG
        {"time": datetime(2026, 1, 1, 11, 0), "close": 90.0,  "ai_signal": 1}, # DCA LONG
        {"time": datetime(2026, 1, 1, 12, 0), "close": 110.0, "ai_signal": 2}, # FLIP TO SHORT
        {"time": datetime(2026, 1, 1, 13, 0), "close": 120.0, "ai_signal": 2}, # DCA SHORT
        {"time": datetime(2026, 1, 1, 14, 0), "close": 105.0, "ai_signal": 1}, # FLIP TO LONG
    ]
    
    df_processed = pd.DataFrame(data)
    
    # State Variables
    balance = 10000.0
    initial_balance = 10000.0
    long_amount = 0.0
    short_amount = 0.0
    long_invested = 0.0
    short_invested = 0.0
    step_investment = 100.0
    
    trades = []
    
    print(f"--- START SIMULATION ---")
    print(f"Initial Balance: {balance}")
    print(f"Step Investment: {step_investment}")
    print("-" * 50)

    for index, row in df_processed.iterrows():
        price = row['close']
        signal = row['ai_signal']
        timestamp = row['time']
        
        print(f"\n[T{index+1}] Time: {timestamp.time()} | Price: {price} | Signal: {signal} ({'LONG' if signal==1 else 'SHORT'})")

        if signal == 1: # SIGNAL: BUY / LONG
            # 1. Close Shorts if any exist
            if short_amount > 0:
                print(f"   -> CLOSING SHORT Positions...")
                pnl = short_invested - (short_amount * price)
                balance += short_invested + pnl
                avg_entry_price = short_invested / short_amount if short_amount > 0 else 0
                pnl_percent = (pnl / short_invested * 100) if short_invested > 0 else 0
                
                trade_record = {
                    "type": "BUY (Close Short)",
                    "price": price,
                    "amount": short_amount,
                    "pnl": round(pnl, 2),
                    "pnl_percent": round(pnl_percent, 2),
                    "avg_entry": round(avg_entry_price, 2),
                    "label": "CLOSE_SHORT"
                }
                trades.append(trade_record)
                print(f"      EXECUTION: Sold {short_amount:.4f} units at ${price}. Entry Avg: ${avg_entry_price:.2f}. PnL: ${pnl:.2f} ({pnl_percent:.2f}%)")
                
                short_amount = 0
                short_invested = 0
            
            # 2. Open/Increase Long (DCA)
            if balance >= step_investment:
                is_dca = long_amount > 0
                amount_to_buy = step_investment / price
                long_amount += amount_to_buy
                long_invested += step_investment
                balance -= step_investment
                avg_entry = long_invested / long_amount
                
                label = "DCA_LONG" if is_dca else "OPEN_LONG"
                print(f"   -> OPENING/INCREASING LONG ({label})...")
                
                trade_record = {
                    "type": "BUY",
                    "price": price,
                    "amount": amount_to_buy,
                    "avg_price": round(avg_entry, 2),
                    "label": label
                }
                trades.append(trade_record)
                print(f"      EXECUTION: Bought {amount_to_buy:.4f} units at ${price}. New Avg Entry: ${avg_entry:.2f}")

        elif signal == 2: # SIGNAL: SELL / SHORT
            # 1. Close Longs if any exist
            if long_amount > 0:
                print(f"   -> CLOSING LONG Positions...")
                pnl = (long_amount * price) - long_invested
                balance += (long_amount * price)
                avg_entry_price = long_invested / long_amount if long_amount > 0 else 0
                pnl_percent = (pnl / long_invested * 100) if long_invested > 0 else 0
                
                trade_record = {
                    "type": "SELL (Close Long)",
                    "price": price,
                    "amount": long_amount,
                    "pnl": round(pnl, 2),
                    "pnl_percent": round(pnl_percent, 2),
                    "avg_entry": round(avg_entry_price, 2),
                    "label": "CLOSE_LONG"
                }
                trades.append(trade_record)
                print(f"      EXECUTION: Sold {long_amount:.4f} units at ${price}. Entry Avg: ${avg_entry_price:.2f}. PnL: ${pnl:.2f} ({pnl_percent:.2f}%)")
                
                long_amount = 0
                long_invested = 0
                
            # 2. Open/Increase Short (DCA)
            if balance >= step_investment:
                is_dca = short_amount > 0
                amount_to_short = step_investment / price
                short_amount += amount_to_short
                short_invested += step_investment
                balance -= step_investment
                avg_entry = short_invested / short_amount
                
                label = "DCA_SHORT" if is_dca else "OPEN_SHORT"
                print(f"   -> OPENING/INCREASING SHORT ({label})...")
                
                trade_record = {
                    "type": "SELL",
                    "price": price,
                    "amount": amount_to_short,
                    "avg_price": round(avg_entry, 2),
                    "label": label
                }
                trades.append(trade_record)
                print(f"      EXECUTION: Sold {amount_to_short:.4f} units at ${price}. New Avg Entry: ${avg_entry:.2f}")

    print("\n--- SUMMARY OF TRADES ---")
    for t in trades:
        print(f"{t['label']:<12} | Price: {t['price']:<8} | Amount: {t['amount']:<8.4f} | PnL: {t.get('pnl', '-'):<8}")

if __name__ == "__main__":
    run_simulation()
