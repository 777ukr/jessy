"""
PullbackBuyStrategy - Стратегия покупки на откатах (pullbacks)
Входит в позицию при откате цены от максимума на 0.5-2%
"""

from freqtrade.strategy import IStrategy, DataFrame
import pandas as pd
import numpy as np


class PullbackBuyStrategy(IStrategy):
    """
    Стратегия покупки на откатах:
    - Определяет локальные максимумы
    - Входит при откате на 0.5-2% от максимума
    - Выходит при восстановлении или стоп-лоссе
    """
    
    INTERFACE_VERSION = 3
    
    timeframe = '5m'
    stoploss = -0.015  # -1.5% стоп-лосс
    
    minimal_roi = {
        "0": 0.03,  # 3% прибыль
        "30": 0.02,  # 2% после 30 минут
        "60": 0.01   # 1% после 60 минут
    }
    
    startup_candle_count: int = 50
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Add indicators"""
        # EMA для тренда
        dataframe['ema_21'] = dataframe['close'].ewm(span=21, adjust=False).mean()
        dataframe['ema_50'] = dataframe['close'].ewm(span=50, adjust=False).mean()
        
        # Определяем локальные максимумы (rolling max за 10 свечей)
        dataframe['local_max'] = dataframe['high'].rolling(window=10).max()
        dataframe['pullback_pct'] = ((dataframe['local_max'] - dataframe['close']) / dataframe['local_max']) * 100
        
        # Объем для подтверждения
        dataframe['volume_ma'] = dataframe['volume'].rolling(window=20).mean()
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry on pullback"""
        dataframe.loc[
            (
                # Откат от максимума на 0.5-2%
                (dataframe['pullback_pct'] >= 0.5) &
                (dataframe['pullback_pct'] <= 2.0) &
                # Цена выше EMA (восходящий тренд)
                (dataframe['close'] > dataframe['ema_21']) &
                (dataframe['ema_21'] > dataframe['ema_50']) &
                # Объем выше среднего
                (dataframe['volume'] > dataframe['volume_ma'] * 0.8) &
                # Цена начала восстанавливаться
                (dataframe['close'] > dataframe['close'].shift(1))
            ),
            'enter_long'
        ] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit when price recovers or trend reverses"""
        dataframe.loc[
            (
                # Цена восстановилась до максимума (прибыль зафиксирована)
                (dataframe['close'] >= dataframe['local_max'] * 0.98) |
                # Тренд развернулся
                (dataframe['ema_21'] < dataframe['ema_50']) |
                # Сильный откат (стоп)
                (dataframe['pullback_pct'] > 3.0)
            ),
            'exit_long'
        ] = 1
        
        return dataframe

