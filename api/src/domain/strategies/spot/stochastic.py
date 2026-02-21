import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from api.src.domain.strategies.base import BaseStrategy

class StochasticStrategy(BaseStrategy):
    """
    Stochastic Strategy v2.0 - Optimized
    
    Identifica puntos de giro con %K/%D y filtros de confirmación.
    
    Mejoras aplicadas:
    - Zonas dinámicas (20/80 → ajustables por tendencia)
    - Filtro de tendencia (EMA 50/200)
    - Cruce confirmado (requiere 2 velas de confirmación)
    - Filtro de volumen
    - Divergencias estocásticas
    """
    
    def __init__(self, config=None):
        super().__init__(config or {})
        self.k_period = int(self.config.get('k_period', 14))
        self.d_period = int(self.config.get('d_period', 3))
        self.oversold = float(self.config.get('oversold', 20))
        self.overbought = float(self.config.get('overbought', 80))
        self.ema_trend = int(self.config.get('ema_trend', 200))
        self.vol_ma = int(self.config.get('vol_ma', 20))

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        if len(df) < self.ema_trend:
            df['signal'] = self.SIGNAL_WAIT
            return df

        # 1. Stochastic calculation
        low_min = df['low'].rolling(window=self.k_period).min()
        high_max = df['high'].rolling(window=self.k_period).max()
        df['stoch_k'] = 100 * ((df['close'] - low_min) / (high_max - low_min + 1e-10))
        df['stoch_d'] = df['stoch_k'].rolling(window=self.d_period).mean()
        
        # 2. Stochastic suavizado
        df['stoch_k_smooth'] = df['stoch_k'].ewm(span=2, adjust=False).mean()
        df['stoch_d_smooth'] = df['stoch_d'].ewm(span=2, adjust=False).mean()
        
        # 3. Filtro de tendencia
        df['ema_200'] = df['close'].ewm(span=self.ema_trend, adjust=False).mean()
        # Vectorizado: 1 si precio > ema, -1 si menor
        df['trend'] = np.where(df['close'] > df['ema_200'], 1, -1)
        
        # 4. Zonas dinámicas
        # En tendencia alcista: sobreventa más agresiva (25), sobrecompra más estricta (85)
        df['oversold_zone'] = np.where(df['trend'] == 1, self.oversold + 5, self.oversold)
        df['overbought_zone'] = np.where(df['trend'] == -1, self.overbought - 5, self.overbought)
        
        # 5. Filtro de volumen
        df['vol_ma'] = df['volume'].rolling(window=self.vol_ma).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma']
        
        # 6. Divergencias
        lookback = 5
        df['price_min'] = df['close'].rolling(lookback).min()
        df['stoch_min'] = df['stoch_k'].rolling(lookback).min()
        df['bull_div'] = (df['close'] < df['price_min'].shift(1)) & (df['stoch_k'] > df['stoch_min'].shift(1))
        
        df['price_max'] = df['close'].rolling(lookback).max()
        df['stoch_max'] = df['stoch_k'].rolling(lookback).max()
        df['bear_div'] = (df['close'] > df['price_max'].shift(1)) & (df['stoch_k'] < df['stoch_max'].shift(1))
        
        # 7. Cruce confirmado (requiere 2 velas)
        df['cross_up'] = (df['stoch_k'] > df['stoch_d']) & (df['stoch_k'].shift(1) <= df['stoch_d'].shift(1))
        df['cross_down'] = (df['stoch_k'] < df['stoch_d']) & (df['stoch_k'].shift(1) >= df['stoch_d'].shift(1))
        df['cross_up_confirmed'] = df['cross_up'] | (df['cross_up'].shift(1) & (df['stoch_k'] > df['stoch_d']))
        df['cross_down_confirmed'] = df['cross_down'] | (df['cross_down'].shift(1) & (df['stoch_k'] < df['stoch_d']))

        df['signal'] = self.SIGNAL_WAIT
        
        # COMPRA: Cruce alcista confirmado + zona de sobreventa + (divergencia O tendencia favorable)
        buy_zone = df['stoch_k'] < df['oversold_zone']
        buy_cond = buy_zone & df['cross_up_confirmed'] & (df['vol_ratio'] > 0.8)
        df.loc[buy_cond & (df['bull_div'] | (df['trend'] >= 0)), 'signal'] = self.SIGNAL_BUY

        # VENTA: Cruce bajista confirmado + zona de sobrecompra + (divergencia O tendencia favorable)
        sell_zone = df['stoch_k'] > df['overbought_zone']
        sell_cond = sell_zone & df['cross_down_confirmed'] & (df['vol_ratio'] > 0.8)
        df.loc[sell_cond & (df['bear_div'] | (df['trend'] <= 0)), 'signal'] = self.SIGNAL_SELL

        return df

    def on_price_tick(self, price: float, current_position: dict = None, context: dict = None) -> int:
        """
        Tick intravela: detector de giro rápido.
        """
        if price is None or price <= 0:
            return self.SIGNAL_WAIT

        ctx = context or {}
        prev_price = float(ctx.get("prev_price") or 0)
        if prev_price <= 0:
            return self.SIGNAL_WAIT

        change = (float(price) - prev_price) / prev_price
        trigger = float(self.config.get("tick_stoch_trigger_pct", 0.5)) / 100.0

        if current_position and float(current_position.get("qty", 0) or 0) > 0:
            return self.SIGNAL_WAIT

        # Reversión por spike
        if change <= -trigger:
            return self.SIGNAL_BUY
        if change >= trigger:
            return self.SIGNAL_SELL
            
        return self.SIGNAL_WAIT

    def get_features(self) -> List[str]:
        return ['stoch_k', 'stoch_d', 'stoch_k_smooth', 'stoch_d_smooth', 'bull_div', 'bear_div']
