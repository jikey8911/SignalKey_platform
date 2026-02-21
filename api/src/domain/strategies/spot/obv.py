import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from api.src.domain.strategies.base import BaseStrategy

class OBVStrategy(BaseStrategy):
    """
    OBV Strategy v2.0 - Optimized
    
    On-Balance Volume con filtros de confirmación y divergencias.
    
    Mejoras aplicadas:
    - OBV acumulación/distribución
    - OBV slope (tendencia de volumen)
    - Divergencias OBV-precio
    - Filtro de tendencia (EMA 200)
    - Volumen relativo normalizado
    - OBV MA crossover confirmado
    """
    
    def __init__(self, config=None):
        super().__init__(config or {})
        self.obv_ma_period = int(self.config.get('obv_ma_period', 20))
        self.ema_trend = int(self.config.get('ema_trend', 200))
        self.vol_ma = int(self.config.get('vol_ma', 20))
        self.divergence_lookback = int(self.config.get('divergence_lookback', 5))

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        if len(df) < self.ema_trend:
            df['signal'] = self.SIGNAL_WAIT
            return df

        # 1. OBV calculation
        df['obv'] = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
        
        # 2. OBV normalizado (para ML)
        df['obv_norm'] = (df['obv'] - df['obv'].rolling(50).min()) / \
                        (df['obv'].rolling(50).max() - df['obv'].rolling(50).min() + 1e-10)
        
        # 3. OBV MA
        df['obv_ma'] = df['obv'].rolling(window=self.obv_ma_period).mean()
        
        # 4. OBV slope (tendencia de volumen)
        df['obv_slope'] = df['obv'].pct_change(5) * 100
        df['obv_slope_sign'] = np.sign(df['obv_slope'])
        
        # 5. Filtro de tendencia
        df['ema_200'] = df['close'].ewm(span=self.ema_trend, adjust=False).mean()
        df['trend'] = 1 if df['close'].iloc[-1] > df['ema_200'].iloc[-1] else -1
        
        # 6. Volumen relativo
        df['vol_ma'] = df['volume'].rolling(window=self.vol_ma).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma']
        
        # 7. Divergencias
        # Divergencia alcista: precio mínimo más bajo, OBV mínimo más alto
        df['price_min'] = df['close'].rolling(self.divergence_lookback).min()
        df['obv_min'] = df['obv'].rolling(self.divergence_lookback).min()
        df['bull_div'] = (df['close'] < df['price_min'].shift(1)) & (df['obv'] > df['obv_min'].shift(1))
        
        # Divergencia bajista: precio máximo más alto, OBV máximo más bajo
        df['price_max'] = df['close'].rolling(self.divergence_lookback).max()
        df['obv_max'] = df['obv'].rolling(self.divergence_lookback).max()
        df['bear_div'] = (df['close'] > df['price_max'].shift(1)) & (df['obv'] < df['obv_max'].shift(1))
        
        # 8. OBV acumulación/distribución
        df['obv_accum'] = df['obv'] > df['obv_ma']
        df['obv_dist'] = df['obv'] < df['obv_ma']
        
        # 9. Cruce confirmado
        df['obv_cross_up'] = (df['obv'] > df['obv_ma']) & (df['obv'].shift(1) <= df['obv_ma'].shift(1))
        df['obv_cross_down'] = (df['obv'] < df['obv_ma']) & (df['obv'].shift(1) >= df['obv_ma'].shift(1))

        df['signal'] = self.SIGNAL_WAIT
        
        # COMPRA: OBV cruza MA + (divergencia alcista O tendencia favorable) + volumen
        buy_cross = df['obv_cross_up']
        buy_vol = df['vol_ratio'] > 0.8
        buy_trend = (df['trend'] >= 0) | df['bull_div']
        
        df.loc[buy_cross & buy_vol & buy_trend, 'signal'] = self.SIGNAL_BUY
        
        # COMPRA alternativa: Divergencia + acumulación
        df.loc[df['bull_div'] & df['obv_accum'] & buy_vol, 'signal'] = self.SIGNAL_BUY

        # VENTA: OBV cruza MA + (divergencia bajista O tendencia favorable) + volumen
        sell_cross = df['obv_cross_down']
        sell_vol = df['vol_ratio'] > 0.8
        sell_trend = (df['trend'] <= 0) | df['bear_div']
        
        df.loc[sell_cross & sell_vol & sell_trend, 'signal'] = self.SIGNAL_SELL
        
        # VENTA alternativa: Divergencia + distribución
        df.loc[df['bear_div'] & df['obv_dist'] & sell_vol, 'signal'] = self.SIGNAL_SELL

        return df

    def on_price_tick(self, price: float, current_position: dict = None, context: dict = None) -> int:
        """
        Tick intravela: detector de flujo de volumen anormal.
        """
        if price is None or price <= 0:
            return self.SIGNAL_WAIT

        ctx = context or {}
        prev_price = float(ctx.get("prev_price") or 0)
        prev_vol = float(ctx.get("prev_volume") or 0)
        curr_vol = float(ctx.get("curr_volume") or 0)
        
        if prev_price <= 0:
            return self.SIGNAL_WAIT

        change = (float(price) - prev_price) / prev_price
        trigger = float(self.config.get("tick_obv_trigger_pct", 0.5)) / 100.0
        
        # Volumen anormal
        vol_spike = (curr_vol > prev_vol * 2) if prev_vol > 0 else False

        if current_position and float(current_position.get("qty", 0) or 0) > 0:
            return self.SIGNAL_WAIT

        if change >= trigger or (change > 0 and vol_spike):
            return self.SIGNAL_BUY
        if change <= -trigger or (change < 0 and vol_spike):
            return self.SIGNAL_SELL
            
        return self.SIGNAL_WAIT

    def get_features(self) -> List[str]:
        return ['obv_norm', 'obv_slope', 'obv_accum', 'obv_dist', 'bull_div', 'bear_div']
