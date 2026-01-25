import pandas as pd
import numpy as np
import logging
from api.strategies.rsi_reversion import RSIReversion
from api.strategies.trend_ema import TrendEMA
from api.strategies.volatility_breakout import VolatilityBreakout
from api.utils.indicators import rsi, adx, atr, bollinger_bands

logger = logging.getLogger(__name__)

class StrategyTrainer:
    def __init__(self, data: pd.DataFrame):
        self.data = data
        self.strategies = [
            RSIReversion(),
            TrendEMA(),
            VolatilityBreakout()
        ]
        # Map IDs: 1=RSI, 2=EMA, 3=Breakout. 0=Hold (default if no profit)

    def _calculate_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calcula features técnicas avanzadas para el modelo.
        Debe coincidir con la lógica de inferencia del MLService.
        """
        # Copia para no afectar original
        df = df.copy()
        
        # 1. RSI (Momentum)
        df['rsi'] = rsi(df['close'], 14) / 100.0
        
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
        
        return df

    def generate_labeled_dataset(self, window_size=60, forecast_horizon=12) -> pd.DataFrame:
        """
        Analiza bloques de datos y determina qué estrategia fue más rentable.
        Retorna DataFrame con Features y Label (best_strategy).
        """
        # Primero calculamos features vectorizados (más rápido)
        # Pero necesitamos features alignados con la ventana 'i'.
        # La feature en 'i' es lo que ve el modelo para predecir 'i -> i+horizon'.
        
        df_feat = self._calculate_features(self.data)
        # Drop NaN iniciales
        df_feat.dropna(inplace=True)
        
        # Feature columns
        feat_cols = ['rsi', 'adx', 'atr_pct', 'bb_width', 'vol_rel']
        
        results = []
        fee = 0.001
        
        # Alinear indices: df_feat es un subset le quedan menos filas.
        # Iteramos sobre el indice de df_feat
        
        # Valid loop bounds
        # i must be index in data. 
        # features at i use [i-window_size : i]? 
        # No, features at row 'i' are calculated using past data automatically by rolling/ewm.
        # So df_feat.iloc[k] contains features looking back from k.
        
        # Tournament Loop
        # Necesitamos datos futuros para calcular Profit
        
        available_indices = df_feat.index
        
        for idx in range(0, len(available_indices) - forecast_horizon):
            current_time_idx = available_indices[idx] # Timestamp index if dataframe indexed by date, or int
            
            # Necesitamos el indice entero en self.data para hacer slicing del futuro
            # Si self.data tiene integer index range es facil
            # Asumiremos integer range index si reseteamos index antes
            
            # Map back to raw data location
            raw_loc = self.data.index.get_loc(current_time_idx)
            
            # Window Data para Estrategias (Backtest real necesita velas OHLCV)
            # Estrategias necesitan ~100 velas para warmup interno (EMA)
            start_loc = raw_loc - 100
            if start_loc < 0: continue
            
            window_slice = self.data.iloc[start_loc : raw_loc + 1].copy() # +1 to force include current candle?
            # Strategy usually takes DataFrame and calculates signal based on last row
            
            # Future Data for Labeling
            future_slice = self.data.iloc[raw_loc : raw_loc + forecast_horizon + 1]
            if len(future_slice) < forecast_horizon: continue
            
            entry_price = future_slice['close'].iloc[0] # Close actual
            exit_price = future_slice['close'].iloc[-1] # Close en horizon
            
            perf_map = {}
            for strat_id, strat in enumerate(self.strategies): # 0=RSI, 1=EMA... (IDs 1,2,3)
                try:
                    res = strat.get_signal(window_slice)
                    signal = res.get('signal')
                    
                    pnl = 0
                    if signal == 'buy':
                        raw_pnl = (exit_price - entry_price) / entry_price
                        pnl = raw_pnl - (fee * 2) 
                    elif signal == 'sell':
                        raw_pnl = (entry_price - exit_price) / entry_price
                        pnl = raw_pnl - (fee * 2)
                        
                    perf_map[strat_id + 1] = pnl
                except:
                    perf_map[strat_id + 1] = -1.0

            # Determine winner
            # Default Winner: 0 (Hold)
            best_strat_id = 0
            best_pnl = 0.002 # Min threshold
            
            if perf_map:
                winner_id = max(perf_map, key=perf_map.get)
                winner_pnl = perf_map[winner_id]
                if winner_pnl > best_pnl:
                    best_strat_id = winner_id
            
            # Extract features for this row
            row_feats = df_feat.loc[current_time_idx, feat_cols].to_dict()
            row_feats['label'] = best_strat_id
            row_feats['timestamp'] = current_time_idx
            
            results.append(row_feats)
            
        return pd.DataFrame(results)
