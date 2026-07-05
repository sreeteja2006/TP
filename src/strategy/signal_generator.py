import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class SignalGenerator:
    def __init__(self):
        self.signals = []
        self.current_position = 0

    def generate_ma_crossover_signals(self, data: pd.DataFrame, short_window: int = 10, long_window: int = 30) -> pd.DataFrame:
        df = data.copy()
        df['MA_short'] = df['Close'].rolling(window=short_window).mean()
        df['MA_long'] = df['Close'].rolling(window=long_window).mean()
        df['Signal'] = 0
        df['Signal'][short_window:] = np.where(df['MA_short'][short_window:] > df['MA_long'][short_window:], 1, 0)
        df['Position'] = df['Signal'].diff()
        return df

    def generate_rsi_signals(self, data: pd.DataFrame, rsi_period: int = 14, oversold: int = 30, overbought: int = 70) -> pd.DataFrame:
        df = data.copy()
        df['RSI'] = self._calculate_rsi(df['Close'], rsi_period)
        df['Signal'] = 0
        df.loc[df['RSI'] < oversold, 'Signal'] = 1
        df.loc[df['RSI'] > overbought, 'Signal'] = -1
        return df

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        delta = prices.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))