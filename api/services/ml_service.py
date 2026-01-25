import torch
import torch.nn as nn
import torch.optim as optim
import pandas as pd
import numpy as np
import os
import logging
import pickle
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple

# No external ML libs to avoid dependency hell on Python 3.14
# from sklearn.preprocessing import MinMaxScaler 
# import joblib 

from api.ml.models.lstm_model import LSTMModel
from api.services.cex_service import CEXService
from api.config import Config
from api.strategies import RSIReversion, TrendEMA, VolatilityBreakout
from api.utils.indicators import rsi, adx, atr, bollinger_bands, ema
from api.ml.strategy_trainer import StrategyTrainer
from api.services.ccxt_service import ccxt_service
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
        self.output_dim = 3   # 3 Strategies (Classes)
        
        self.scaler = SimpleScaler()

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

    def _create_sequences(self, df_features: pd.DataFrame, df_raw: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Genera dataset para el Meta-Selector:
        X: Features normalizados (rsi, adx...) de la ventana t-N...t
        y: ID de la Estrategia Ganadora en el futuro (t...t+Horizon)
        """
        data = df_features.values
        X, y = [], []
        
        # Estrategias disponibles para el "Torneo"
        strategies = [
            RSIReversion(),
            TrendEMA(),
            VolatilityBreakout()
        ]
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
             
        
        all_X = []
        all_y = []
        
        processed_count = 0
        
        for symbol in symbols:
            try:
                # 1. Fetch Data
                # Call new CCXTService method
                all_ohlcv = await ccxt_service.get_historical_ohlcv(
                    symbol=symbol, 
                    exchange_id=target_exchange_id, 
                    timeframe=timeframe, 
                    days_back=days
                )

                if len(all_ohlcv) < 500:
                    logger.warning(f"Skipping {symbol}: Not enough data")
                    continue
                    
                df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df.drop_duplicates(subset=['timestamp'], inplace=True)
                df.sort_values('timestamp', inplace=True)
                df.reset_index(drop=True, inplace=True)
                
                # 2. Generate Labeled Dataset
                trainer = StrategyTrainer(df)
                labeled_df = trainer.generate_labeled_dataset(window_size=60, forecast_horizon=12)
                
                if labeled_df.empty: 
                    continue
                    
                # Save individual CSV (optional but good for debugging)
                safe_symbol = symbol.replace('/', '_')
                csv_path = f"{self.datasets_dir}/{safe_symbol}_{timeframe}_labeled.csv"
                labeled_df.to_csv(csv_path, index=False)
                
                # 3. Create Sequences
                X, y = self._create_sequences_from_csv(labeled_df)
                if len(X) > 0:
                    all_X.append(X)
                    all_y.append(y)
                    processed_count += 1
                    logger.info(f"Processed {symbol}: {len(X)} samples")
                    
            except Exception as e:
                logger.error(f"Error processing {symbol} for global model: {e}")
                continue
                
        if processed_count == 0:
            raise Exception("No data available for global training")
            
        # 4. Concatenate All Data
        X_global = np.concatenate(all_X, axis=0)
        y_global = np.concatenate(all_y, axis=0)
        
        logger.info(f"Global Dataset Size: {len(X_global)} samples")
        
        # 5. Train Global Model
        train_size = int(len(X_global) * 0.8)
        X_train, X_test = X_global[:train_size], X_global[train_size:]
        y_train, y_test = y_global[:train_size], y_global[train_size:]
        
        X_train_tensor = torch.from_numpy(X_train).float()
        y_train_tensor = torch.from_numpy(y_train).long()
        X_test_tensor = torch.from_numpy(X_test).float()
        y_test_tensor = torch.from_numpy(y_test).long()
        
        model = LSTMModel(self.input_dim, self.hidden_dim, self.num_layers, output_dim=4)
        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(model.parameters(), lr=0.001)
        
        model.train()
        history = {'loss': []}
        
        for epoch in range(epochs):
            optimizer.zero_grad()
            output = model(X_train_tensor)
            loss = criterion(output, y_train_tensor)
            loss.backward()
            optimizer.step()
            history['loss'].append(loss.item())
            
        # 6. Save Global Model
        # Use "GLOBAL" as symbol name
        model_name = f"GLOBAL_{timeframe}"
        model_path = f"{self.models_dir}/{model_name}_lstm.pth"
        scaler_path = f"{self.models_dir}/{model_name}_scaler.pkl"
        meta_path = f"{self.models_dir}/{model_name}_meta.json"
        
        torch.save(model.state_dict(), model_path)
        with open(scaler_path, 'wb') as f:
            pickle.dump(self.scaler, f)
            
        # Calc Accuracy
        model.eval()
        with torch.no_grad():
            test_pred = model(X_test_tensor)
            pred_classes = torch.argmax(test_pred, dim=1)
            accuracy_val = (pred_classes == y_test_tensor).float().mean()
            
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
            
            # 1. Generate Labeled Dataset (Using StrategyTrainer)
            trainer = StrategyTrainer(df)
            labeled_df = trainer.generate_labeled_dataset(window_size=60, forecast_horizon=12)
            
            if labeled_df.empty: raise Exception("StrategyTrainer generated 0 samples")
            
            # Save CSV
            safe_symbol = symbol.replace('/', '_')
            csv_path = f"{self.datasets_dir}/{safe_symbol}_{timeframe}_labeled.csv"
            labeled_df.to_csv(csv_path, index=False)
            logger.info(f"Saved labeled dataset to {csv_path}")
            
            # 2. Train from CSV Data
            X, y = self._create_sequences_from_csv(labeled_df)
            
            if len(X) == 0: raise Exception("No sequences generated")
            
            train_size = int(len(X) * 0.8)
            X_train, X_test = X[:train_size], X[train_size:]
            y_train, y_test = y[:train_size], y[train_size:]
            
            X_train_tensor = torch.from_numpy(X_train).float()
            y_train_tensor = torch.from_numpy(y_train).long()
            X_test_tensor = torch.from_numpy(X_test).float()
            y_test_tensor = torch.from_numpy(y_test).long()
            
            # 3. Model
            model = LSTMModel(self.input_dim, self.hidden_dim, self.num_layers, output_dim=4)
            criterion = nn.CrossEntropyLoss()
            optimizer = optim.Adam(model.parameters(), lr=0.001)
            
            model.train()
            history = {'loss': []}
            
            for epoch in range(epochs):
                optimizer.zero_grad()
                output = model(X_train_tensor)
                loss = criterion(output, y_train_tensor)
                loss.backward()
                optimizer.step()
                history['loss'].append(loss.item())
            
            # 4. Save
            model_path = f"{self.models_dir}/{safe_symbol}_{timeframe}_lstm.pth"
            scaler_path = f"{self.models_dir}/{safe_symbol}_{timeframe}_scaler.pkl"
            meta_path = f"{self.models_dir}/{safe_symbol}_{timeframe}_meta.json"
            
            # 4. Save Model & Scaler
            torch.save(model.state_dict(), model_path)
            with open(scaler_path, 'wb') as f:
                pickle.dump(self.scaler, f)
                
            # 5. Eval (Calculate Accuracy)
            model.eval()
            with torch.no_grad():
                test_pred = model(X_test_tensor)
                pred_classes = torch.argmax(test_pred, dim=1)
                accuracy_val = (pred_classes == y_test_tensor).float().mean()
            
            # 6. Save Metadata
            import json
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

            return {
                "status": "success",
                "model_path": model_path,
                "csv_path": csv_path,
                "final_loss": history['loss'][-1],
                "test_accuracy": accuracy_val.item()
            }
            
        except Exception as e:
            logger.error(f"Error training: {e}")
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
            strategies = ["HOLD", "RSI_Reversion", "Trend_EMA", "Volatility_Breakout"]
            strategy_name = strategies[pred_class]
            
            return {
                "symbol": symbol,
                "strategy_selected": strategy_name,
                "confidence": float(probs[pred_class]),
                "class_probabilities": probs.tolist(),
                "decision": "HOLD" if pred_class == 0 else "BUY/SELL (Check Strategy)",
                "used_model": model_name
            }
            
        except Exception as e:
            logger.error(f"Error predicting: {e}")
            raise e

    async def get_models_status(self) -> List[Dict[str, Any]]:
        models = []
        if not os.path.exists(self.models_dir):
            return []
            
        import json
        for f in os.listdir(self.models_dir):
            if f.endswith("_meta.json"):
                try:
                    with open(os.path.join(self.models_dir, f), 'r') as meta_file:
                        data = json.load(meta_file)
                        models.append({
                            "id": f.replace("_meta.json", ""),
                            "symbol": data.get("symbol", "Unknown"),
                            "timeframe": data.get("timeframe", "1h"),
                            "status": "Ready",
                            "last_trained": data.get("last_trained"),
                            "accuracy": data.get("accuracy", 0),
                            "final_loss": data.get("final_loss", 0),
                            "model_type": data.get("model_type", "LSTM")
                        })
                except Exception as e:
                    logger.error(f"Error reading meta {f}: {e}")
                    
        return models
