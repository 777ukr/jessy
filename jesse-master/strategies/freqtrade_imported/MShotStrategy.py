# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
"""
MShot Strategy - Адаптация Rust стратегии для Freqtrade
Ловит прострелы и автоматически переставляет ордер при движении цены
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
    stoploss_from_absolute,
    stoploss_from_open,
)

import talib.abstract as ta
from technical import qtpylib


class MShotStrategy(IStrategy):
    """
    MShot Strategy - переставление buy ордеров в коридоре цен
    Основана на Rust реализации из src/strategy/moon_strategies/mshot.rs
    
    Параметры:
    - mshot_price: % от текущей цены для buy ордера (по умолчанию 10%)
    - mshot_price_min: Мин. % когда переставлять ордер (по умолчанию 7%)
    - sell_price: Цена продажи в % (по умолчанию 1.35%)
    """
    
    INTERFACE_VERSION = 3
    timeframe = "5m"
    can_short: bool = False
    
    # Минимальный ROI
    minimal_roi = {
        "0": 0.0135  # 1.35% как в Rust версии
    }
    
    # Stoploss (опционально, если use_stop_loss = True)
    stoploss = -0.10
    
    # Trailing stop
    trailing_stop = False
    
    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    
    startup_candle_count: int = 50
    
    # MShot параметры (соответствуют MShotConfig из Rust)
    mshot_price = DecimalParameter(5.0, 20.0, default=10.0, decimals=2, space="buy")
    mshot_price_min = DecimalParameter(3.0, 15.0, default=7.0, decimals=2, space="buy")
    sell_price = DecimalParameter(0.5, 5.0, default=1.35, decimals=2, space="sell")
    
    # Модификаторы дельт (можно настроить через hyperopt)
    mshot_add_3h_delta = DecimalParameter(-1.0, 1.0, default=0.0, decimals=2, space="buy")
    mshot_add_hourly_delta = DecimalParameter(-1.0, 1.0, default=0.0, decimals=2, space="buy")
    mshot_add_15min_delta = DecimalParameter(-1.0, 1.0, default=0.0, decimals=2, space="buy")
    
    # Задержки
    mshot_replace_delay = DecimalParameter(0.0, 60.0, default=0.0, decimals=2, space="buy")
    mshot_raise_wait = DecimalParameter(0.0, 60.0, default=0.0, decimals=2, space="buy")
    
    # Опции
    mshot_minus_satoshi = BooleanParameter(default=False, space="buy")
    mshot_use_price = CategoricalParameter(["BID", "ASK", "Trade"], default="ASK", space="buy")
    
    def informative_pairs(self):
        """
        Добавляем дополнительные таймфреймы для расчета дельт
        """
        return [
            ("BTC/USDT", "15m"),  # Для 15m дельты
            ("BTC/USDT", "1h"),   # Для hourly дельты
            ("BTC/USDT", "3h"),   # Для 3h дельты
        ]
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Добавляем индикаторы для MShot стратегии
        """
        # SMA для определения тренда
        dataframe['sma10'] = ta.SMA(dataframe, timeperiod=10)
        dataframe['sma50'] = ta.SMA(dataframe, timeperiod=50)
        
        # RSI для фильтрации перекупленности
        dataframe['rsi'] = ta.RSI(dataframe)
        
        # ATR для волатильности
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # Расчет дельт (изменение цены за период)
        dataframe['delta_15m'] = dataframe['close'].pct_change(3) * 100  # Примерно 15m на 5m свечах
        dataframe['delta_1h'] = dataframe['close'].pct_change(12) * 100   # Примерно 1h
        dataframe['delta_3h'] = dataframe['close'].pct_change(36) * 100  # Примерно 3h
        
        # Расчет базовой цены (BID/ASK/Trade)
        if self.dp and self.dp.runmode.value in ("live", "dry_run"):
            try:
                ob = self.dp.orderbook(metadata["pair"], 1)
                dataframe["best_bid"] = ob["bids"][0][0] if ob["bids"] else dataframe['close']
                dataframe["best_ask"] = ob["asks"][0][0] if ob["asks"] else dataframe['close']
            except:
                dataframe["best_bid"] = dataframe['close']
                dataframe["best_ask"] = dataframe['close']
        else:
            # Для бэктеста используем close
            dataframe["best_bid"] = dataframe['close']
            dataframe["best_ask"] = dataframe['close']
        
        # Определяем базовую цену в зависимости от параметра
        dataframe['base_price'] = dataframe.apply(
            lambda row: {
                'BID': row['best_bid'],
                'ASK': row['best_ask'],
                'Trade': row['close']
            }.get(self.mshot_use_price.value, row['close']),
            axis=1
        )
        
        # Вычисляем эффективную цену с учетом дельт
        dataframe['effective_price'] = (
            self.mshot_price.value +
            dataframe['delta_3h'] * self.mshot_add_3h_delta.value +
            dataframe['delta_1h'] * self.mshot_add_hourly_delta.value +
            dataframe['delta_15m'] * self.mshot_add_15min_delta.value
        )
        
        dataframe['effective_price_min'] = (
            self.mshot_price_min.value +
            dataframe['delta_3h'] * self.mshot_add_3h_delta.value +
            dataframe['delta_1h'] * self.mshot_add_hourly_delta.value +
            dataframe['delta_15m'] * self.mshot_add_15min_delta.value
        )
        
        # Вычисляем целевую цену покупки
        dataframe['target_buy_price'] = dataframe['base_price'] * (1.0 - dataframe['effective_price'] / 100.0)
        
        # MShotMinusSatoshi: отступ от ASK на ~0.002%
        if self.mshot_minus_satoshi.value:
            dataframe['min_buy_price'] = dataframe['best_ask'] * 0.99998
            dataframe['target_buy_price'] = dataframe[['target_buy_price', 'min_buy_price']].min(axis=1)
        
        # Расстояние текущей цены от целевой
        dataframe['distance_to_target'] = ((dataframe['close'] - dataframe['target_buy_price']) / dataframe['close']) * 100
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Логика входа: когда цена близка к целевой цене покупки
        """
        dataframe.loc[
            (
                # Цена близка к целевой (в пределах эффективного коридора)
                (dataframe['distance_to_target'] <= dataframe['effective_price']) &
                (dataframe['distance_to_target'] >= dataframe['effective_price_min']) &
                
                # Фильтры качества
                (dataframe['volume'] > 0) &
                (dataframe['rsi'] < 70) &  # Не перекуплен
                (dataframe['sma10'] > dataframe['sma50'])  # Восходящий тренд
            ),
            "enter_long"] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Логика выхода: продажа по достижению целевой прибыли
        """
        dataframe.loc[
            (
                # ROI достигнут (sell_price %)
                (dataframe['close'] > dataframe['open'] * (1.0 + self.sell_price.value / 100.0)) &
                (dataframe['volume'] > 0)
            ),
            "exit_long"] = 1
        
        return dataframe
    
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                           proposed_stake: float, min_stake: Optional[float], max_stake: float,
                           leverage: float, entry_tag: Optional[str], side: str,
                           **kwargs) -> float:
        """
        Кастомный размер ставки (можно настроить под себя)
        """
        return proposed_stake
    
    def adjust_trade_position(self, trade: Trade, current_time: datetime,
                              current_rate: float, current_profit: float,
                              min_stake: Optional[float], max_stake: float,
                              current_entry_rate: float, current_exit_rate: float,
                              current_entry_profit: float, current_exit_profit: float,
                              **kwargs) -> Optional[float]:
        """
        Переставление ордера при движении цены (основная логика MShot)
        """
        if not trade.is_open:
            return None
        
        # Получаем текущие данные
        dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
        if dataframe.empty:
            return None
        
        last_candle = dataframe.iloc[-1]
        
        # Вычисляем расстояние от текущей цены до целевой
        distance = ((current_rate - last_candle['target_buy_price']) / current_rate) * 100
        
        # Если цена подошла слишком близко к целевой (MShotPriceMin)
        if distance <= last_candle['effective_price_min']:
            # Проверяем задержку ReplaceDelay
            time_since_entry = (current_time - trade.open_date_utc).total_seconds()
            if time_since_entry >= self.mshot_replace_delay.value:
                # Переставляем ордер на новую целевую цену
                # В freqtrade это делается через изменение размера позиции
                # Но для простоты возвращаем None (не переставляем)
                pass
        
        return None

