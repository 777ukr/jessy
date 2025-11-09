"""
Simple RSI Strategy - Простая RSI стратегия для тестирования
Вход при перепроданности, выход при перекупленности
"""

from freqtrade.strategy import IStrategy, DataFrame
import pandas as pd
import numpy as np


class SimpleRSIStrategy(IStrategy):
    """
    Простая RSI стратегия
    Вход: RSI < 30 (перепроданность)
    Выход: RSI > 70 (перекупленность) или стоп-лосс
    """
    
    INTERFACE_VERSION = 3
    
    timeframe = '5m'
    stoploss = -0.03  # -3% стоп-лосс
    
    minimal_roi = {
        "0": 0.04,
        "30": 0.02,
        "60": 0.01
    }
    
    startup_candle_count: int = 14
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Add RSI indicator"""
        # RSI calculation - handle division by zero
        delta = dataframe['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        
        # Avoid division by zero
        rs = gain / loss.replace(0, np.nan)
        rs = rs.fillna(0)
        
        dataframe['rsi'] = 100 - (100 / (1 + rs))
        dataframe['rsi'] = dataframe['rsi'].fillna(50)  # Default to 50 if calculation fails
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry when RSI is oversold"""
        dataframe.loc[
            (
                (dataframe['rsi'] < 30) &
                (dataframe['rsi'].shift(1) >= 30) &
                (dataframe['volume'] > 0)
            ),
            'enter_long'
        ] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit when RSI is overbought"""
        dataframe.loc[
            (
                (dataframe['rsi'] > 70) &
                (dataframe['rsi'].shift(1) <= 70)
            ),
            'exit_long'
        ] = 1
        
        return dataframe

