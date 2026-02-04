import numpy as np
import pandas as pd
from typing import List
from api.src.domain.strategies.base import BaseStrategy

class BollingerBandsStrategy(BaseStrategy):
    """
    Compra cuando el precio toca la banda inferior (barato).
    Venta cuando toca la banda superior (caro).
    """
    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        window = self.config.get('window', 20)
        std_dev = self.config.get('std_dev', 2)

        df['bb_mid'] = df['close'].rolling(window=window).mean()
        df['bb_std'] = df['close'].rolling(window=window).std()
        df['bb_upper'] = df['bb_mid'] + (df['bb_std'] * std_dev)
        df['bb_lower'] = df['bb_mid'] - (df['bb_std'] * std_dev)

        df['signal'] = self.SIGNAL_WAIT
        
        # Compra: Precio cierra por debajo de banda inferior y empieza a subir
        df.loc[df['close'] < df['bb_lower'], 'signal'] = self.SIGNAL_BUY
        
        # Venta: Precio supera banda superior
        df.loc[df['close'] > df['bb_upper'], 'signal'] = self.SIGNAL_SELL

        return df

    def get_features(self) -> List[str]:
        return ['bb_upper', 'bb_mid', 'bb_lower', 'bb_std']
