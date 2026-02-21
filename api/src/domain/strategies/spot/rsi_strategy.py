import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from api.src.domain.strategies.base import BaseStrategy

class RSIStrategy(BaseStrategy):
    """
    RSI Strategy v2.0 - Optimized
    
    Compra en sobreventa y vende en sobrecompra con filtros avanzados.
    
    Mejoras aplicadas:
    - RSI suavizado para reducir falsas señales
    - Divergencias RSI-precio (early warning)
    - Filtro de tendencia (EMA 50/200)
    - Zonas dinámicas (30/70 → 25/75 en tendencia fuerte)
    - Tick handler con detección de reversión por spike
    """
    
    def __init__(self, config=None):
        super().__init__(config or {})
        self.period = int(self.config.get('period', 14))
        self.lower_base = float(self.config.get('lower_base', 30))
        self.upper_base = float(self.config.get('upper_base', 70))
        self.ema_fast = int(self.config.get('ema_fast', 50))
        self.ema_slow = int(self.config.get('ema_slow', 200))
        self.divergence_lookback = int(self.config.get('divergence_lookback', 5))

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        if len(df) < self.ema_slow:
            df['signal'] = self.SIGNAL_WAIT
            return df

        # 1. RSI calculation (vectorizado)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
        rs = gain / (loss + 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 2. RSI suavizado (menos ruido)
        df['rsi_smooth'] = df['rsi'].ewm(span=3, adjust=False).mean()
        
        # 3. Filtro de tendencia
        df['ema_50'] = df['close'].ewm(span=self.ema_fast, adjust=False).mean()
        df['ema_200'] = df['close'].ewm(span=self.ema_slow, adjust=False).mean()
        # Vectorizado: 1 si precio > ema, -1 si menor
        df['trend'] = np.where(df['close'] > df['ema_200'], 1, -1)
        
        # 4. Zonas dinámicas (ajustar según tendencia)
        # En tendencia alcista: sobreventa más agresiva (35), sobrecompra más estricta (75)
        # En tendencia bajista: sobrecompra más agresiva (65), sobreventa más estricta (25)
        df['lower_zone'] = np.where(df['trend'] == 1, self.lower_base - 5, self.lower_base)
        df['upper_zone'] = np.where(df['trend'] == -1, self.upper_base + 5, self.upper_base)
        
        # 5. Divergencias (feature avanzada)
        # Divergencia alcista: precio hace mínimo más bajo, RSI hace mínimo más alto
        df['price_min'] = df['close'].rolling(self.divergence_lookback).min()
        df['price_min_prev'] = df['price_min'].shift(1)
        df['rsi_min'] = df['rsi'].rolling(self.divergence_lookback).min()
        df['rsi_min_prev'] = df['rsi_min'].shift(1)
        df['bull_div'] = (df['close'] < df['price_min_prev']) & (df['rsi'] > df['rsi_min_prev'])
        
        # Divergencia bajista: precio hace máximo más alto, RSI hace máximo más bajo
        df['price_max'] = df['close'].rolling(self.divergence_lookback).max()
        df['price_max_prev'] = df['price_max'].shift(1)
        df['rsi_max'] = df['rsi'].rolling(self.divergence_lookback).max()
        df['rsi_max_prev'] = df['rsi_max'].shift(1)
        df['bear_div'] = (df['close'] > df['price_max_prev']) & (df['rsi'] < df['rsi_max_prev'])

        df['signal'] = self.SIGNAL_WAIT
        
        # COMPRA: RSI < zona inferior + (divergencia alcista O salida de sobreventa)
        buy_oversold = df['rsi'] < df['lower_zone']
        buy_exit = (df['rsi'] > df['lower_zone']) & (df['rsi'].shift(1) <= df['lower_zone'])
        df.loc[(buy_oversold | buy_exit) & (df['bull_div'] | (df['trend'] >= 0)), 'signal'] = self.SIGNAL_BUY
        
        # VENTA: RSI > zona superior + (divergencia bajista O entrada en sobrecompra)
        sell_overbought = df['rsi'] > df['upper_zone']
        sell_entry = (df['rsi'] < df['upper_zone']) & (df['rsi'].shift(1) >= df['upper_zone'])
        df.loc[(sell_overbought | sell_entry) & (df['bear_div'] | (df['trend'] <= 0)), 'signal'] = self.SIGNAL_SELL

        return df

    def on_price_tick(self, price: float, current_position: dict = None, context: dict = None) -> int:
        """
        Tick rápido RSI: reversión por spike extremo.
        """
        if price is None or price <= 0:
            return self.SIGNAL_WAIT

        ctx = context or {}
        prev_price = float(ctx.get("prev_price") or 0)
        if prev_price <= 0:
            return self.SIGNAL_WAIT

        change = (float(price) - prev_price) / prev_price
        spike = float(self.config.get("tick_rsi_spike_pct", 0.5)) / 100.0

        # Reversión: spike negativo fuerte → BUY, spike positivo fuerte → SELL
        if change <= -spike:
            return self.SIGNAL_BUY
        if change >= spike:
            return self.SIGNAL_SELL
            
        return self.SIGNAL_WAIT

    def get_features(self) -> List[str]:
        return ['rsi', 'rsi_smooth', 'bull_div', 'bear_div']
