import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from api.src.domain.strategies.base import BaseStrategy

class VolatilityBreakout(BaseStrategy):
    """
    Volatility Breakout Strategy v2.0 - Optimized
    
    Ruptura basada en canales de volatilidad y ATR con filtros avanzados.
    
    Mejoras aplicadas:
    - Canales dinámicos (ajuste por ATR)
    - ATR expansion/contraction
    - Squeeze detection (baja volatilidad → explosión)
    - Filtro de tendencia (ADX)
    - Volumen para confirmación
    - Pullback post-ruptura
    """
    
    def __init__(self, config=None):
        super().__init__(config or {})
        self.period = int(self.config.get('period', 20))
        self.atr_period = int(self.config.get('atr_period', 14))
        self.atr_multiplier = float(self.config.get('atr_multiplier', 2.0))
        self.adx_period = int(self.config.get('adx_period', 14))
        self.vol_ma = int(self.config.get('vol_ma', 20))
        self.adx_threshold = float(self.config.get('adx_threshold', 20))
        self.squeeze_threshold = float(self.config.get('squeeze_threshold', 0.05))

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        if len(df) < self.period + self.adx_period:
            df['signal'] = self.SIGNAL_WAIT
            return df

        # 1. Canales de volatilidad
        df['upper_channel'] = df['high'].rolling(window=self.period).max()
        df['lower_channel'] = df['low'].rolling(window=self.period).min()
        df['channel_mid'] = (df['upper_channel'] + df['lower_channel']) / 2
        
        # 2. Posición en el canal
        df['channel_position'] = (df['close'] - df['lower_channel']) / \
                                 (df['upper_channel'] - df['lower_channel'] + 1e-10)
        
        # 3. ATR
        df['tr'] = pd.concat([df['high'] - df['low'], 
                             (df['high'] - df['close'].shift()).abs(), 
                             (df['low'] - df['close'].shift()).abs()], axis=1).max(axis=1)
        df['atr'] = df['tr'].rolling(window=self.atr_period).mean()
        df['atr_pct'] = df['atr'] / df['close'] * 100
        
        # 4. ATR bands (canales dinámicos)
        df['atr_upper'] = df['close'] + (self.atr_multiplier * df['atr'])
        df['atr_lower'] = df['close'] - (self.atr_multiplier * df['atr'])
        
        # 5. ATR expansion/contraction
        df['atr_ma'] = df['atr'].rolling(20).mean()
        df['atr_ratio'] = df['atr'] / df['atr_ma']
        df['squeeze'] = df['atr_ratio'] < (1 - self.squeeze_threshold)
        df['squeeze_release'] = df['squeeze'].shift(1) & (~df['squeeze'])
        
        # 6. ADX (fuerza de tendencia)
        df['high_diff'] = df['high'].diff()
        df['low_diff'] = df['low'].diff()
        df['plus_dm'] = np.where((df['high_diff'] > abs(df['low_diff'])) & (df['high_diff'] > 0), df['high_diff'], 0)
        df['minus_dm'] = np.where((abs(df['low_diff']) > df['high_diff']) & (df['low_diff'] < 0), abs(df['low_diff']), 0)
        df['tr_smooth'] = df['tr'].rolling(self.adx_period).sum()
        df['plus_di'] = 100 * df['plus_dm'].rolling(self.adx_period).sum() / (df['tr_smooth'] + 1e-10)
        df['minus_di'] = 100 * df['minus_dm'].rolling(self.adx_period).sum() / (df['tr_smooth'] + 1e-10)
        df['dx'] = 100 * abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'] + 1e-10)
        df['adx'] = df['dx'].rolling(self.adx_period).mean()
        
        # 7. Volumen relativo
        df['vol_ma'] = df['volume'].rolling(window=self.vol_ma).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma']
        
        # 8. Breakout confirmado
        df['breakout_up'] = df['close'] > df['upper_channel'].shift(1)
        df['breakout_down'] = df['close'] < df['lower_channel'].shift(1)
        df['breakout_up_confirmed'] = df['breakout_up'] & (df['vol_ratio'] > 1.2)
        df['breakout_down_confirmed'] = df['breakout_down'] & (df['vol_ratio'] > 1.2)
        
        # 9. Pullback post-ruptura
        df['pullback_up'] = df['breakout_up'].shift(1) & (df['close'] <= df['upper_channel']) & (df['close'] >= df['channel_mid'])
        df['pullback_down'] = df['breakout_down'].shift(1) & (df['close'] >= df['lower_channel']) & (df['close'] <= df['channel_mid'])

        df['signal'] = self.SIGNAL_WAIT
        
        # COMPRA: Breakout confirmado + squeeze release O ADX fuerte
        buy_adx = df['adx'] > self.adx_threshold
        buy_vol = df['vol_ratio'] > 1.0
        
        df.loc[df['breakout_up_confirmed'] & (df['squeeze_release'] | buy_adx) & buy_vol, 'signal'] = self.SIGNAL_BUY
        df.loc[df['pullback_up'] & buy_vol & (df['adx'] > self.adx_threshold * 0.8), 'signal'] = self.SIGNAL_BUY

        # VENTA: Breakout confirmado + squeeze release O ADX fuerte
        sell_adx = df['adx'] > self.adx_threshold
        sell_vol = df['vol_ratio'] > 1.0
        
        df.loc[df['breakout_down_confirmed'] & (df['squeeze_release'] | sell_adx) & sell_vol, 'signal'] = self.SIGNAL_SELL
        df.loc[df['pullback_down'] & sell_vol & (df['adx'] > self.adx_threshold * 0.8), 'signal'] = self.SIGNAL_SELL

        return df

    def on_price_tick(self, price: float, current_position: dict = None, context: dict = None) -> int:
        """
        Tick rápido: captura rupturas de volatilidad.
        """
        if price is None or price <= 0:
            return self.SIGNAL_WAIT

        ctx = context or {}
        prev_price = float(ctx.get("prev_price") or 0)
        if prev_price <= 0:
            return self.SIGNAL_WAIT

        change = (float(price) - prev_price) / prev_price
        breakout = float(self.config.get("tick_breakout_pct", 0.4)) / 100.0

        if current_position and float(current_position.get("qty", 0) or 0) > 0:
            return self.SIGNAL_WAIT

        if change >= breakout:
            return self.SIGNAL_BUY
        if change <= -breakout:
            return self.SIGNAL_SELL
            
        return self.SIGNAL_WAIT

    def get_features(self) -> List[str]:
        return ['channel_position', 'atr_pct', 'atr_ratio', 'squeeze', 'squeeze_release', 'adx', 'vol_ratio']
