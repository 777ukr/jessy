"""
Short Trend Strategy - Шортовая стратегия для фьючерсов
Торгует против тренда при сигналах разворота
"""

from freqtrade.strategy.interface import IStrategy
from typing import Dict, List
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib

class ShortTrendStrategy(IStrategy):
    """
    Шортовая стратегия для фьючерсов с плечом
    Торгует против восходящего тренда при сигналах разворота
    """
    
    INTERFACE_VERSION = 2
    
    # Параметры стратегии
    can_short = True  # Включаем шорт
    timeframe = '1h'
    
    # ROI для шорта (отрицательные значения)
    minimal_roi = {
        "0": -0.02,   # 2% прибыль
        "30": -0.01,  # 1% после 30 минут
        "60": 0.005   # 0.5% после 1 часа
    }
    
    stoploss = 0.03  # 3% стоп-лосс для шорта
    
    # Trailing stop
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True
    
    # Индикаторы
    startup_candle_count = 200
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Добавить индикаторы"""
        # EMA для определения тренда
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)
        
        # RSI для определения перекупленности
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # MACD для определения разворота
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # Volume для подтверждения
        dataframe['volume_sma'] = ta.SMA(dataframe, timeperiod=20, column='volume')
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Условия входа в шорт"""
        dataframe.loc[
            (
                # EMA50 пересекла EMA200 сверху вниз (разворот вниз)
                (dataframe['ema_50'] < dataframe['ema_200']) &
                (dataframe['ema_50'].shift(1) >= dataframe['ema_200'].shift(1)) &
                
                # RSI показывает перекупленность
                (dataframe['rsi'] > 70) &
                
                # MACD показывает разворот вниз
                (dataframe['macd'] < dataframe['macdsignal']) &
                (dataframe['macdhist'] < 0) &
                
                # Объем выше среднего
                (dataframe['volume'] > dataframe['volume_sma']) &
                
                (dataframe['volume'] > 0)
            ),
            'enter_short'] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Условия выхода из шорта"""
        dataframe.loc[
            (
                # RSI перешел в зону перепроданности (возможен разворот)
                (dataframe['rsi'] < 30) |
                
                # MACD показывает разворот вверх
                (dataframe['macd'] > dataframe['macdsignal']) &
                (dataframe['macdhist'] > 0)
            ),
            'exit_short'] = 1
        
        return dataframe




