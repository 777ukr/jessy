# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
"""
Advanced Indicator Strategy - Стратегия с множеством технических индикаторов
Основана на стратегии с hash: 83badbcc97221e69320c2c680455cddc9065bde29048fff1ffb467350cd79510
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


class AdvancedIndicatorStrategy(IStrategy):
    """
    Продвинутая стратегия с множеством технических индикаторов
    
    Индикаторы:
    - VWAP, RSI (fast, RMI, MFI)
    - Donchian Channels (DC)
    - Bollinger Bands (BB)
    - Ichimoku (Senkou Span A/B)
    - KAMA, EMA, ZEMA
    - Volume indicators
    - Trend indicators (4h, 15m, 6h)
    """
    
    INTERFACE_VERSION = 3
    timeframe = "5m"
    can_short: bool = False
    
    # ROI и Stoploss
    minimal_roi = {
        "0": 0.02
    }
    
    stoploss = -0.11  # Как указано в параметрах
    
    trailing_stop = False
    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    
    startup_candle_count: int = 100
    
    def informative_pairs(self):
        """
        Добавляем дополнительные таймфреймы для трендов
        """
        return [
            ("BTC/USDT", "15m"),
            ("BTC/USDT", "4h"),
            ("BTC/USDT", "6h"),
        ]
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Заполняем все необходимые индикаторы
        """
        # === RSI индикаторы ===
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['rsi_fast'] = ta.RSI(dataframe, timeperiod=7)
        
        # RSI RMI (Relative Momentum Index)
        rmi_length = 14
        dataframe['rsi_rmi_length'] = dataframe['rsi']
        dataframe['rsi_mfi_rmi_length'] = ta.MFI(dataframe, timeperiod=14)
        
        # FastK RSI
        dataframe['fastk_rsi'] = ta.STOCHF(dataframe, fastk_period=5, fastd_period=3)['fastk']
        
        # === Moving Averages ===
        dataframe['ema_5'] = ta.EMA(dataframe, timeperiod=5)
        dataframe['zema_30'] = ta.EMA(dataframe, timeperiod=30)  # ZEMA как EMA
        dataframe['basis_ma_period_rsi_period'] = ta.SMA(dataframe, timeperiod=20)
        
        # KAMA (Kaufman Adaptive Moving Average)
        dataframe['high_offset_kama'] = ta.KAMA(dataframe, timeperiod=14)
        
        # === VWAP ===
        dataframe['vwap_high'] = qtpylib.rolling_vwap(dataframe)  # Используем rolling_vwap для избежания lookahead bias
        
        # === Donchian Channels ===
        period = 20
        dataframe['dc_mid'] = (dataframe['high'].rolling(period).max() + dataframe['low'].rolling(period).min()) / 2
        dataframe['dc_upper'] = dataframe['high'].rolling(period).max()
        dataframe['dc_lower'] = dataframe['low'].rolling(period).min()
        dataframe['dc_lf'] = dataframe['dc_lower']  # Lower filter
        dataframe['dca_buy_signal2'] = (dataframe['close'] > dataframe['dc_lower']).astype(int)
        
        # === Bollinger Bands ===
        bb_period = 20
        bb_std = 2
        bollinger = qtpylib.bollinger_bands(dataframe['close'], window=bb_period, stds=bb_std)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_lowerband2'] = bollinger['lower'] * 0.99
        dataframe['bb_lowerband3'] = bollinger['lower'] * 0.98
        dataframe['bb_up'] = bollinger['upper']
        dataframe['bb_mid'] = bollinger['mid']
        
        # === Ichimoku ===
        # Вычисляем компоненты Ichimoku вручную
        period1 = 9
        period2 = 26
        period3 = 52
        
        # Tenkan-sen (Conversion Line)
        tenkan_high = dataframe['high'].rolling(period1).max()
        tenkan_low = dataframe['low'].rolling(period1).min()
        tenkan_sen = (tenkan_high + tenkan_low) / 2
        
        # Kijun-sen (Base Line)
        kijun_high = dataframe['high'].rolling(period2).max()
        kijun_low = dataframe['low'].rolling(period2).min()
        kijun_sen = (kijun_high + kijun_low) / 2
        
        # Senkou Span A (Leading Span A)
        dataframe['senkou_span_a'] = ((tenkan_sen + kijun_sen) / 2).shift(period2)
        dataframe['senkou_a'] = dataframe['senkou_span_a']
        
        # Senkou Span B (Leading Span B)
        senkou_b_high = dataframe['high'].rolling(period3).max()
        senkou_b_low = dataframe['low'].rolling(period3).min()
        dataframe['senkou_span_b'] = ((senkou_b_high + senkou_b_low) / 2).shift(period2)
        dataframe['senkou_b'] = dataframe['senkou_span_b']
        
        # === Volume indicators ===
        dataframe['avg_vol'] = dataframe['volume'].rolling(20).mean()
        dataframe['low_vol'] = (dataframe['volume'] < dataframe['avg_vol'] * 0.5).astype(int)
        dataframe['avg_rsi'] = dataframe['rsi'].rolling(14).mean()
        
        # === Momentum indicators ===
        dataframe['close_delta'] = dataframe['close'].diff()
        dataframe['closedelta'] = dataframe['close'].diff()
        dataframe['down_rmi_length'] = -dataframe['close'].pct_change(14)
        dataframe['negative_pmom_nmom_prev'] = -dataframe['close'].pct_change(1)
        dataframe['ema_5_pmom_nmom'] = dataframe['ema_5'].pct_change(1)
        
        # === Dispersion ===
        ma_period = 20
        rsi_period = 14
        stdev_multiplier = 2.0
        dataframe['basis'] = dataframe['close'].rolling(ma_period).mean()
        dataframe['stdev'] = dataframe['close'].rolling(ma_period).std()
        dataframe['disp_up_ma_period_rsi_period_stdev_multiplier_dispersion'] = (
            (dataframe['close'] - dataframe['basis']) / dataframe['stdev'] * stdev_multiplier
        )
        
        # === Trend indicators (4h, 15m, 6h) ===
        # Используем информативные пары для расчета трендов
        if self.dp:
            try:
                # 4h тренд
                inf_4h = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe='4h')
                if not inf_4h.empty:
                    dataframe['trend_open_4h'] = inf_4h['open'].iloc[-1] if len(inf_4h) > 0 else dataframe['open']
                    dataframe['trend_close_4h'] = inf_4h['close'].iloc[-1] if len(inf_4h) > 0 else dataframe['close']
                
                # 15m тренд
                inf_15m = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe='15m')
                if not inf_15m.empty:
                    dataframe['trend_open_15m'] = inf_15m['open'].iloc[-1] if len(inf_15m) > 0 else dataframe['open']
                    dataframe['trend_close_15m'] = inf_15m['close'].iloc[-1] if len(inf_15m) > 0 else dataframe['close']
                
                # 6h тренд
                inf_6h = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe='6h')
                if not inf_6h.empty:
                    dataframe['trend_open_6h'] = inf_6h['open'].iloc[-1] if len(inf_6h) > 0 else dataframe['open']
            except:
                pass
        
        # Если не удалось получить, используем текущие значения
        if 'trend_open_4h' not in dataframe.columns:
            dataframe['trend_open_4h'] = dataframe['open']
            dataframe['trend_close_4h'] = dataframe['close']
        if 'trend_open_15m' not in dataframe.columns:
            dataframe['trend_open_15m'] = dataframe['open']
            dataframe['trend_close_15m'] = dataframe['close']
        if 'trend_open_6h' not in dataframe.columns:
            dataframe['trend_open_6h'] = dataframe['open']
        
        # === Дополнительные сигналы ===
        dataframe['low_rsi'] = (dataframe['rsi'] < 30).astype(int)
        dataframe['silence_silence'] = 0  # Placeholder
        
        # DSL Level (Dynamic Support/Resistance Level)
        dataframe['dsl_lvld'] = dataframe['close'].rolling(20).min()
        
        # Lower trend
        dataframe['lower'] = dataframe['low'].rolling(20).min()
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Логика входа на основе множества индикаторов
        """
        dataframe.loc[
            (
                # Bollinger Bands сигналы
                (dataframe['close'] < dataframe['bb_lowerband3']) |
                (dataframe['close'] < dataframe['bb_lowerband2']) |
                
                # Donchian Channels
                (dataframe['dca_buy_signal2'] == 1) |
                (dataframe['close'] > dataframe['dc_lower']) |
                
                # RSI сигналы
                (dataframe['low_rsi'] == 1) |
                (dataframe['rsi'] < 30) |
                (dataframe['rsi_fast'] < 25) |
                
                # Трендовые сигналы
                (dataframe['trend_close_4h'] > dataframe['trend_open_4h']) |
                (dataframe['trend_close_15m'] > dataframe['trend_open_15m']) |
                
                # Volume подтверждение
                (dataframe['volume'] > dataframe['avg_vol'] * 0.8) &
                
                # Общие фильтры
                (dataframe['volume'] > 0) &
                (dataframe['close'] > dataframe['dc_lower'])
            ),
            "enter_long"] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Логика выхода
        """
        dataframe.loc[
            (
                # Bollinger Bands верхняя граница
                (dataframe['close'] > dataframe['bb_up']) |
                
                # RSI перекупленность
                (dataframe['rsi'] > 70) |
                (dataframe['rsi_fast'] > 75) |
                
                # Donchian Channels верхняя граница
                (dataframe['close'] > dataframe['dc_upper']) |
                
                # Трендовые сигналы
                (dataframe['trend_close_4h'] < dataframe['trend_open_4h']) |
                
                # Volume фильтр
                (dataframe['volume'] > 0)
            ),
            "exit_long"] = 1
        
        return dataframe

