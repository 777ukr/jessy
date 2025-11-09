"""
EMA Short Peak Strategy - Opposite of Pullback Strategy
- Waits for 0.8% price increase within 30 seconds
- Shorts on peaks: 0.8%, 0.5%, 0.3%
- Stop-loss: 0.12%
- Take-profit: 11% less than peak price (calculated from 30s/60s peak)
"""

from freqtrade.strategy.interface import IStrategy
from typing import Dict, List
from pandas import DataFrame
import talib.abstract as ta
import numpy as np
from freqtrade.persistence import Trade

class EMA_ShortPeakStrategy(IStrategy):
    """
    Opposite strategy: Short on peaks (reverse of pullback strategy)
    """
    
    INTERFACE_VERSION = 2
    
    can_short = True
    timeframe = '30s'
    
    # Peak levels (in percentage: 0.8%, 0.5%, 0.3%)
    peak_levels = [0.008, 0.005, 0.003]
    peak_window = 30  # seconds
    
    # Stop-loss and take-profit
    stoploss = 0.0012  # 0.12% stop-loss for short
    take_profit_multiplier = 0.11  # 11% of peak price
    
    # ROI for short (negative values)
    minimal_roi = {
        "0": -0.15,
        "60": -0.10,
        "120": -0.05
    }
    
    trailing_stop = True
    trailing_stop_positive = 0.005
    trailing_stop_positive_offset = 0.01
    trailing_only_offset_is_reached = True
    
    position_adjustment_enable = True
    max_entry_position_adjustment = 3
    
    startup_candle_count = 200
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Add indicators"""
        dataframe['ema_20'] = ta.EMA(dataframe, timeperiod=20)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        
        dataframe['price_change_pct'] = dataframe['close'].pct_change()
        dataframe['rolling_min_30s'] = dataframe['low'].rolling(window=30).min()
        dataframe['rolling_max_30s'] = dataframe['high'].rolling(window=30).max()
        
        # Calculate rise percentage
        dataframe['rise_from_low'] = (dataframe['close'] - dataframe['low']) / dataframe['low']
        
        dataframe['volume_sma'] = ta.SMA(dataframe, timeperiod=20, column='volume')
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry conditions: Detect 0.8% rise and short on peaks"""
        # Primary condition: 0.8% rise detected within 30 seconds
        peak_condition = (
            (dataframe['rise_from_low'] >= self.peak_levels[0]) &  # 0.8% rise
            (dataframe['close'] > dataframe['ema_20']) &  # Above EMA (overbought)
            (dataframe['volume'] > dataframe['volume_sma']) &
            (dataframe['volume'] > 0)
        )
        
        # First entry at 0.8% peak
        dataframe.loc[
            peak_condition &
            (dataframe['close'] >= dataframe['rolling_max_30s'] * (1 - self.peak_levels[0])),
            'enter_short'] = 1
        
        return dataframe
    
    def adjust_trade_position(self, trade: Trade, current_time, current_rate,
                            current_profit, min_stake, max_stake, **kwargs):
        """DCA: Add positions at 0.5% and 0.3% peaks"""
        if current_profit > 0:
            return None
        
        if trade.nr_of_successful_entries < len(self.peak_levels):
            entry_rate = trade.open_rate
            rise_pct = (current_rate - entry_rate) / entry_rate
            
            if trade.nr_of_successful_entries == 1:
                if rise_pct >= self.peak_levels[1]:
                    return min_stake
            elif trade.nr_of_successful_entries == 2:
                if rise_pct >= self.peak_levels[2]:
                    return min_stake
        
        return None
    
    def custom_stoploss(self, pair: str, trade: Trade, current_time, current_rate,
                       current_profit, after_fill, **kwargs):
        """Custom stop-loss: 0.12%"""
        return self.stoploss
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit conditions"""
        dataframe.loc[
            (
                (dataframe['close'] < dataframe['ema_20']) &
                (dataframe['close'] < dataframe['ema_50'])
            ),
            'exit_short'] = 1
        
        return dataframe




