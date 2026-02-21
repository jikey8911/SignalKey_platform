import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from api.src.domain.strategies.base import BaseStrategy

class ATRTrailingStrategy(BaseStrategy):
    """
    ATR Trailing Strategy v2.0 - Optimized
    
    Usa volatilidad (ATR) para trailing stop y detección de tendencias.
    
    Mejoras aplicadas:
    - ATR dinámico (ajuste por periodo)
    - Bandas trailing (upper/lower) con multiplicador ajustable
    - Filtro de tendencia (ADX)
    - Chandelier Exit logic
    - Volumen para confirmación
    - ATR expansion/contraction como feature
    """
    
    def __init__(self, config=None):
        super().__init__(config or {})
        self.atr_period = int(self.config.get('atr_period', 14))
        self.multiplier = float(self.config.get('multiplier', 3.0))
        self.adx_period = int(self.config.get('adx_period', 14))
        self.vol_ma = int(self.config.get('vol_ma', 20))
        self.adx_threshold = float(self.config.get('adx_threshold', 20))

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        if len(df) < self.atr_period + self.adx_period:
            df['signal'] = self.SIGNAL_WAIT
            return df

        # 1. True Range
        df['tr0'] = abs(df['high'] - df['low'])
        df['tr1'] = abs(df['high'] - df['close'].shift())
        df['tr2'] = abs(df['low'] - df['close'].shift())
        df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
        
        # 2. ATR
        df['atr'] = df['tr'].rolling(window=self.atr_period).mean()
        df['atr_pct'] = df['atr'] / df['close'] * 100
        
        # 3. ATR expansion/contraction
        df['atr_ma'] = df['atr'].rolling(window=20).mean()
        df['atr_ratio'] = df['atr'] / df['atr_ma']
        df['atr_expanding'] = df['atr'] > df['atr_ma']
        
        # 4. Trailing bands
        df['upper_band'] = df['high'] + (self.multiplier * df['atr'])
        df['lower_band'] = df['low'] - (self.multiplier * df['atr'])
        
        # 5. Chandelier Exit (trailing stop dinámico)
        df['chandelier_long'] = df['close'].rolling(22).max() - (3 * df['atr'])
        df['chandelier_short'] = df['close'].rolling(22).max() + (3 * df['atr'])
        
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
        
        # 8. Posición relativa a las bandas
        df['band_position'] = (df['close'] - df['lower_band']) / (df['upper_band'] - df['lower_band'] + 1e-10)
        
        # 9. Ruptura de bandas
        df['break_upper'] = df['close'] > df['upper_band'].shift(1)
        df['break_lower'] = df['close'] < df['lower_band'].shift(1)

        df['signal'] = self.SIGNAL_WAIT
        
        # COMPRA: Ruptura banda superior + ATR expanding + ADX fuerte + volumen
        buy_break = df['break_upper']
        buy_atr = df['atr_ratio'] > 1.0
        buy_adx = df['adx'] > self.adx_threshold
        buy_vol = df['vol_ratio'] > 1.0
        
        df.loc[buy_break & buy_atr & buy_adx & buy_vol, 'signal'] = self.SIGNAL_BUY
        
        # COMPRA alternativa: Chandelier long + tendencia
        df.loc[(df['close'] > df['chandelier_long']) & (df['adx'] > self.adx_threshold * 0.8) & buy_vol, 'signal'] = self.SIGNAL_BUY

        # VENTA: Ruptura banda inferior + ATR expanding + ADX fuerte + volumen
        sell_break = df['break_lower']
        sell_atr = df['atr_ratio'] > 1.0
        sell_adx = df['adx'] > self.adx_threshold
        sell_vol = df['vol_ratio'] > 1.0
        
        df.loc[sell_break & sell_atr & sell_adx & sell_vol, 'signal'] = self.SIGNAL_SELL
        
        # VENTA alternativa: Chandelier short + tendencia
        df.loc[(df['close'] < df['chandelier_short']) & (df['adx'] > self.adx_threshold * 0.8) & sell_vol, 'signal'] = self.SIGNAL_SELL

        return df

    def on_price_tick(self, price: float, current_position: dict = None, context: dict = None) -> int:
        """
        Tick intravela: detector de expansión de volatilidad.
        """
        if price is None or price <= 0:
            return self.SIGNAL_WAIT

        ctx = context or {}
        prev_price = float(ctx.get("prev_price") or 0)
        if prev_price <= 0:
            return self.SIGNAL_WAIT

        change = (float(price) - prev_price) / prev_price
        trigger = float(self.config.get("tick_atr_trigger_pct", 0.5)) / 100.0

        if current_position and float(current_position.get("qty", 0) or 0) > 0:
            return self.SIGNAL_WAIT

        if change >= trigger:
            return self.SIGNAL_BUY
        if change <= -trigger:
            return self.SIGNAL_SELL
            
        return self.SIGNAL_WAIT

    def get_features(self) -> List[str]:
        return ['atr_pct', 'atr_ratio', 'band_position', 'adx', 'vol_ratio', 'break_upper', 'break_lower']
