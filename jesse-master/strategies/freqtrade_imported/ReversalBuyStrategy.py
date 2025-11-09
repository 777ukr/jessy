"""
ReversalBuyStrategy - Стратегия покупки на разворотах
Входит при развороте нисходящего тренда
"""

from freqtrade.strategy import IStrategy, DataFrame
import pandas as pd
import numpy as np


class ReversalBuyStrategy(IStrategy):
    """
    Стратегия покупки на разворотах:
    - Определяет нисходящий тренд
    - Входит при признаках разворота
    - Выходит при продолжении роста или стоп-лоссе
    """
    
    INTERFACE_VERSION = 3
    
    timeframe = '5m'
    stoploss = -0.025  # -2.5% стоп-лосс
    
    minimal_roi = {
        "0": 0.05,  # 5% прибыль
        "30": 0.03,  # 3% после 30 минут
        "60": 0.02   # 2% после 60 минут
    }
    
    startup_candle_count: int = 50
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Add indicators"""
        # EMA для определения тренда
        dataframe['ema_9'] = dataframe['close'].ewm(span=9, adjust=False).mean()
        dataframe['ema_21'] = dataframe['close'].ewm(span=21, adjust=False).mean()
        dataframe['ema_50'] = dataframe['close'].ewm(span=50, adjust=False).mean()
        
        # MACD для определения разворота
        exp1 = dataframe['close'].ewm(span=12, adjust=False).mean()
        exp2 = dataframe['close'].ewm(span=26, adjust=False).mean()
        dataframe['macd'] = exp1 - exp2
        dataframe['macd_signal'] = dataframe['macd'].ewm(span=9, adjust=False).mean()
        dataframe['macd_hist'] = dataframe['macd'] - dataframe['macd_signal']
        
        # Объем
        dataframe['volume_ma'] = dataframe['volume'].rolling(window=20).mean()
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry on reversal"""
        dataframe.loc[
            (
                # Была нисходящая тенденция (EMA 9 ниже EMA 21)
                (dataframe['ema_9'].shift(2) < dataframe['ema_21'].shift(2)) &
                # Теперь разворот (EMA 9 пересекает EMA 21 снизу вверх)
                (dataframe['ema_9'] > dataframe['ema_21']) &
                (dataframe['ema_9'].shift(1) <= dataframe['ema_21'].shift(1)) &
                # MACD подтверждает разворот
                (dataframe['macd_hist'] > 0) &
                (dataframe['macd_hist'].shift(1) <= 0) &
                # Цена выше EMA 50 (сильный разворот)
                (dataframe['close'] > dataframe['ema_50']) &
                # Объем подтверждает
                (dataframe['volume'] > dataframe['volume_ma'] * 0.8)
            ),
            'enter_long'
        ] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit on trend continuation or reversal"""
        dataframe.loc[
            (
                # Тренд развернулся обратно
                (dataframe['ema_9'] < dataframe['ema_21']) &
                (dataframe['ema_9'].shift(1) >= dataframe['ema_21'].shift(1)) |
                # MACD разворот
                (dataframe['macd_hist'] < 0) &
                (dataframe['macd_hist'].shift(1) >= 0)
            ),
            'exit_long'
        ] = 1
        
        return dataframe

