import torch
import torch.nn as nn
import torch.optim as optim
import pandas as pd
import numpy as np
from torch.utils.data import TensorDataset, DataLoader
import os
import logging
import pickle
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
import traceback
import asyncio
from functools import lru_cache

# No external ML libs to avoid dependency hell on Python 3.14
# from sklearn.preprocessing import MinMaxScaler 
# import joblib 

from api.ml.models.lstm_model import LSTMModel
from api.src.application.services.cex_service import CEXService
from api.config import Config
from api.strategies import load_strategies
from api.utils.indicators import rsi, adx, atr, bollinger_bands, ema
from api.ml.strategy_trainer import StrategyTrainer
from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service
from api.src.adapters.driven.persistence.mongodb import db
import logging

logger = logging.getLogger(__name__)



class SimpleScaler:
    """Implementación manual de min-max scaling para evitar dependencia de sklearn/scipy"""
    def __init__(self):
        self.min_val = None
        # ... (rest of Scaler stays same, saving tokens by not repeating)
        self.max_val = None
        self.feature_range = (0, 1)

    def fit(self, data):
        if isinstance(data, pd.DataFrame):
            self.min_val = data.min().values
            self.max_val = data.max().values
        else:
            self.min_val = np.min(data, axis=0)
            self.max_val = np.max(data, axis=0)
        return self

    def transform(self, data):
        if self.min_val is None: return data
        if isinstance(data, pd.DataFrame): X = data.values
        else: X = data
        
        # Safety: replace infs
        X = np.nan_to_num(X, nan=0.0, posinf=1.0, neginf=0.0)
        
        denom = (self.max_val - self.min_val)
        denom[denom == 0] = 1.0
        X_std = (X - self.min_val) / denom
        return X_std

class MLService:
    def __init__(self, cex_service: CEXService = None):
        self.cex_service = cex_service or CEXService()
        self.models_dir = "api/data/models"
        self.datasets_dir = "api/data/datasets"
        os.makedirs(self.models_dir, exist_ok=True)
        os.makedirs(self.datasets_dir, exist_ok=True)
        
        # Meta-Model Configuration
        self.seq_length = 60 
        self.input_dim = 5    # RSI, ADX, ATR%, BB_Width, RVOL
        self.hidden_dim = 64
        self.num_layers = 2
        _, self.strategies_list = load_strategies()
        self.output_dim = len(self.strategies_list) + 1   # Strategies + HOLD
        
        self.scaler = SimpleScaler()
        
        # Virtual Balance Configuration
        self.use_virtual_balance = True
        self.default_virtual_balance = 10000.0  # Default if not found in DB

    def _prepare_features(self, df: pd.DataFrame, fit: bool = True) -> pd.DataFrame:
        """Calcula indicadores de contexto avanzado para el Meta-Selector."""
        
        # 1. RSI (Momentum)
        df['rsi'] = rsi(df['close'], 14) / 100.0  # Normalize 0-1
        
        # 2. ADX (Trend Strength)
        df['adx'] = adx(df['high'], df['low'], df['close'], 14) / 100.0
        
        # 3. ATR% (Volatility normalized)
        atr_val = atr(df['high'], df['low'], df['close'], 14)
        df['atr_pct'] = atr_val / df['close']
        
        # 4. Bollinger Bandwidth (Compression)
        bb = bollinger_bands(df['close'], 20, 2.0)
        df['bb_width'] = (bb['upper'] - bb['lower']) / bb['mid']
        
        # 5. Relative Volume (Liquidity)
        vol_sma = df['volume'].rolling(20).mean()
        # Log ratio with safety for 0 volume
        df['vol_rel'] = np.log((df['volume'] + 0.1) / (vol_sma.replace(0, 0.1)))
        
        # Drop NaN
        df.dropna(inplace=True)
        
        feature_cols = ['rsi', 'adx', 'atr_pct', 'bb_width', 'vol_rel']
        df_features = df[feature_cols].copy()
        
        # Fit scaler ONLY if requested (Training)
        if fit:
            self.scaler.fit(df_features)
        
        normalized_data = self.scaler.transform(df_features)
        return pd.DataFrame(normalized_data, columns=feature_cols)
    
    async def _get_virtual_balance(self, user_id: str, market_type: str = "CEX", asset: str = "USDT") -> float:
        """
        Obtiene el balance virtual del usuario desde MongoDB.
        Si no existe, retorna el balance por defecto.
        """
        try:
            user = await db.users.find_one({"openId": user_id})
            if not user:
                logger.warning(f"User {user_id} not found, using default balance")
                return self.default_virtual_balance
            
            balance_doc = await db.virtual_balances.find_one({
                "userId": user["_id"],
                "marketType": market_type,
                "asset": asset
            })
            
            if balance_doc and "amount" in balance_doc:
                balance = float(balance_doc["amount"])
                logger.info(f"Using virtual balance for {user_id}: {balance} {asset}")
                return balance
            else:
                logger.warning(f"No virtual balance found for {user_id}, using default")
                return self.default_virtual_balance
                
        except Exception as e:
            logger.error(f"Error retrieving virtual balance: {e}")
            return self.default_virtual_balance

    def _create_sequences(self, df_features: pd.DataFrame, df_raw: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Genera dataset para el Meta-Selector:
        X: Features normalizados (rsi, adx...) de la ventana t-N...t
        y: ID de la Estrategia Ganadora en el futuro (t...t+Horizon)
        """
        data = df_features.values
        X, y = [], []
        
        # Estrategias disponibles para el "Torneo"
        # Estrategias disponibles para el "Torneo"
        _, strategies = load_strategies()
        # Map: 0=HOLD, 1=RSI, 2=EMA, 3=Breakout
        
        horizon = 12 
        fee = 0.001 
        
        for i in range(self.seq_length, len(df_raw) - horizon):
            
            # 2. Torneo
            current_slice = df_raw.iloc[i-100:i].copy() 
            if len(current_slice) < 50: continue
            
            # Valid sample, append Features
            # 1. Input Context
            X.append(data[i-self.seq_length:i])
            
            best_pnl = 0
            best_strat_id = 0 # 0 = Hold
            
            # Precios para PnL (Future)
            entry_price = df_raw.iloc[i]['close']
            exit_price = df_raw.iloc[i+horizon]['close']
            
            for idx, strat in enumerate(strategies):
                try:
                    res = strat.get_signal(current_slice)
                    signal = res.get('signal')
                    
                    pnl = 0
                    if signal == 'buy':
                        raw_pnl = (exit_price - entry_price) / entry_price
                        pnl = raw_pnl - (fee * 2) 
                    elif signal == 'sell':
                        raw_pnl = (entry_price - exit_price) / entry_price
                        pnl = raw_pnl - (fee * 2)
                    
                    if pnl > 0.005 and pnl > best_pnl: 
                        best_pnl = pnl
                        best_strat_id = idx + 1 
                        
                except Exception:
                    continue
            
            y.append(best_strat_id)
                
        return np.array(X), np.array(y)

    def _create_sequences_from_csv(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """Reads Labeled CSV dataframe and creates sequences"""
        # CSV columns: timestamp, rsi, adx, atr_pct, bb_width, vol_rel, label
        feature_cols = ['rsi', 'adx', 'atr_pct', 'bb_width', 'vol_rel']
        
        # Scale Features
        self.scaler.fit(df[feature_cols])
        X_data = self.scaler.transform(df[feature_cols])
        y_data = df['label'].values
        
        X, y = [], []
        # Target: Predict label at step t using sequence t-N...t
        # StrategyTrainer label at row t is "Best Strategy Looking Forward".
        # So inputs X[t-N : t] -> Output y[t]
        # X_data[0:60] (indices 0..59) -> y_data[59]?
        # Yes.
        
        for i in range(self.seq_length, len(X_data)):
            X.append(X_data[i - self.seq_length : i])
            y.append(y_data[i-1]) # Label at the end of the input sequence?
            # StrategyTrainer: row "t" contains features calculated AT "t" and Label for future starting AT "t".
            # So if we execute at "t", we use Features(t) to decide.
            # So if input is X[t], output is y[t].
            # Input sequence: X[t-N...t]. We want decision for time t.
            # So y.append(y_data[i-1]) is correct (index i is exclusive upper bound, so X ends at i-1).
            
        return np.array(X), np.array(y)

    async def train_global_model(self, symbols: List[str], timeframe: str = '1h', days: int = 365, epochs: int = 20, user_id: str = "default_user", exchange_id: str = None) -> Dict[str, Any]:
        """
        Entrena un ÚNICO modelo combinando datos de múltiples símbolos.
        """
        logger.info(f"Starting GLOBAL training for {len(symbols)} symbols")
        
        # Determine exchange_id if not provided
        target_exchange_id = exchange_id
        if not target_exchange_id:
             # Fetch default active exchange from user config
             _, config = await self.cex_service.get_exchange_instance(user_id)
             if config and "exchanges" in config:
                 active_ex = next((e for e in config["exchanges"] if e.get("isActive", True)), None)
                 if active_ex:
                     target_exchange_id = active_ex["exchangeId"]
        
        if not target_exchange_id:
            raise ValueError("No exchange_id provided and no active exchange found/configured for user.")
             
        loop = asyncio.get_running_loop()
        
        all_X = []
        all_y = []
        
        processed_count = 0
        
        for symbol in symbols:
            try:
                logger.info(f"Processing symbol for Global Model: {symbol}")
                # 1. Fetch Data
                # Call new CCXTService method
                all_ohlcv = await ccxt_service.get_historical_ohlcv(
                    symbol=symbol, 
                    exchange_id=target_exchange_id, 
                    timeframe=timeframe, 
                    days_back=days
                )

                if len(all_ohlcv) < 500:
                    logger.warning(f"Skipping {symbol}: Not enough data ({len(all_ohlcv)} candles)")
                    continue
                
                logger.info(f"Fetched {len(all_ohlcv)} candles for {symbol}")
                    
                df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df.drop_duplicates(subset=['timestamp'], inplace=True)
                df.sort_values('timestamp', inplace=True)
                df.reset_index(drop=True, inplace=True)
                
                # 2. Generate Labeled Dataset with Virtual Balance
                # Get virtual balance for this user
                virtual_balance = await self._get_virtual_balance(user_id)
                logger.info(f"Generating labeled dataset for {symbol} (Balance: {virtual_balance})...")
                
                trainer = StrategyTrainer(
                    df, 
                    initial_balance=virtual_balance,
                    use_virtual_balance=self.use_virtual_balance
                )

                labeled_df = await loop.run_in_executor(None, lambda: trainer.generate_labeled_dataset(window_size=60, forecast_horizon=12))
                
                if labeled_df.empty: 
                    logger.warning(f"Labeled dataset empty for {symbol}")
                    continue
                    
                # Save individual CSV (optional but good for debugging)
                safe_symbol = symbol.replace('/', '_')
                csv_path = f"{self.datasets_dir}/{safe_symbol}_{timeframe}_labeled.csv"
                logger.info(f"Saving labeled dataset to {csv_path} ({len(labeled_df)} rows)...")
                labeled_df.to_csv(csv_path, index=False)
                logger.info(f"CSV saved successfully for {symbol}")
                
                # 3. Create Sequences
                logger.info(f"Creating sequences from labeled data for {symbol}...")
                X, y = self._create_sequences_from_csv(labeled_df)
                X, y = await loop.run_in_executor(None, lambda: self._create_sequences_from_csv(labeled_df))
                logger.info(f"Generated {len(X)} sequences for {symbol}")
                if len(X) > 0:
                    all_X.append(X)
                    all_y.append(y)
                    processed_count += 1
                    logger.info(f"Processed {symbol}: {len(X)} samples added to global dataset")
                else:
                    logger.warning(f"No sequences generated for {symbol}")
                    
            except Exception as e:
                logger.error(f"Error processing {symbol} for global model: {e}")
                logger.error(traceback.format_exc())
                continue
                
        if processed_count == 0:
            raise Exception("No data available for global training")
            
        # 4. Concatenate All Data
        logger.info(f"Concatenating data from {processed_count} symbols...")
        X_global = np.concatenate(all_X, axis=0)
        y_global = np.concatenate(all_y, axis=0)
        
        logger.info(f"Global Dataset Size: {len(X_global)} samples from {processed_count} symbols")
        
        # 5. Train Global Model
        logger.info("Splitting dataset into train/test (80/20)...")
        train_size = int(len(X_global) * 0.8)
        X_train, X_test = X_global[:train_size], X_global[train_size:]
        y_train, y_test = y_global[:train_size], y_global[train_size:]
        logger.info(f"Train set: {len(X_train)} samples, Test set: {len(X_test)} samples")
        
        logger.info("Converting data to PyTorch tensors...")
        X_train_tensor = torch.from_numpy(X_train).float()
        y_train_tensor = torch.from_numpy(y_train).long()
        X_test_tensor = torch.from_numpy(X_test).float()
        y_test_tensor = torch.from_numpy(y_test).long()
        logger.info(f"Tensor shapes - X_train: {X_train_tensor.shape}, y_train: {y_train_tensor.shape}")
        
        num_strategies = len(load_strategies()[1])
        output_dim = num_strategies + 1 # +1 for HOLD
        logger.info(f"Initializing LSTM model (input_dim={self.input_dim}, hidden_dim={self.hidden_dim}, layers={self.num_layers}, output_dim={output_dim})...")
        model = LSTMModel(self.input_dim, self.hidden_dim, self.num_layers, output_dim=output_dim)
        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(model.parameters(), lr=0.001)
        logger.info(f"Model initialized with {sum(p.numel() for p in model.parameters())} parameters")
        
        # Use DataLoader for mini-batch training to avoid memory issues and blocking
        batch_size = 64
        train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        
        model.train()
        history = {'loss': []}
        
        logger.info(f"Starting Global Model training for {epochs} epochs (Batch Size: {batch_size})...")
        for epoch in range(epochs):
            epoch_loss = 0.0
            batch_count = 0
            
            for X_batch, y_batch in train_loader:
                optimizer.zero_grad()
                output = model(X_batch)
                loss = criterion(output, y_batch)
                loss.backward()
                optimizer.step()
                
                epoch_loss += loss.item()
                batch_count += 1
                
                # Yield control to event loop every few batches to prevent WebSocket timeout
                if batch_count % 10 == 0:
                    await asyncio.sleep(0)
            
            avg_loss = epoch_loss / batch_count if batch_count > 0 else 0
            history['loss'].append(avg_loss)
            logger.info(f"Global Model - Epoch [{epoch+1}/{epochs}], Loss: {avg_loss:.4f}")
            
        # 6. Save Global Model
        # Use "GLOBAL" as symbol name
        logger.info("Saving Global Model artifacts...")
        model_name = f"GLOBAL_{timeframe}"
        model_path = f"{self.models_dir}/{model_name}_lstm.pth"
        scaler_path = f"{self.models_dir}/{model_name}_scaler.pkl"
        meta_path = f"{self.models_dir}/{model_name}_meta.json"
        
        torch.save(model.state_dict(), model_path)
        with open(scaler_path, 'wb') as f:
            pickle.dump(self.scaler, f)
            
        # Calc Accuracy
        logger.info("Calculating test accuracy...")
        model.eval()
        with torch.no_grad():
            test_pred = model(X_test_tensor)
            pred_classes = torch.argmax(test_pred, dim=1)
            accuracy_val = (pred_classes == y_test_tensor).float().mean()
            logger.info(f"Global Model Test Accuracy: {accuracy_val.item():.2%}")
            
        # Save Metadata
        import json
        metadata = {
            "symbol": "GLOBAL_MODEL",
            "timeframe": timeframe,
            "final_loss": history['loss'][-1],
            "accuracy": accuracy_val.item(),
            "last_trained": datetime.now().isoformat(),
            "samples": len(X_global),
            "model_type": "Meta-LSTM-Global",
            "included_symbols": symbols
        }
        with open(meta_path, 'w') as f:
            json.dump(metadata, f)
            
        logger.info(f"Global Model training completed successfully. Saved to {model_path}")

        return {
            "status": "success",
            "model_path": model_path,
            "final_loss": history['loss'][-1],
            "test_accuracy": accuracy_val.item(),
            "total_samples": len(X_global)
        }

    async def train_model(self, symbol: str, timeframe: str = '1h', days: int = 365, epochs: int = 20, user_id: str = "default_user", exchange_id: str = None) -> Dict[str, Any]:
        """
        Entrena el Meta-Selector usando dataset CSV generado por StrategyTrainer.
        """
        logger.info(f"Starting training for {symbol}")
        
        loop = asyncio.get_running_loop()
        try:
            # Usar instancia PÚBLICA para training (Data histórica no requiere Auth)
            # Usar instancia PÚBLICA para training (Data histórica no requiere Auth)
            target_exchange_id = exchange_id
            if not target_exchange_id:
                # Fetch default active exchange from user config
                 _, config = await self.cex_service.get_exchange_instance(user_id)
                 if config and "exchanges" in config:
                     active_ex = next((e for e in config["exchanges"] if e.get("isActive", True)), None)
                     if active_ex:
                         target_exchange_id = active_ex["exchangeId"]

            if not target_exchange_id:
                 raise ValueError("No exchange_id provided and no active exchange found/configured for user.")
 
            
            all_ohlcv = await ccxt_service.get_historical_ohlcv(
                symbol=symbol,
                exchange_id=target_exchange_id,
                timeframe=timeframe,
                days_back=days
            )
                
            if len(all_ohlcv) < 500:
                raise Exception(f"Not enough data: {len(all_ohlcv)}")
                
            df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df.drop_duplicates(subset=['timestamp'], inplace=True)
            df.sort_values('timestamp', inplace=True)
            df.reset_index(drop=True, inplace=True)
            
            # 1. Generate Labeled Dataset with Virtual Balance
            # Get virtual balance for this user
            virtual_balance = await self._get_virtual_balance(user_id)
            
            trainer = StrategyTrainer(
                df,
                initial_balance=virtual_balance,
                use_virtual_balance=self.use_virtual_balance
            )
            labeled_df = await loop.run_in_executor(None, lambda: trainer.generate_labeled_dataset(window_size=60, forecast_horizon=12))
            
            if labeled_df.empty: raise Exception("StrategyTrainer generated 0 samples")
            
            # Save CSV
            safe_symbol = symbol.replace('/', '_')
            csv_path = f"{self.datasets_dir}/{safe_symbol}_{timeframe}_labeled.csv"
            logger.info(f"Saving labeled dataset to {csv_path} ({len(labeled_df)} rows)...")
            labeled_df.to_csv(csv_path, index=False)
            logger.info(f"CSV saved successfully: {csv_path}")
            
            # 2. Train from CSV Data
            logger.info(f"Creating sequences from labeled dataset...")
            X, y = await loop.run_in_executor(None, lambda: self._create_sequences_from_csv(labeled_df))
            logger.info(f"Generated {len(X)} training sequences")
            
            if len(X) == 0: raise Exception("No sequences generated")
            
            logger.info("Splitting dataset (80% train, 20% test)...")
            train_size = int(len(X) * 0.8)
            X_train, X_test = X[:train_size], X[train_size:]
            y_train, y_test = y[:train_size], y[train_size:]
            logger.info(f"Train: {len(X_train)} samples, Test: {len(X_test)} samples")
            
            logger.info("Converting to PyTorch tensors...")
            X_train_tensor = torch.from_numpy(X_train).float()
            y_train_tensor = torch.from_numpy(y_train).long()
            X_test_tensor = torch.from_numpy(X_test).float()
            y_test_tensor = torch.from_numpy(y_test).long()
            logger.info(f"Tensor shapes - X: {X_train_tensor.shape}, y: {y_train_tensor.shape}")
            
            # 3. Model
            logger.info(f"Initializing LSTM model for {symbol}...")
            num_strategies = len(load_strategies()[1])
            output_dim = num_strategies + 1
            model = LSTMModel(self.input_dim, self.hidden_dim, self.num_layers, output_dim=output_dim)
            criterion = nn.CrossEntropyLoss()
            optimizer = optim.Adam(model.parameters(), lr=0.001)
            logger.info(f"Model has {sum(p.numel() for p in model.parameters())} trainable parameters")
            
            model.train()
            history = {'loss': []}
            
            logger.info(f"Starting training for {symbol} ({epochs} epochs)...")
            for epoch in range(epochs):
                optimizer.zero_grad()
                output = model(X_train_tensor)
                loss = criterion(output, y_train_tensor)
                loss.backward()
                optimizer.step()
                history['loss'].append(loss.item())
                await asyncio.sleep(0)
                if (epoch + 1) % 5 == 0 or epoch == 0:
                    logger.info(f"Model {symbol} - Epoch [{epoch+1}/{epochs}], Loss: {loss.item():.4f}")
            
            # 4. Save
            model_path = f"{self.models_dir}/{safe_symbol}_{timeframe}_lstm.pth"
            scaler_path = f"{self.models_dir}/{safe_symbol}_{timeframe}_scaler.pkl"
            meta_path = f"{self.models_dir}/{safe_symbol}_{timeframe}_meta.json"
            
            # 4. Save Model & Scaler
            logger.info(f"Saving model to {model_path}...")
            torch.save(model.state_dict(), model_path)
            logger.info(f"Saving scaler to {scaler_path}...")
            with open(scaler_path, 'wb') as f:
                pickle.dump(self.scaler, f)
                
            # 5. Eval (Calculate Accuracy)
            logger.info("Evaluating model on test set...")
            model.eval()
            with torch.no_grad():
                test_pred = model(X_test_tensor)
                pred_classes = torch.argmax(test_pred, dim=1)
                accuracy_val = (pred_classes == y_test_tensor).float().mean()
            logger.info(f"Test Accuracy: {accuracy_val.item():.2%}")
            
            # 6. Save Metadata
            import json
            logger.info(f"Saving metadata to {meta_path}...")
            metadata = {
                "symbol": symbol,
                "timeframe": timeframe,
                "final_loss": history['loss'][-1],
                "accuracy": accuracy_val.item(),
                "last_trained": datetime.now().isoformat(),
                "samples": len(X),
                "model_type": "Meta-LSTM"
            }
            with open(meta_path, 'w') as f:
                json.dump(metadata, f)
            
            logger.info(f"✓ Training completed for {symbol}! Final loss: {history['loss'][-1]:.4f}, Accuracy: {accuracy_val.item():.2%}")

            return {
                "status": "success",
                "model_path": model_path,
                "csv_path": csv_path,
                "final_loss": history['loss'][-1],
                "test_accuracy": accuracy_val.item()
            }
            
        except Exception as e:
            logger.error(f"Error training: {e}")
            logger.error(traceback.format_exc())
            raise e

    def predict(self, symbol: str, timeframe: str, candles: List[Dict]) -> Dict[str, Any]:
        """
        Predice la estrategia ganadora para el momento actual.
        """
        try:
            # 1. Load Model & Scaler
            safe_symbol = symbol.replace('/', '_')
            # Intentar cargar modelo específico, sino fallback a GLOBAL
            model_name = f"{safe_symbol}_{timeframe}"
            model_path = f"{self.models_dir}/{model_name}_lstm.pth"
            scaler_path = f"{self.models_dir}/{model_name}_scaler.pkl"
            
            if not os.path.exists(model_path):
                 # Fallback to GLOBAL model
                 model_name = f"GLOBAL_{timeframe}"
                 model_path = f"{self.models_dir}/{model_name}_lstm.pth"
                 scaler_path = f"{self.models_dir}/{model_name}_scaler.pkl"
                 if not os.path.exists(model_path):
                     raise FileNotFoundError(f"Model not found for {symbol} or GLOBAL")

            # Load Scaler
            with open(scaler_path, 'rb') as f:
                self.scaler = pickle.load(f) # Ensure scaler is loaded
                
            # 2. Prepare Data
            df = pd.DataFrame(candles)
            if df.empty: raise ValueError("No candles provided")
            
            # Features
            # IMPORTANT: fit=False to use loaded scaler parameters
            df_features = self._prepare_features(df.copy(), fit=False)
            
            # Need at least seq_length recent rows
            if len(df_features) < self.seq_length:
                raise ValueError(f"Not enough data for features. Need {self.seq_length}, got {len(df_features)}")
                
            # Extract last sequence
            input_seq = df_features.values[-self.seq_length:]
            
            # 3. Model Inference
            model = LSTMModel(self.input_dim, self.hidden_dim, self.num_layers, output_dim=4)
            model.load_state_dict(torch.load(model_path))
            model.eval()
            
            input_tensor = torch.from_numpy(input_seq).float().unsqueeze(0) # Batch size 1
            
            with torch.no_grad():
                output = model(input_tensor)
                probs = torch.softmax(output, dim=1).numpy()[0]
                pred_class = np.argmax(probs)
                
            # Map class to strategy
            _, strategies_list = load_strategies()
            strategies_names = ["HOLD"] + [s.name for s in strategies_list]
            
            # Safety check if model has different dim than current strategies
            if pred_class >= len(strategies_names):
                strategy_name = "UNKNOWN_STRATEGY"
            else:
                strategy_name = strategies_names[pred_class]
            
            return {
                "symbol": symbol,
                "strategy_selected": strategy_name,
# ... (existing predict method)
                "confidence": float(probs[pred_class]),
                "class_probabilities": probs.tolist(),
                "decision": "HOLD" if pred_class == 0 else "BUY/SELL (Check Strategy)",
                "used_model": model_name
            }
            
        except Exception as e:
            logger.error(f"Error predicting: {e}")
            raise e

    def predict_batch(self, symbol: str, timeframe: str, candles: List[Dict], model_name: str = None) -> List[Dict[str, Any]]:
        """
        Realiza predicciones en lote para una serie histórica de velas.
        Optimizado para Backtesting.
        """
        try:
            # 1. Load Model (Cached)
            # Logic: If model_name provided, try it. Else construct from symbol.
            # If fail, fallback to GLOBAL.
            
            target_model = model_name
            if not target_model:
                safe_symbol = symbol.replace('/', '_')
                target_model = f"{safe_symbol}_{timeframe}"
            
            # Intentar cargar
            try:
                model, scaler, meta = self._load_model_artifacts(target_model)
            except FileNotFoundError:
                 # Fallback to GLOBAL
                 # Per user request: "usar global... si no coincide"
                 target_model = f"GLOBAL_{timeframe}"
                 try:
                    model, scaler, meta = self._load_model_artifacts(target_model)
                 except FileNotFoundError:
                    logger.warning(f"Neither specified model nor Global model found for {symbol} {timeframe}")
                    return []

            self.scaler = scaler # Set current scaler

            # 2. Prepare Data
            df = pd.DataFrame(candles)
            if df.empty: return []

            # Features (fit=False)
            df_features = self._prepare_features(df.copy(), fit=False)
            
            if len(df_features) < self.seq_length:
                return []

            # 3. Create Sequences (Batch)
            # Vectorized sequence creation
            data = df_features.values
            num_samples = len(data) - self.seq_length + 1
            if num_samples <= 0: return []
            
            # Create sliding window view (efficient)
            # Shape: (num_samples, seq_length, input_dim)
            # Note: This might be memory intensive for huge datasets, but ok for typical backtest
            X = []
            for i in range(num_samples):
                X.append(data[i : i + self.seq_length])
            
            input_tensor = torch.from_numpy(np.array(X)).float()

            # 4. Inference
            model.eval()
            with torch.no_grad():
                outputs = model(input_tensor)
                probs = torch.softmax(outputs, dim=1).numpy()
                pred_classes = np.argmax(probs, axis=1)

            # 5. Map results to original candles
            # The first prediction corresponds to the candle at index (seq_length - 1)
            results = []
            
            _, strategies_list = load_strategies()
            strategies_names = ["HOLD"] + [s.name for s in strategies_list]
            
            # Rellenar los primeros indices con None/Hold porque no hay contexto suficiente
            for _ in range(self.seq_length - 1):
                results.append({
                    "strategy": "HOLD",
                    "confidence": 0.0,
                    "action": "HOLD"
                })

            for i, pred_class in enumerate(pred_classes):
                if pred_class < len(strategies_names):
                    strategy_name = strategies_names[pred_class]
                else:
                    strategy_name = "UNKNOWN"
                confidence = float(probs[i][pred_class])
                
                results.append({
                    "strategy": strategy_name,
                    "confidence": confidence,
                    "action": "HOLD" if pred_class == 0 else "CHECK_SIGNAL"
                })
            
            # Verify alignment
            if len(results) < len(candles):
                # Pad remaining missing candles caused by dropping NaNs in features
                missing = len(candles) - len(results)
                padding = [{
                    "strategy": "HOLD",
                    "confidence": 0.0,
                    "action": "HOLD"
                }] * missing
                results = padding + results
            
            return results

        except Exception as e:
            logger.error(f"Error in predict_batch: {e}")
            # Return empty list on error to avoid crashing flow, let service handle
            return []

    @lru_cache(maxsize=10)
    def _load_model_artifacts(self, model_prefix: str):
        """Carga modelo, scaler y metadata con caché LRU"""
        model_path = f"{self.models_dir}/{model_prefix}_lstm.pth"
        scaler_path = f"{self.models_dir}/{model_prefix}_scaler.pkl"
        
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model {model_prefix} not found")
            
        # Load Model
        # Load Model with current dynamic output dimension
        model = LSTMModel(self.input_dim, self.hidden_dim, self.num_layers, output_dim=self.output_dim)
        try:
            model.load_state_dict(torch.load(model_path))
        except RuntimeError as e:
            if "size mismatch" in str(e):
                logger.error(f"Model dimension mismatch. The model was trained with fewer/different strategies. PLEASE RETRAIN.")
                raise ValueError(f"Model architecture mismatch (Strategies changed?). Please retrain the model for {model_prefix}.")
            raise e
        model.eval()
        
        # Load Scaler
        with open(scaler_path, 'rb') as f:
            scaler = pickle.load(f)
            
        return model, scaler, {}


    async def get_models_status(self) -> List[Dict[str, Any]]:
        loop = asyncio.get_running_loop()
        
        def _read_models_sync():
            models = []
            try:
                if not os.path.exists(self.models_dir):
                    return []
                
                import json
                files = os.listdir(self.models_dir)
                
                for f in files:
                    if f.endswith("_meta.json"):
                        try:
                            file_path = os.path.join(self.models_dir, f)
                            with open(file_path, 'r') as meta_file:
                                data = json.load(meta_file)
                                if not isinstance(data, dict):
                                    continue
                                    
                                def safe_val(val):
                                    if val is None: return 0.0
                                    try:
                                        f = float(val)
                                        if np.isnan(f) or np.isinf(f): return 0.0
                                        return f
                                    except:
                                        return 0.0

                                models.append({
                                    "id": f.replace("_meta.json", ""),
                                    "symbol": data.get("symbol", "Unknown"),
                                    "timeframe": data.get("timeframe", "1h"),
                                    "status": "Ready",
                                    "last_trained": data.get("last_trained"),
                                    "accuracy": safe_val(data.get("accuracy", 0)),
                                    "final_loss": safe_val(data.get("final_loss", 0)),
                                    "model_type": data.get("model_type", "LSTM")
                                })
                        except Exception as e:
                            logger.error(f"Error reading meta {f}: {e}")
                            continue
                return models
            except Exception as e:
                logger.error(f"Error in _read_models_sync: {e}")
                return []

        try:
            return await loop.run_in_executor(None, _read_models_sync)
        except Exception as e:
            logger.error(f"Error getting models status: {e}")
            logger.error(traceback.format_exc())
            return []
