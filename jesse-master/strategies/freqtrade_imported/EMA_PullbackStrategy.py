"""
EMA Pullback Strategy - Custom EMA strategy with pullback rules
- Waits for 0.8% price drop within 30 seconds
- Buys on pullbacks: 0.8%, 0.5%, 0.3%
- Stop-loss: 0.12%
- Take-profit: 11% less than drop price (calculated from 30s/60s drop)
"""

from freqtrade.strategy.interface import IStrategy
from typing import Dict, List
from pandas import DataFrame
import talib.abstract as ta
import numpy as np
from freqtrade.persistence import Trade

class EMA_PullbackStrategy(IStrategy):
    """
    Custom EMA strategy with pullback detection and DCA entry
    """
    
    INTERFACE_VERSION = 2
    
    # Strategy parameters
    timeframe = '30s'  # 30-second candles for precise entry
    
    # Pullback levels (in percentage: 0.8%, 0.5%, 0.3%)
    pullback_levels = [0.008, 0.005, 0.003]
    pullback_window = 30  # seconds to detect drop
    
    # Stop-loss and take-profit
    stoploss = -0.0012  # 0.12% stop-loss
    take_profit_multiplier = 0.11  # 11% of drop price
    
    # ROI - dynamic based on drop
    minimal_roi = {
        "0": 0.15,   # 15% default
        "60": 0.10,  # 10% after 1 minute
        "120": 0.05  # 5% after 2 minutes
    }
    
    # Trailing stop
    trailing_stop = True
    trailing_stop_positive = 0.005
    trailing_stop_positive_offset = 0.01
    trailing_only_offset_is_reached = True
    
    # Position adjustment (DCA)
    position_adjustment_enable = True
    max_entry_position_adjustment = 3  # Max 3 entries (0.8%, 0.5%, 0.3%)
    
    # Indicators
    startup_candle_count = 200
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Add indicators"""
        # EMA for trend detection
        dataframe['ema_20'] = ta.EMA(dataframe, timeperiod=20)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        
        # Price change percentage (for pullback detection)
        dataframe['price_change_pct'] = dataframe['close'].pct_change()
        
        # Rolling min/max for pullback detection
        dataframe['rolling_min_30s'] = dataframe['low'].rolling(window=30).min()
        dataframe['rolling_max_30s'] = dataframe['high'].rolling(window=30).max()
        
        # Calculate drop percentage
        dataframe['drop_from_high'] = (dataframe['high'] - dataframe['close']) / dataframe['high']
        
        # Volume for confirmation
        dataframe['volume_sma'] = ta.SMA(dataframe, timeperiod=20, column='volume')
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry conditions: Detect 0.8% drop and buy on pullbacks"""
        conditions = []
        
        # Primary condition: 0.8% drop detected within 30 seconds
        drop_condition = (
            (dataframe['drop_from_high'] >= self.pullback_levels[0]) &  # 0.8% drop
            (dataframe['close'] < dataframe['ema_20']) &  # Below EMA (oversold)
            (dataframe['volume'] > dataframe['volume_sma']) &  # Volume confirmation
            (dataframe['volume'] > 0)
        )
        
        # First entry at 0.8% pullback
        conditions.append(
            drop_condition &
            (dataframe['close'] <= dataframe['rolling_min_30s'] * (1 + self.pullback_levels[0]))
        )
        
        # Additional entries at 0.5% and 0.3% (DCA)
        # These will be handled by position_adjustment_enable
        
        if conditions:
            dataframe.loc[conditions[0], 'buy'] = 1
        
        return dataframe
    
    def adjust_trade_position(self, trade: Trade, current_time, current_rate,
                            current_profit, min_stake, max_stake, **kwargs):
        """DCA: Add positions at 0.5% and 0.3% pullbacks"""
        if current_profit > 0:
            return None  # Don't add if already profitable
        
        # Check if we should add more positions
        if trade.nr_of_successful_entries < len(self.pullback_levels):
            # Calculate drop from entry
            entry_rate = trade.open_rate
            drop_pct = (entry_rate - current_rate) / entry_rate
            
            # Check if price dropped to next pullback level
            if trade.nr_of_successful_entries == 1:
                # Add at 0.5%
                if drop_pct >= self.pullback_levels[1]:
                    return min_stake
            elif trade.nr_of_successful_entries == 2:
                # Add at 0.3%
                if drop_pct >= self.pullback_levels[2]:
                    return min_stake
        
        return None
    
    def custom_stoploss(self, pair: str, trade: Trade, current_time, current_rate,
                       current_profit, after_fill, **kwargs):
        """Custom stop-loss: 0.12%"""
        return self.stoploss
    
    def custom_exit(self, pair: str, trade: Trade, current_time, current_rate,
                    current_profit, **kwargs):
        """Custom exit: Calculate take-profit based on drop"""
        # Get entry rate
        entry_rate = trade.open_rate
        
        # Calculate the drop that triggered entry
        # This is stored in trade metadata or calculated from entry
        if hasattr(trade, 'metadata') and 'entry_drop' in trade.metadata:
            entry_drop = trade.metadata['entry_drop']
        else:
            # Estimate drop from entry (assuming 0.8% minimum)
            entry_drop = 0.008
        
        # Calculate take-profit: 11% less than drop price
        take_profit_pct = entry_drop * self.take_profit_multiplier
        
        # Check if we've reached take-profit
        if current_profit >= take_profit_pct:
            return 'take_profit_reached'
        
        return None
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit conditions"""
        dataframe.loc[
            (
                # Price recovered above EMA
                (dataframe['close'] > dataframe['ema_20']) &
                (dataframe['close'] > dataframe['ema_50'])
            ),
            'sell'] = 1
        
        return dataframe




