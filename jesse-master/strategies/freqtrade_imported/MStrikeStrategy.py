# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
"""
MStrike Strategy - Адаптация Rust стратегии для Freqtrade
Детект прострела с LastBidEMA
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


class MStrikeStrategy(IStrategy):
    """
    MStrike Strategy - детект прострела с LastBidEMA
    Основана на Rust реализации из src/strategy/moon_strategies/mstrike.rs
    
    Ловит быстрое падение цены и выставляет buy ордер
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
    
    # MStrike параметры
    mstrike_depth = DecimalParameter(5.0, 20.0, default=10.0, decimals=2, space="buy")
    mstrike_buy_level = DecimalParameter(0.0, 50.0, default=0.0, decimals=2, space="buy")
    mstrike_sell_level = DecimalParameter(50.0, 100.0, default=80.0, decimals=2, space="sell")
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Вычисляем индикаторы для детекта MStrike"""
        # EMA для LastBidEMA (используем EMA(4) как в Rust)
        dataframe['last_bid_ema'] = ta.EMA(dataframe['close'], timeperiod=4)
        
        # Вычисляем максимальную цену до прострела (для расчета глубины)
        dataframe['price_before_strike'] = dataframe['last_bid_ema'].shift(1)
        
        # Минимальная цена во время прострела
        dataframe['min_price_during_strike'] = dataframe['low'].rolling(5).min()
        
        # Глубина прострела
        dataframe['strike_depth'] = ((dataframe['price_before_strike'] - dataframe['min_price_during_strike']) / 
                                     dataframe['price_before_strike']) * 100.0
        
        # Целевая цена покупки
        dataframe['strike_buy_price'] = dataframe.apply(
            lambda row: row['min_price_during_strike'] * (1.0 + row['strike_depth'] * self.mstrike_buy_level.value / 100.0 / 100.0)
            if self.mstrike_buy_level.value > 0.0 else row['min_price_during_strike'],
            axis=1
        )
        
        # Целевая цена продажи
        dataframe['strike_sell_price'] = dataframe.apply(
            lambda row: row['min_price_during_strike'] * (1.0 + row['strike_depth'] * self.mstrike_sell_level.value / 100.0 / 100.0),
            axis=1
        )
        
        # Volume для фильтрации
        dataframe['avg_volume'] = dataframe['volume'].rolling(20).mean()
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Логика входа: детект прострела"""
        dataframe.loc[
            (
                # Детект прострела: глубина >= порога
                (dataframe['strike_depth'] >= self.mstrike_depth.value) &
                
                # Цена близка к целевой цене покупки
                (dataframe['close'] <= dataframe['strike_buy_price'] * 1.01) &
                
                # Цена ниже LastBidEMA (прострел)
                (dataframe['close'] < dataframe['last_bid_ema']) &
                
                # Фильтры качества
                (dataframe['volume'] > dataframe['avg_volume'] * 0.5) &
                (dataframe['volume'] > 0)
            ),
            "enter_long"] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Логика выхода: продажа по достижению MStrikeSellLevel"""
        dataframe.loc[
            (
                # Цена достигла уровня продажи
                (dataframe['close'] >= dataframe['strike_sell_price']) &
                (dataframe['volume'] > 0)
            ),
            "exit_long"] = 1
        
        return dataframe

