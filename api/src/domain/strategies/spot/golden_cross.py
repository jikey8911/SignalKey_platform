import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from api.src.domain.strategies.base import BaseStrategy

class GoldenCrossStrategy(BaseStrategy):
    """
    Golden Cross Strategy v2.0 - Optimized
    
    Cruce de SMAs con filtros de confirmación y gestión de tendencia.
    
    Mejoras aplicadas:
    - Triple SMA (50/100/200) para confirmación
    - ADX filtro (fuerza de tendencia)
    - Volumen relativo para confirmación
    - SMA slope (pendiente) como feature
    - Golden/Death cross clásico + cruces intermedios
    - Pullback detection
    """
    
    def __init__(self, config=None):
        super().__init__(config or {})
        self.sma_fast = int(self.config.get('sma_fast', 50))
        self.sma_mid = int(self.config.get('sma_mid', 100))
        self.sma_slow = int(self.config.get('sma_slow', 200))
        self.adx_period = int(self.config.get('adx_period', 14))
        self.vol_ma = int(self.config.get('vol_ma', 20))
        self.adx_threshold = float(self.config.get('adx_threshold', 20))

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        if len(df) < self.sma_slow + self.adx_period:
            df['signal'] = self.SIGNAL_WAIT
            return df

        # 1. Triple SMA
        df['sma_f'] = df['close'].rolling(window=self.sma_fast).mean()
        df['sma_m'] = df['close'].rolling(window=self.sma_mid).mean()
        df['sma_s'] = df['close'].rolling(window=self.sma_slow).mean()
        
        # 2. SMA differences (porcentaje)
        df['sma_diff_fm'] = (df['sma_f'] - df['sma_m']) / df['sma_m'] * 100
        df['sma_diff_ms'] = (df['sma_m'] - df['sma_s']) / df['sma_s'] * 100
        df['sma_diff_fs'] = (df['sma_f'] - df['sma_s']) / df['sma_s'] * 100
        
        # 3. SMA slope (pendiente = fuerza)
        df['sma_f_slope'] = df['sma_f'].pct_change(10) * 100
        df['sma_s_slope'] = df['sma_s'].pct_change(10) * 100
        
        # 4. ADX (fuerza de tendencia)
        df['tr'] = pd.concat([df['high'] - df['low'], 
                             (df['high'] - df['close'].shift()).abs(), 
                             (df['low'] - df['close'].shift()).abs()], axis=1).max(axis=1)
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
        
        # 6. Golden Cross (clásico: 50 cruza 200)
        df['golden_cross'] = (df['sma_f'] > df['sma_s']) & (df['sma_f'].shift(1) <= df['sma_s'].shift(1))
        df['death_cross'] = (df['sma_f'] < df['sma_s']) & (df['sma_f'].shift(1) >= df['sma_s'].shift(1))
        
        # 7. Cruce intermedio (50/100)
        df['cross_up_mid'] = (df['sma_f'] > df['sma_m']) & (df['sma_f'].shift(1) <= df['sma_m'].shift(1))
        df['cross_down_mid'] = (df['sma_f'] < df['sma_m']) & (df['sma_f'].shift(1) >= df['sma_m'].shift(1))
        
        # 8. Tendencia alineada
        df['trend_bull'] = (df['sma_f'] > df['sma_m']) & (df['sma_m'] > df['sma_s'])
        df['trend_bear'] = (df['sma_f'] < df['sma_m']) & (df['sma_m'] < df['sma_s'])
        
        # 9. Pullback
        df['pullback_bull'] = df['trend_bull'] & (df['close'] <= df['sma_f']) & (df['close'] > df['sma_m'])
        df['pullback_bear'] = df['trend_bear'] & (df['close'] >= df['sma_f']) & (df['close'] < df['sma_m'])

        df['signal'] = self.SIGNAL_WAIT
        
        # COMPRA: Golden cross O cruce intermedio + ADX + volumen
        buy_cross = df['golden_cross'] | df['cross_up_mid']
        buy_adx = df['adx'] > self.adx_threshold
        buy_vol = df['vol_ratio'] > 1.0
        
        df.loc[buy_cross & buy_adx & buy_vol, 'signal'] = self.SIGNAL_BUY
        df.loc[df['pullback_bull'] & buy_vol & (df['adx'] > self.adx_threshold * 0.8), 'signal'] = self.SIGNAL_BUY

        # VENTA: Death cross O cruce intermedio + ADX + volumen
        sell_cross = df['death_cross'] | df['cross_down_mid']
        sell_adx = df['adx'] > self.adx_threshold
        sell_vol = df['vol_ratio'] > 1.0
        
        df.loc[sell_cross & sell_adx & sell_vol, 'signal'] = self.SIGNAL_SELL
        df.loc[df['pullback_bear'] & sell_vol & (df['adx'] > self.adx_threshold * 0.8), 'signal'] = self.SIGNAL_SELL

        return df

    def on_price_tick(self, price: float, current_position: dict = None, context: dict = None) -> int:
        """
        Tick intravela: detector de ruptura de tendencia.
        """
        if price is None or price <= 0:
            return self.SIGNAL_WAIT

        ctx = context or {}
        prev_price = float(ctx.get("prev_price") or 0)
        if prev_price <= 0:
            return self.SIGNAL_WAIT

        change = (float(price) - prev_price) / prev_price
        trigger = float(self.config.get("tick_gc_trigger_pct", 0.5)) / 100.0

        if current_position and float(current_position.get("qty", 0) or 0) > 0:
            return self.SIGNAL_WAIT

        if change >= trigger:
            return self.SIGNAL_BUY
        if change <= -trigger:
            return self.SIGNAL_SELL
            
        return self.SIGNAL_WAIT

    def get_features(self) -> List[str]:
        return ['sma_diff_fm', 'sma_diff_ms', 'sma_f_slope', 'sma_s_slope', 'adx', 'vol_ratio', 'golden_cross', 'death_cross']
