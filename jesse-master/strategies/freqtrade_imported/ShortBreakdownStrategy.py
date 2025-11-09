"""
Short Breakdown Strategy - Шорт на пробой уровня поддержки
Для фьючерсов с плечом 3-20x
"""

from freqtrade.strategy.interface import IStrategy
from typing import Dict, List
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np

class ShortBreakdownStrategy(IStrategy):
    """
    Шорт на пробой уровня поддержки
    Таймфрейм: 15M-4H
    Плечо: 3-20x
    """
    
    INTERFACE_VERSION = 2
    
    can_short = True
    timeframe = '15m'
    
    # ROI
    minimal_roi = {
        "0": -0.02,   # 2% прибыль
        "60": -0.01,  # 1% после 1 часа
        "120": 0.005  # 0.5% после 2 часов
    }
    
    stoploss = 0.02  # 2% стоп-лосс
    
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.015
    trailing_only_offset_is_reached = True
    
    startup_candle_count = 200
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Добавить индикаторы"""
        # Определяем уровни поддержки/сопротивления
        dataframe['high_max'] = dataframe['high'].rolling(window=20).max()
        dataframe['low_min'] = dataframe['low'].rolling(window=20).min()
        
        # Поддержка (нижний уровень)
        dataframe['support'] = dataframe['low_min'].shift(1)
        
        # Объем для подтверждения пробоя
        dataframe['volume_sma'] = ta.SMA(dataframe, timeperiod=20, column='volume')
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma']
        
        # RSI для фильтрации
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Условия входа в шорт при пробое поддержки"""
        dataframe.loc[
            (
                # Цена пробила поддержку (закрылась ниже)
                (dataframe['close'] < dataframe['support']) &
                (dataframe['close'].shift(1) >= dataframe['support'].shift(1)) &
                
                # Объем выше среднего (подтверждение пробоя)
                (dataframe['volume_ratio'] > 1.5) &
                
                # RSI не в зоне перепроданности (еще есть место для падения)
                (dataframe['rsi'] > 30) &
                
                (dataframe['volume'] > 0)
            ),
            'enter_short'] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Условия выхода из шорта"""
        dataframe.loc[
            (
                # Цена вернулась выше уровня поддержки
                (dataframe['close'] > dataframe['support']) |
                
                # RSI в зоне перепроданности (возможен разворот)
                (dataframe['rsi'] < 25)
            ),
            'exit_short'] = 1
        
        return dataframe




