import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from api.src.domain.strategies.base import BaseStrategy

class MACDStrategy(BaseStrategy):
    """
    MACD Strategy v2.0 - Optimized
    
    Sigue la inercia del precio con confirmación de histograma y tendencia.
    
    Mejoras aplicadas:
    - Histograma como señal primaria (más sensible que cruces)
    - Filtro de tendencia (EMA 200)
    - Filtro de volumen para confirmación
    - Divergencias MACD-precio
    - Zero-line cross como confirmación secundaria
    """
    
    def __init__(self, config=None):
        super().__init__(config or {})
        self.fast = int(self.config.get('fast', 12))
        self.slow = int(self.config.get('slow', 26))
        self.signal_smooth = int(self.config.get('signal', 9))
        self.ema_trend = int(self.config.get('ema_trend', 200))
        self.vol_ma = int(self.config.get('vol_ma', 20))

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        if len(df) < self.ema_trend:
            df['signal'] = self.SIGNAL_WAIT
            return df

        # 1. MACD calculation
        exp1 = df['close'].ewm(span=self.fast, adjust=False).mean()
        exp2 = df['close'].ewm(span=self.slow, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=self.signal_smooth, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # 2. Histograma normalizado (para ML)
        df['macd_hist_norm'] = (df['macd_hist'] - df['macd_hist'].rolling(50).min()) / \
                               (df['macd_hist'].rolling(50).max() - df['macd_hist'].rolling(50).min() + 1e-9)
        
        # 3. Filtro de tendencia
        df['ema_200'] = df['close'].ewm(span=self.ema_trend, adjust=False).mean()
        df['trend'] = 1 if df['close'].iloc[-1] > df['ema_200'].iloc[-1] else -1
        
        # 4. Filtro de volumen
        df['vol_ma'] = df['volume'].rolling(window=self.vol_ma).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma']
        
        # 5. Divergencias
        # Divergencia alcista: precio mínimo más bajo, MACD mínimo más alto
        lookback = 5
        df['price_min'] = df['close'].rolling(lookback).min()
        df['macd_min'] = df['macd'].rolling(lookback).min()
        df['bull_div'] = (df['close'] < df['price_min'].shift(1)) & (df['macd'] > df['macd_min'].shift(1))
        
        # Divergencia bajista: precio máximo más alto, MACD máximo más bajo
        df['price_max'] = df['close'].rolling(lookback).max()
        df['macd_max'] = df['macd'].rolling(lookback).max()
        df['bear_div'] = (df['close'] > df['price_max'].shift(1)) & (df['macd'] < df['macd_max'].shift(1))
        
        # 6. Zero-line cross (confirmación)
        df['zero_cross_up'] = (df['macd'] > 0) & (df['macd'].shift(1) <= 0)
        df['zero_cross_down'] = (df['macd'] < 0) & (df['macd'].shift(1) >= 0)

        df['signal'] = self.SIGNAL_WAIT
        
        # COMPRA: Histograma gira al alza + (divergencia O zero-cross) + volumen
        hist_turn_up = df['macd_hist'] > df['macd_hist'].shift(1)
        hist_was_down = df['macd_hist'].shift(1) < df['macd_hist'].shift(2)
        buy_vol = df['vol_ratio'] > 0.8
        
        df.loc[hist_turn_up & hist_was_down & buy_vol & 
               (df['bull_div'] | df['zero_cross_up'] | (df['trend'] >= 0)), 'signal'] = self.SIGNAL_BUY

        # VENTA: Histograma gira a la baja + (divergencia O zero-cross) + volumen
        hist_turn_down = df['macd_hist'] < df['macd_hist'].shift(1)
        hist_was_up = df['macd_hist'].shift(1) > df['macd_hist'].shift(2)
        sell_vol = df['vol_ratio'] > 0.8
        
        df.loc[hist_turn_down & hist_was_up & sell_vol & 
               (df['bear_div'] | df['zero_cross_down'] | (df['trend'] <= 0)), 'signal'] = self.SIGNAL_SELL

        return df

    def on_price_tick(self, price: float, current_position: dict = None, context: dict = None) -> int:
        """
        Tick intravela: detector de continuación de momentum.
        """
        if price is None or price <= 0:
            return self.SIGNAL_WAIT

        ctx = context or {}
        prev_price = float(ctx.get("prev_price") or 0)
        if prev_price <= 0:
            return self.SIGNAL_WAIT

        change = (float(price) - prev_price) / prev_price
        trigger = float(self.config.get("tick_macd_trigger_pct", 0.4)) / 100.0

        # Si ya hay posición, esperar
        if current_position and float(current_position.get("qty", 0) or 0) > 0:
            return self.SIGNAL_WAIT

        if change >= trigger:
            return self.SIGNAL_BUY
        if change <= -trigger:
            return self.SIGNAL_SELL
            
        return self.SIGNAL_WAIT

    def get_features(self) -> List[str]:
        return ['macd', 'macd_signal', 'macd_hist', 'macd_hist_norm', 'bull_div', 'bear_div']
