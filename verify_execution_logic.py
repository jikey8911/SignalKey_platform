import asyncio
from unittest.mock import MagicMock, AsyncMock
from api.src.application.services.execution_engine import ExecutionEngine
from api.strategies.base import BaseStrategy

async def verify_execution():
    print("🧪 Verifying Task 6.2 & 6.3: Execution Engine & Profit Guard...")
    
    # 1. Mock Dependencies
    mock_db = MagicMock()
    # Mock configs collection find_one
    mock_db.db.__getitem__.return_value.find_one = AsyncMock(return_value={"value": 100.0})
    
    mock_socket = AsyncMock()
    
    engine = ExecutionEngine(db_adapter=mock_db, socket_service=mock_socket)
    
    # Mock Simulator and Real Exchange
    engine.simulator = AsyncMock()
    engine.simulator.execute_trade.return_value = {"pnl": 10}
    
    engine.real_exchange = AsyncMock()
    engine.real_exchange.execute_trade.return_value = MagicMock(success=True, price=100, amount=1, order_id="123")
    
    # 2. Test Profit Guard (BLOCK SELL)
    # Scenario: In Position (Avg 100). Current Price 90. Signal SELL.
    # Should be BLOCKED.
    bot_loss = {
        'id': 'bot1',
        'symbol': 'BTC/USDT',
        'mode': 'real',
        'status': 'active',
        'position': {'qty': 1, 'avg_price': 100}
    }
    signal_sell_loss = {'signal': BaseStrategy.SIGNAL_SELL, 'price': 90}
    
    print("\n--- Testing Profit Guard (Block Loss) ---")
    res_block = await engine.process_signal(bot_loss, signal_sell_loss)
    
    if res_block and res_block.get('status') == 'blocked':
        print("✅ Profit Guard correctly BLOCKED lossy sell.")
    else:
        print(f"❌ Profit Guard FAILED. Result: {res_block}")
        
    # 3. Test Profit Guard (ALLOW PROFIT)
    # Scenario: In Position (Avg 100). Current Price 110. Signal SELL.
    # Should execute.
    signal_sell_profit = {'signal': BaseStrategy.SIGNAL_SELL, 'price': 110}
    
    print("\n--- Testing Profit Guard (Allow Profit) ---")
    res_allow = await engine.process_signal(bot_loss, signal_sell_profit)
    
    if res_allow and res_allow.get('status') == 'executed':
        print("✅ Profit Guard correctly ALLOWED profitable sell.")
    else:
        print(f"❌ Profit Guard FAILED to allow profit. Result: {res_allow}")
        
    # 4. Test Dual Mode Routing (Simulated)
    print("\n--- Testing Mode Routing (Simulated) ---")
    bot_sim = {'id': 'bot2', 'symbol': 'ETH/USDT', 'mode': 'simulated', 'status': 'active'}
    signal_buy = {'signal': BaseStrategy.SIGNAL_BUY, 'price': 2000}
    
    await engine.process_signal(bot_sim, signal_buy)
    
    if engine.simulator.execute_trade.called:
        print("✅ Routed to Simulator correctly.")
    else:
        print("❌ Failed to route to simulator.")

    # 5. Test Telegram Notification Trigger (Mock)
    # Check if socket emit was called (part of Task 6.3/4.3)
    if mock_socket.emit.called:
        print("✅ Socket event emitted (Live Monitoring).")
    else:
        print("❌ Socket event NOT emitted.")

if __name__ == "__main__":
    asyncio.run(verify_execution())
