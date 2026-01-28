import pandas as pd
import numpy as np
import logging
from api.strategies.rsi_reversion import RSIReversion
from api.strategies.trend_ema import TrendEMA
from api.strategies.volatility_breakout import VolatilityBreakout
from api.strategies import load_strategies
from api.utils.indicators import rsi, adx, atr, bollinger_bands

logger = logging.getLogger(__name__)

class StrategyTrainer:
    def __init__(self, data: pd.DataFrame, initial_balance: float = 10000.0, use_virtual_balance: bool = True):
        self.data = data
        _, self.strategies = load_strategies()
        # Map IDs: 1..N based on sorted order. 0=Hold
        # Map IDs: 1=RSI, 2=EMA, 3=Breakout. 0=Hold (default if no profit)
        
        # Virtual Balance Management
        self.use_virtual_balance = use_virtual_balance
        self.initial_balance = initial_balance
        self.virtual_balance = initial_balance  # Current cash balance
        self.position_size = 0  # Current position (in base currency)
        self.position_entry_price = 0  # Entry price of current position

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

    def _execute_virtual_trade(self, signal: str, entry_price: float, exit_price: float, fee: float = 0.001) -> float:
        """
        Simula ejecución de trade usando balance virtual.
        Retorna PnL realizado.
        """
        if not self.use_virtual_balance:
            # Fallback to simple PnL calculation
            if signal == 'buy':
                raw_pnl = (exit_price - entry_price) / entry_price
                return raw_pnl - (fee * 2)
            elif signal == 'sell':
                raw_pnl = (entry_price - exit_price) / entry_price
                return raw_pnl - (fee * 2)
            return 0
        
        # Virtual balance tracking
        pnl = 0
        
        if signal == 'buy':
            # Open long position or accumulate
            # Use 95% of balance to leave margin for fees
            trade_amount = self.virtual_balance * 0.95
            fee_cost = trade_amount * fee
            position_value = trade_amount - fee_cost
            self.position_size = position_value / entry_price
            self.position_entry_price = entry_price
            self.virtual_balance -= trade_amount
            
            # Close position at exit
            exit_value = self.position_size * exit_price
            exit_fee = exit_value * fee
            realized_value = exit_value - exit_fee
            self.virtual_balance += realized_value
            
            # Calculate PnL
            pnl = (realized_value - position_value) / position_value
            
            # Reset position
            self.position_size = 0
            self.position_entry_price = 0
            
        elif signal == 'sell':
            # Short selling (simplified: assume we can borrow)
            trade_amount = self.virtual_balance * 0.95
            fee_cost = trade_amount * fee
            position_value = trade_amount - fee_cost
            self.position_size = position_value / entry_price  # Borrowed amount
            self.position_entry_price = entry_price
            self.virtual_balance += position_value  # Receive cash from short
            
            # Close short at exit
            buyback_cost = self.position_size * exit_price
            buyback_fee = buyback_cost * fee
            total_cost = buyback_cost + buyback_fee
            self.virtual_balance -= total_cost
            
            # Calculate PnL
            pnl = (position_value - buyback_cost) / position_value
            
            # Reset position
            self.position_size = 0
            self.position_entry_price = 0
        
        # Check if balance is depleted
        if self.virtual_balance <= 0:
            self.virtual_balance = 0
            return -1.0  # Total loss
        
        return pnl
    
    def generate_labeled_dataset(self, window_size=60, forecast_horizon=12) -> pd.DataFrame:
        """
        Analiza bloques de datos y determina qué estrategia fue más rentable.
        Retorna DataFrame con Features y Label (best_strategy).
        Usa virtual_balance para simular trading realista.
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
                    # Reset virtual balance for each strategy test
                    self.virtual_balance = self.initial_balance
                    self.position_size = 0
                    self.position_entry_price = 0
                    
                    # Create position context (empty for training simplicity)
                    position_context = {
                        'has_position': False,
                        'position_type': None,
                        'avg_entry_price': 0,
                        'current_price': entry_price,
                        'unrealized_pnl_pct': 0,
                        'position_count': 0
                    }
                    
                    # Get signal with position context
                    res = strat.get_signal(window_slice, position_context)
                    signal = res.get('signal')
                    
                    # Execute virtual trade
                    pnl = self._execute_virtual_trade(signal, entry_price, exit_price, fee)
                    
                    perf_map[strat_id + 1] = pnl
                except Exception as e:
                    logger.debug(f"Strategy {strat_id} failed: {e}")
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
            # Use actual timestamp from original data
            row_feats['timestamp'] = self.data.loc[current_time_idx, 'timestamp']
            
            results.append(row_feats)
            
        return pd.DataFrame(results)
