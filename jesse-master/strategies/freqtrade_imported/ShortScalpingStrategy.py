"""
Short Scalping Strategy - Скальпинговая шортовая стратегия
Для фьючерсов с высоким плечом (5-50x)
"""

from freqtrade.strategy.interface import IStrategy
from typing import Dict, List
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib

class ShortScalpingStrategy(IStrategy):
    """
    Скальпинговая шортовая стратегия для фьючерсов
    Таймфрейм: 1-5 минут
    Плечо: 5-50x
    """
    
    INTERFACE_VERSION = 2
    
    can_short = True
    timeframe = '5m'
    
    # ROI для скальпинга
    minimal_roi = {
        "0": -0.003,  # 0.3% прибыль
        "5": -0.001,  # 0.1% после 5 минут
        "10": 0.001   # 0.1% после 10 минут
    }
    
    stoploss = 0.005  # 0.5% стоп-лосс
    
    # Trailing stop для скальпинга
    trailing_stop = True
    trailing_stop_positive = 0.002
    trailing_stop_positive_offset = 0.003
    trailing_only_offset_is_reached = True
    
    startup_candle_count = 50
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Добавить индикаторы"""
        # VWAP для определения направления
        dataframe['vwap'] = qtpylib.rolling_vwap(dataframe, window=20)
        
        # Stochastic RSI для определения перекупленности
        stoch_rsi = ta.STOCHRSI(dataframe, timeperiod=14)
        dataframe['fastd_rsi'] = stoch_rsi['fastd']
        dataframe['fastk_rsi'] = stoch_rsi['fastk']
        
        # Объем
        dataframe['volume_sma'] = ta.SMA(dataframe, timeperiod=20, column='volume')
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Условия входа в шорт"""
        dataframe.loc[
            (
                # Цена ниже VWAP
                (dataframe['close'] < dataframe['vwap']) &
                
                # Stochastic RSI показывает перекупленность и пересечение вниз
                (dataframe['fastk_rsi'] > 80) &
                (dataframe['fastk_rsi'] < dataframe['fastk_rsi'].shift(1)) &
                
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
                # Stochastic RSI перешел в зону перепроданности
                (dataframe['fastk_rsi'] < 20) |
                
                # Цена вернулась выше VWAP
                (dataframe['close'] > dataframe['vwap'])
            ),
            'exit_short'] = 1
        
        return dataframe




