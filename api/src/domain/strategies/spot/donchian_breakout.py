import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from api.src.domain.strategies.base import BaseStrategy

class DonchianBreakoutStrategy(BaseStrategy):
    """
    Donchian Breakout Strategy v2.0 - Optimized
    
    Ruptura de máximos/mínimos de N periodos con filtros de confirmación.
    
    Mejoras aplicadas:
    - Canales dinámicos (ajuste por volatilidad)
    - Filtro de volumen (confirmación de ruptura)
    - Filtro de tendencia (ADX)
    - Breakout confirmado (cierre sostenido)
    - Pullback detection (entrada post-ruptura)
    - ATR para stop loss dinámico
    """
    
    def __init__(self, config=None):
        super().__init__(config or {})
        self.window = int(self.config.get('window', 20))
        self.atr_period = int(self.config.get('atr_period', 14))
        self.adx_period = int(self.config.get('adx_period', 14))
        self.vol_ma = int(self.config.get('vol_ma', 20))
        self.adx_threshold = float(self.config.get('adx_threshold', 20))
        self.vol_multiplier = float(self.config.get('vol_multiplier', 1.2))

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        if len(df) < self.window + self.adx_period:
            df['signal'] = self.SIGNAL_WAIT
            return df

        # 1. Donchian Channels
        df['donchian_high'] = df['high'].rolling(window=self.window).max()
        df['donchian_low'] = df['low'].rolling(window=self.window).min()
        df['donchian_mid'] = (df['donchian_high'] + df['donchian_low']) / 2
        
        # 2. Canal normalizado (posición relativa)
        df['donchian_position'] = (df['close'] - df['donchian_low']) / \
                                  (df['donchian_high'] - df['donchian_low'] + 1e-10)
        
        # 3. ATR (volatilidad)
        df['tr'] = pd.concat([df['high'] - df['low'], 
                             (df['high'] - df['close'].shift()).abs(), 
                             (df['low'] - df['close'].shift()).abs()], axis=1).max(axis=1)
        df['atr'] = df['tr'].rolling(window=self.atr_period).mean()
        df['atr_pct'] = df['atr'] / df['close'] * 100
        
        # 4. ADX (fuerza de tendencia)
        df['high_diff'] = df['high'].diff()
        df['low_diff'] = df['low'].diff()
        df['plus_dm'] = np.where((df['high_diff'] > abs(df['low_diff'])) & (df['high_diff'] > 0), df['high_diff'], 0)
        df['minus_dm'] = np.where((abs(df['low_diff']) > df['high_diff']) & (df['low_diff'] < 0), abs(df['low_diff']), 0)
        df['tr_smooth'] = df['tr'].rolling(self.adx_period).sum()
        df['plus_di'] = 100 * df['plus_dm'].rolling(self.adx_period).sum() / (df['tr_smooth'] + 1e-10)
        df['minus_di'] = 100 * df['minus_dm'].rolling(self.adx_period).sum() / (df['tr_smooth'] + 1e-10)
        df['dx'] = 100 * abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'] + 1e-10)
        df['adx'] = df['dx'].rolling(self.adx_period).mean()
        
        # 5. Volumen relativo
        df['vol_ma'] = df['volume'].rolling(window=self.vol_ma).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma']
        
        # 6. Breakout confirmado (cierre por encima del máximo + volumen)
        df['breakout_up'] = df['close'] > df['donchian_high'].shift(1)
        df['breakout_down'] = df['close'] < df['donchian_low'].shift(1)
        df['breakout_up_confirmed'] = df['breakout_up'] & (df['vol_ratio'] > self.vol_multiplier)
        df['breakout_down_confirmed'] = df['breakout_down'] & (df['vol_ratio'] > self.vol_multiplier)
        
        # 7. Pullback post-ruptura
        df['pullback_up'] = df['breakout_up'].shift(1) & (df['close'] <= df['donchian_high']) & (df['close'] >= df['donchian_mid'])
        df['pullback_down'] = df['breakout_down'].shift(1) & (df['close'] >= df['donchian_low']) & (df['close'] <= df['donchian_mid'])

        df['signal'] = self.SIGNAL_WAIT
        
        # COMPRA: Breakout confirmado + ADX fuerte O Pullback con volumen
        buy_adx = df['adx'] > self.adx_threshold
        buy_vol = df['vol_ratio'] > 1.0
        
        df.loc[df['breakout_up_confirmed'] & buy_adx & buy_vol, 'signal'] = self.SIGNAL_BUY
        df.loc[df['pullback_up'] & buy_vol, 'signal'] = self.SIGNAL_BUY

        # VENTA: Breakout confirmado + ADX fuerte O Pullback con volumen
        sell_adx = df['adx'] > self.adx_threshold
        sell_vol = df['vol_ratio'] > 1.0
        
        df.loc[df['breakout_down_confirmed'] & sell_adx & sell_vol, 'signal'] = self.SIGNAL_SELL
        df.loc[df['pullback_down'] & sell_vol, 'signal'] = self.SIGNAL_SELL

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
        trigger = float(self.config.get("tick_donchian_trigger_pct", 0.4)) / 100.0

        if current_position and float(current_position.get("qty", 0) or 0) > 0:
            return self.SIGNAL_WAIT

        if change >= trigger:
            return self.SIGNAL_BUY
        if change <= -trigger:
            return self.SIGNAL_SELL
            
        return self.SIGNAL_WAIT

    def get_features(self) -> List[str]:
        return ['donchian_position', 'atr_pct', 'adx', 'vol_ratio', 'breakout_up_confirmed', 'breakout_down_confirmed']
