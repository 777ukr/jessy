"""
Simple EMA Strategy - Простая рабочая стратегия для тестирования
EMA crossover с минимальными настройками
"""

from freqtrade.strategy import IStrategy, DataFrame
import pandas as pd
import numpy as np


class SimpleEMAStrategy(IStrategy):
    """
    Простая EMA стратегия для быстрого тестирования
    Вход: EMA 9 пересекает EMA 21 снизу вверх
    Выход: EMA 9 пересекает EMA 21 сверху вниз или стоп-лосс
    """
    
    # Strategy interface version
    INTERFACE_VERSION = 3
    
    # Strategy parameters
    timeframe = '5m'
    stoploss = -0.02  # -2% стоп-лосс
    
    # Minimal ROI
    minimal_roi = {
        "0": 0.05,  # 5% прибыль
        "60": 0.03,  # 3% после 60 минут
        "120": 0.01  # 1% после 120 минут
    }
    
    # Trailing stop
    trailing_stop = False
    
    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 30
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Add indicators to dataframe"""
        # EMA 9
        dataframe['ema_9'] = dataframe['close'].ewm(span=9, adjust=False).mean()
        
        # EMA 21
        dataframe['ema_21'] = dataframe['close'].ewm(span=21, adjust=False).mean()
        
        # EMA 50
        dataframe['ema_50'] = dataframe['close'].ewm(span=50, adjust=False).mean()
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry signals"""
        dataframe.loc[
            (
                (dataframe['ema_9'] > dataframe['ema_21']) &
                (dataframe['ema_9'].shift(1) <= dataframe['ema_21'].shift(1)) &
                (dataframe['close'] > dataframe['ema_50']) &
                (dataframe['volume'] > 0)
            ),
            'enter_long'
        ] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit signals"""
        dataframe.loc[
            (
                (dataframe['ema_9'] < dataframe['ema_21']) &
                (dataframe['ema_9'].shift(1) >= dataframe['ema_21'].shift(1))
            ),
            'exit_long'
        ] = 1
        
        return dataframe

