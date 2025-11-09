"""
DipBuyStrategy - Стратегия покупки на проливах (dips)
Входит при резком падении цены на 1-3%
"""

from freqtrade.strategy import IStrategy, DataFrame
import pandas as pd
import numpy as np


class DipBuyStrategy(IStrategy):
    """
    Стратегия покупки на проливах:
    - Определяет резкие падения (1-3%)
    - Входит при признаках разворота
    - Выходит при восстановлении или стоп-лоссе
    """
    
    INTERFACE_VERSION = 3
    
    timeframe = '5m'
    stoploss = -0.02  # -2% стоп-лосс
    
    minimal_roi = {
        "0": 0.04,  # 4% прибыль
        "20": 0.02,  # 2% после 20 минут
        "40": 0.01   # 1% после 40 минут
    }
    
    startup_candle_count: int = 30
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Add indicators"""
        # RSI для определения перепроданности
        delta = dataframe['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        # Избегаем деления на ноль
        rs = gain / loss.replace(0, np.nan)
        rs = rs.fillna(0)
        dataframe['rsi'] = 100 - (100 / (1 + rs.replace(0, np.nan)))
        dataframe['rsi'] = dataframe['rsi'].fillna(50)  # По умолчанию 50 если нет данных
        
        # Определяем падение за последние N свечей
        dataframe['price_change_pct'] = ((dataframe['close'] - dataframe['close'].shift(5)) / dataframe['close'].shift(5)) * 100
        
        # Объем для подтверждения
        dataframe['volume_ma'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_spike'] = dataframe['volume'] > dataframe['volume_ma'] * 1.5
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry on dip with reversal signs"""
        # Инициализируем колонку
        dataframe.loc[:, 'enter_long'] = 0
        
        dataframe.loc[
            (
                # Падение на 1-3%
                (dataframe['price_change_pct'] <= -1.0) &
                (dataframe['price_change_pct'] >= -3.0) &
                # RSI перепродан (ниже 35)
                (dataframe['rsi'] < 35) &
                (dataframe['rsi'] > 0) &  # Проверка на валидность
                # Признаки разворота (цена начала расти)
                (dataframe['close'] > dataframe['close'].shift(1)) &
                # Объем выше среднего (интерес покупателей)
                (dataframe['volume'] > dataframe['volume_ma'] * 0.9) &
                # Проверка на NaN
                (dataframe['price_change_pct'].notna()) &
                (dataframe['volume_ma'].notna())
            ),
            'enter_long'
        ] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit on recovery or stop"""
        dataframe.loc[
            (
                # Цена восстановилась (прибыль)
                (dataframe['price_change_pct'] > 0) |
                # RSI перекуплен (выход с прибылью)
                (dataframe['rsi'] > 70) |
                # Дальнейшее падение (стоп)
                (dataframe['price_change_pct'] < -4.0)
            ),
            'exit_long'
        ] = 1
        
        return dataframe

