import unittest
import asyncio
import pandas as pd
import numpy as np
import shutil
import os
import sys

# Asegurar path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.services.ml_service import MLService
from api.services.cex_service import CEXService
from unittest.mock import MagicMock, AsyncMock

class TestEndToEnd(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # setUp is sync, asyncSetUp is async
        pass

    def setUp(self):
        # Mock CEX Service to return synthetic data
        self.mock_cex = MagicMock(spec=CEXService)
        # Setup AsyncMock for get_exchange_instance
        self.mock_exchange = AsyncMock()
        self.mock_exchange.has = {'fetchOHLCV': True}
        self.mock_exchange.id = 'mock_exchange'
        # Fix: parse8601 can be a simple function (sync)
        self.mock_exchange.parse8601 = lambda x: 1672531200000 
        
        self.mock_cex.get_exchange_instance = AsyncMock(return_value=(self.mock_exchange, {}))
        self.mock_cex.get_public_exchange_instance = AsyncMock(return_value=self.mock_exchange)
        
        self.ml_service = MLService(cex_service=self.mock_cex)
        # Use a temporary test directory for models
        self.ml_service.models_dir = "api/tests/temp_models"
        os.makedirs(self.ml_service.models_dir, exist_ok=True)
        
        # Hyperparameters for fast test
        self.ml_service.seq_length = 10
        self.ml_service.hidden_dim = 16
        self.ml_service.num_layers = 1
        
        # Generate Synthetic Data (Random Walk)
        dates = pd.date_range(start='2023-01-01', periods=600, freq='h')
        price = 100.0
        prices = [price]
        for _ in range(599):
            price += np.random.normal(0, 1.0)
            prices.append(price)
            
        self.ohlcv_data = []
        for i, p in enumerate(prices):
            self.ohlcv_data.append([
                dates[i].value // 10**6, # ms timestamp
                p, p+1, p-1, p, 1000 + np.random.random()*500
            ])
            
        self.mock_exchange.fetch_ohlcv = AsyncMock(return_value=self.ohlcv_data)

    def tearDown(self):
        # Cleanup
        if os.path.exists(self.ml_service.models_dir):
            try:
                shutil.rmtree(self.ml_service.models_dir)
            except: pass

    async def test_train_and_predict_flow(self):
        # Patch the global ccxt_service used in MLService
        from unittest.mock import patch
        
        with patch('api.services.ml_service.ccxt_service') as mock_ccxt_svc:
            # Configure mock to return our synthetic data
            mock_ccxt_svc.get_historical_ohlcv = AsyncMock(return_value=self.ohlcv_data)
            
            # 1. Train
            result = await self.ml_service.train_model(
                symbol="BTC/USDT", 
                timeframe="1h", 
                days=10, 
                epochs=2, # Fast training
                exchange_id="mock_exchange" # Avoid config lookup logic
            )
        
        self.assertEqual(result['status'], 'success')
        self.assertTrue(os.path.exists(result['model_path']))
        print(f"\nTraining Result: Accuracy {result['test_accuracy']:.2f}, Loss {result['final_loss']:.4f}")
        
        # 2. Predict
        # Use last N candles from generated data
        recent_candles = []
        columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        for row in self.ohlcv_data[-50:]: # Need enough for indicators (50)
             recent_candles.append(dict(zip(columns, row)))
             
        prediction = self.ml_service.predict("BTC/USDT", "1h", recent_candles)
        
        print(f"Prediction Result: {prediction}")
        
        self.assertIn(prediction['decision'], ['BUY', 'SELL', 'HOLD', 'BUY/SELL (Check Strategy)'])
        self.assertIn('strategy_selected', prediction)
        self.assertIn('class_probabilities', prediction)
        self.assertTrue(len(prediction['class_probabilities']) == 4) # 4 classes

if __name__ == '__main__':
    unittest.main()
