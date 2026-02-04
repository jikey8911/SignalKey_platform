import asyncio
import logging
import traceback
import sys
import os

# Ensure project root is in path
sys.path.append(os.getcwd())

from api.src.application.services.ml_service import MLService
from api.src.adapters.driven.exchange.ccxt_adapter import CcxtAdapter

# Configure logging to see output
logging.basicConfig(level=logging.INFO)

async def train():
    print("Starting manual training...")
    try:
        adapter = CcxtAdapter()
        service = MLService(exchange_adapter=adapter)
        
        symbols = ["BTC/USDT", "ETH/USDT"] 
        print(f"Symbols: {symbols}")
        
        # Fixed argument: 'days' instead of 'days_back'
        await service.train_all_strategies(
            symbols=symbols,
            timeframe="1h",
            days=5, 
            market_type="spot",
            user_id="default"
        )
        print("✅ Training finished.")
    except Exception as e:
        print(f"ERROR inside train: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(train())
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        traceback.print_exc()
