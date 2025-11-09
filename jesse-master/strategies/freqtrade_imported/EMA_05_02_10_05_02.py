"""
EMA_05_02_10_05_02 - Очень чувствительная EMA стратегия
- Таймфрейм: 30 секунд
- Вход: при просадке 0.5% от EMA
- Стоп-лосс: 0.2%
- Тейк-профит: 10%
- Трейлинг: активируется при прибыли 0.5%, отступ 0.2%
"""

from freqtrade.strategy.interface import IStrategy
from pandas import DataFrame
import pandas as pd
import numpy as np
from typing import Optional


class EMA_05_02_10_05_02(IStrategy):
    """
    Очень чувствительная EMA стратегия для 30-секундного таймфрейма:
    - Отслеживает просадки 0.5% от EMA
    - Быстрый стоп-лосс 0.2%
    - Высокий тейк-профит 10%
    - Трейлинг стоп с отступом 0.2% после достижения 0.5% прибыли
    """
    
    INTERFACE_VERSION = 3
    
    timeframe = '30s'  # 30 секунд
    
    # Стоп-лосс и тейк-профит
    stoploss = -0.002  # -0.2% стоп-лосс
    
    minimal_roi = {
        "0": 0.10,   # 10% тейк-профит
        "30": 0.05,  # 5% после 30 свечей (15 минут)
        "60": 0.03,  # 3% после 60 свечей (30 минут)
        "120": 0.01  # 1% после 120 свечей (1 час)
    }
    
    # Трейлинг стоп
    trailing_stop = True
    trailing_stop_positive = 0.002  # Активируется при 0.2% прибыли
    trailing_stop_positive_offset = 0.005  # Отступ 0.5% (должен быть больше чем trailing_stop_positive)
    trailing_only_offset_is_reached = True
    
    startup_candle_count: int = 50
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Добавляем EMA индикаторы"""
        # Быстрая EMA для отслеживания краткосрочных движений
        dataframe['ema_fast'] = dataframe['close'].ewm(span=9, adjust=False).mean()
        
        # Средняя EMA для определения тренда
        dataframe['ema_medium'] = dataframe['close'].ewm(span=21, adjust=False).mean()
        
        # Медленная EMA для долгосрочного тренда
        dataframe['ema_slow'] = dataframe['close'].ewm(span=50, adjust=False).mean()
        
        # Процентное отклонение от EMA
        dataframe['price_deviation_pct'] = ((dataframe['close'] - dataframe['ema_fast']) / dataframe['ema_fast']) * 100
        
        # Процентное изменение за последние N свечей
        dataframe['price_change_1'] = dataframe['close'].pct_change(1) * 100
        dataframe['price_change_3'] = dataframe['close'].pct_change(3) * 100
        dataframe['price_change_5'] = dataframe['close'].pct_change(5) * 100
        
        # Объем для подтверждения
        dataframe['volume_ma'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_ma']
        
        # RSI для определения перепроданности
        delta = dataframe['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, np.nan)
        rs = rs.fillna(0)
        dataframe['rsi'] = 100 - (100 / (1 + rs.replace(0, np.nan)))
        dataframe['rsi'] = dataframe['rsi'].fillna(50)
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Вход при просадке 0.5% от EMA"""
        dataframe.loc[:, 'enter_long'] = 0
        
        dataframe.loc[
            (
                # Просадка 0.5% от быстрой EMA (в пределах 0.4-0.6%)
                (dataframe['price_deviation_pct'] <= -0.4) &
                (dataframe['price_deviation_pct'] >= -0.6) &
                
                # Восходящий тренд (быстрая EMA выше средней)
                (dataframe['ema_fast'] > dataframe['ema_medium']) &
                
                # Средняя EMA выше медленной (подтверждение тренда)
                (dataframe['ema_medium'] > dataframe['ema_slow']) &
                
                # Признаки разворота (цена начала расти)
                (dataframe['close'] > dataframe['close'].shift(1)) &
                
                # RSI не перекуплен (ниже 70)
                (dataframe['rsi'] < 70) &
                (dataframe['rsi'] > 30) &
                
                # Объем выше среднего (интерес покупателей)
                (dataframe['volume_ratio'] > 0.8) &
                
                # Проверка на валидность данных
                (dataframe['price_deviation_pct'].notna()) &
                (dataframe['ema_fast'].notna()) &
                (dataframe['volume_ratio'].notna())
            ),
            'enter_long'
        ] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Выход по тейк-профиту или стоп-лоссу (трейлинг обрабатывается автоматически)"""
        dataframe.loc[:, 'exit_long'] = 0
        
        # Выход при достижении тейк-профита или при развороте тренда
        dataframe.loc[
            (
                # Разворот тренда (быстрая EMA ниже средней)
                (dataframe['ema_fast'] < dataframe['ema_medium']) |
                
                # RSI перекуплен (выше 70)
                (dataframe['rsi'] > 70) |
                
                # Цена значительно выше EMA (перекупленность)
                (dataframe['price_deviation_pct'] > 2.0)
            ),
            'exit_long'
        ] = 1
        
        return dataframe
    
    def custom_stoploss(self, pair: str, trade: 'Trade', current_time: 'datetime',
                       current_rate: float, current_profit: float, **kwargs) -> float:
        """
        Кастомный стоп-лосс с трейлингом
        - Базовый стоп: -0.2%
        - Трейлинг активируется при прибыли 0.5%
        - Отступ трейлинга: 0.2%
        """
        # Базовый стоп-лосс
        if current_profit < -0.002:
            return -0.002
        
        # Трейлинг стоп: активируется при прибыли 0.5%
        if current_profit >= 0.005:
            # Трейлинг с отступом 0.2%
            # Если текущая прибыль 0.5%, стоп на 0.3% (0.5% - 0.2%)
            # Если текущая прибыль 1%, стоп на 0.8% (1% - 0.2%)
            trailing_stop = current_profit - 0.002
            return -trailing_stop
        
        # До достижения 0.5% прибыли используем базовый стоп
        return -0.002

