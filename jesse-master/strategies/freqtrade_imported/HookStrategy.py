# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
"""
Hook Strategy - Адаптация Rust стратегии для Freqtrade
Детектит быстрое падение и выставляет buy-ордер, который движется в коридоре
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from pandas import DataFrame
from typing import Dict, Optional, Union, Tuple

from freqtrade.strategy import (
    IStrategy,
    Trade,
    Order,
    PairLocks,
    informative,
    BooleanParameter,
    CategoricalParameter,
    DecimalParameter,
    IntParameter,
    RealParameter,
    timeframe_to_minutes,
    merge_informative_pair,
)

import talib.abstract as ta
from technical import qtpylib


class HookStrategy(IStrategy):
    """
    Hook Strategy - динамический коридор цены
    Основана на Rust реализации из src/strategy/moon_strategies/hook.rs
    
    Детектит быстрое падение (hook) и выставляет buy-ордер
    """
    
    INTERFACE_VERSION = 3
    timeframe = "5m"
    can_short: bool = False
    
    minimal_roi = {
        "0": 0.02
    }
    
    stoploss = -0.10
    trailing_stop = False
    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    
    startup_candle_count: int = 50
    
    # Hook параметры
    hook_detect_depth = DecimalParameter(3.0, 15.0, default=5.0, decimals=2, space="buy")
    hook_initial_price = DecimalParameter(10.0, 50.0, default=25.0, decimals=2, space="buy")
    hook_price_distance = DecimalParameter(5.0, 20.0, default=10.0, decimals=2, space="buy")
    hook_price_roll_back = DecimalParameter(20.0, 50.0, default=33.0, decimals=2, space="buy")
    hook_sell_level = DecimalParameter(50.0, 100.0, default=75.0, decimals=2, space="sell")
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Вычисляем индикаторы для детекта Hook"""
        # SMA для определения тренда
        dataframe['sma10'] = ta.SMA(dataframe, timeperiod=10)
        dataframe['sma50'] = ta.SMA(dataframe, timeperiod=50)
        
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe)
        
        # Вычисляем максимальную и минимальную цену за период (для детекта hook)
        dataframe['high_rolling'] = dataframe['high'].rolling(10).max()
        dataframe['low_rolling'] = dataframe['low'].rolling(10).min()
        
        # Глубина падения (hook depth)
        dataframe['hook_depth'] = ((dataframe['high_rolling'] - dataframe['low_rolling']) / dataframe['high_rolling']) * 100.0
        
        # Цена отката (rollback)
        dataframe['rollback_price'] = dataframe['high_rolling'] - (
            dataframe['hook_depth'] * self.hook_price_roll_back.value / 100.0 * dataframe['high_rolling'] / 100.0
        )
        
        # Целевая цена покупки (initial price)
        dataframe['hook_buy_price'] = dataframe['low_rolling'] + (
            (dataframe['high_rolling'] - dataframe['low_rolling']) * self.hook_initial_price.value / 100.0
        )
        
        # Коридор цены
        dataframe['corridor_upper'] = dataframe['high_rolling']
        dataframe['corridor_lower'] = dataframe['low_rolling']
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Логика входа: детект Hook (быстрое падение)"""
        dataframe.loc[
            (
                # Детект Hook: глубина падения >= порога
                (dataframe['hook_depth'] >= self.hook_detect_depth.value) &
                
                # Цена близка к нижней границе коридора
                (dataframe['close'] <= dataframe['hook_buy_price'] * 1.02) &
                
                # Фильтры качества
                (dataframe['volume'] > 0) &
                (dataframe['rsi'] < 50) &  # Не перекуплен
                (dataframe['sma10'] > dataframe['sma50'])  # Восходящий тренд в целом
            ),
            "enter_long"] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Логика выхода: продажа по достижению HookSellLevel"""
        dataframe.loc[
            (
                # Цена достигла уровня продажи (от глубины hook)
                (dataframe['close'] >= dataframe['low_rolling'] * (1.0 + dataframe['hook_depth'] * self.hook_sell_level.value / 100.0 / 100.0)) &
                (dataframe['volume'] > 0)
            ),
            "exit_long"] = 1
        
        return dataframe

