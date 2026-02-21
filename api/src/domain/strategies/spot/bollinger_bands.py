import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from api.src.domain.strategies.base import BaseStrategy

class BollingerBandsStrategy(BaseStrategy):
    """
    Bollinger Bands Strategy v2.0 - Optimized
    
    Compra en banda inferior, vende en banda superior con filtros avanzados.
    
    Mejoras aplicadas:
    - %B Indicator (posición relativa en las bandas)
    - Bandwidth (medida de volatilidad/squeeze)
    - Filtro de tendencia (EMA 200)
    - Confirmación de volumen en rupturas
    - Detección de squeeze (baja volatilidad → explosión inminente)
    """
    
    def __init__(self, config=None):
        super().__init__(config or {})
        self.window = int(self.config.get('window', 20))
        self.std_dev = float(self.config.get('std_dev', 2.0))
        self.ema_trend = int(self.config.get('ema_trend', 200))
        self.vol_ma = int(self.config.get('vol_ma', 20))
        self.squeeze_threshold = float(self.config.get('squeeze_threshold', 0.05))

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        if len(df) < self.ema_trend:
            df['signal'] = self.SIGNAL_WAIT
            return df

        # 1. Bollinger Bands
        df['bb_mid'] = df['close'].rolling(window=self.window).mean()
        df['bb_std'] = df['close'].rolling(window=self.window).std()
        df['bb_upper'] = df['bb_mid'] + (df['bb_std'] * self.std_dev)
        df['bb_lower'] = df['bb_mid'] - (df['bb_std'] * self.std_dev)
        
        # 2. %B Indicator (posición relativa: 0=banda inferior, 1=banda superior)
        df['bb_pct'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 1e-10)
        
        # 3. Bandwidth (volatilidad relativa)
        df['bb_bandwidth'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid']
        
        # 4. Squeeze detection (bandwidth < threshold → baja volatilidad)
        df['squeeze'] = df['bb_bandwidth'] < self.squeeze_threshold
        df['squeeze_release'] = df['squeeze'].shift(1) & (~df['squeeze'])
        
        # 5. Filtro de tendencia
        df['ema_200'] = df['close'].ewm(span=self.ema_trend, adjust=False).mean()
        df['trend'] = 1 if df['close'].iloc[-1] > df['ema_200'].iloc[-1] else -1
        
        # 6. Filtro de volumen
        df['vol_ma'] = df['volume'].rolling(window=self.vol_ma).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma']
        
        # 7. Normalized band position for ML
        df['bb_position'] = (df['bb_pct'] - df['bb_pct'].rolling(50).min()) / \
                           (df['bb_pct'].rolling(50).max() - df['bb_pct'].rolling(50).min() + 1e-9)

        df['signal'] = self.SIGNAL_WAIT
        
        # COMPRA: Precio en/toca banda inferior + %B < 0.2 + (squeeze release O tendencia favorable)
        buy_low = df['close'] <= df['bb_lower']
        buy_pct = df['bb_pct'] < 0.2
        buy_vol = df['vol_ratio'] > 1.0
        
        df.loc[buy_low & buy_pct & buy_vol & 
               (df['squeeze_release'] | (df['trend'] >= 0)), 'signal'] = self.SIGNAL_BUY

        # VENTA: Precio en/toca banda superior + %B > 0.8 + (squeeze release O tendencia favorable)
        sell_high = df['close'] >= df['bb_upper']
        sell_pct = df['bb_pct'] > 0.8
        sell_vol = df['vol_ratio'] > 1.0
        
        df.loc[sell_high & sell_pct & sell_vol & 
               (df['squeeze_release'] | (df['trend'] <= 0)), 'signal'] = self.SIGNAL_SELL

        return df

    def on_price_tick(self, price: float, current_position: dict = None, context: dict = None) -> int:
        """
        Tick intravela: detector de ruptura de bandas.
        """
        if price is None or price <= 0:
            return self.SIGNAL_WAIT

        ctx = context or {}
        prev_price = float(ctx.get("prev_price") or 0)
        if prev_price <= 0:
            return self.SIGNAL_WAIT

        change = (float(price) - prev_price) / prev_price
        trigger = float(self.config.get("tick_bb_trigger_pct", 0.5)) / 100.0

        if current_position and float(current_position.get("qty", 0) or 0) > 0:
            return self.SIGNAL_WAIT

        if change >= trigger:
            return self.SIGNAL_BUY
        if change <= -trigger:
            return self.SIGNAL_SELL
            
        return self.SIGNAL_WAIT

    def get_features(self) -> List[str]:
        return ['bb_pct', 'bb_bandwidth', 'bb_position', 'squeeze', 'squeeze_release']
