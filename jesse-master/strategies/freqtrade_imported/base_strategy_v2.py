"""
Base Strategy V2 - Enhanced strategy base class inspired by Hummingbot architecture
Provides modular entry/exit filters, risk management, and auto-switching capabilities
"""

from typing import List, Callable, Optional, Dict, Any
from decimal import Decimal
from freqtrade.strategy import IStrategy, DataFrame

try:
    import pandas as pd
    import numpy as np
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    pd = None
    np = None


class BaseStrategyV2(IStrategy):
    """
    Enhanced base strategy with Hummingbot-inspired architecture:
    - Modular entry/exit filters
    - Risk management integration
    - Auto-switching between long/short strategies
    - Configurable conditions
    """
    
    # Strategy configuration
    timeframe = '5m'
    stoploss = -0.10  # -10% default
    
    # Auto-switching configuration
    auto_switch_enabled = False  # Enable auto-switching to opposite strategy
    switch_threshold = -0.20  # Switch when total PnL reaches -20%
    opposite_strategy: Optional[str] = None  # Name of opposite strategy (e.g., "EMA_ShortPeakStrategy")
    
    # Entry/Exit filter system
    entry_filters: List[Callable] = []
    exit_conditions: List[Callable] = []
    
    # Risk management
    max_position_size: float = 1.0  # Maximum position size (1.0 = 100% of capital)
    max_drawdown_pct: float = 0.20  # Maximum drawdown before disabling strategy
    
    def __init__(self, config: dict) -> None:
        """
        Initialize strategy with filters and conditions
        
        Args:
            config: Freqtrade strategy configuration
        """
        super().__init__(config)
        self.entry_filters = []
        self.exit_conditions = []
        self._total_pnl = 0.0  # Track total PnL for auto-switching
        self._is_disabled = False  # Flag to disable strategy if needed
    
    def add_entry_filter(self, condition: Callable[[DataFrame], DataFrame]) -> None:
        """
        Add an entry condition filter
        
        Args:
            condition: Function that takes DataFrame and returns filtered DataFrame
                      Should set 'enter_long' or 'enter_short' columns
        """
        self.entry_filters.append(condition)
    
    def add_exit_condition(self, condition: Callable[[DataFrame], DataFrame]) -> None:
        """
        Add an exit condition
        
        Args:
            condition: Function that takes DataFrame and returns DataFrame
                      Should set 'exit_long' or 'exit_short' columns
        """
        self.exit_conditions.append(condition)
    
    def should_switch_to_opposite(self, current_pnl: float) -> bool:
        """
        Check if should switch to opposite strategy
        
        Args:
            current_pnl: Current total PnL as decimal (e.g., -0.20 for -20%)
            
        Returns:
            True if should switch, False otherwise
        """
        if not self.auto_switch_enabled:
            return False
        
        if self.opposite_strategy is None:
            return False
        
        # Check if PnL reached switch threshold
        if current_pnl <= self.switch_threshold:
            return True
        
        return False
    
    def check_risk_limits(self, dataframe: DataFrame, current_price: float) -> DataFrame:
        """
        Apply risk management limits to dataframe
        
        Args:
            dataframe: OHLCV DataFrame
            current_price: Current market price
            
        Returns:
            DataFrame with risk limits applied
        """
        # Check max position size
        if 'position_size' not in dataframe.columns:
            dataframe['position_size'] = 1.0
        
        dataframe.loc[dataframe['position_size'] > self.max_position_size, 'position_size'] = self.max_position_size
        
        # Check max drawdown
        if 'drawdown' in dataframe.columns:
            dataframe.loc[dataframe['drawdown'] > self.max_drawdown_pct, 'enter_long'] = False
            dataframe.loc[dataframe['drawdown'] > self.max_drawdown_pct, 'enter_short'] = False
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate entry signals with applied filters
        
        Args:
            dataframe: OHLCV DataFrame
            metadata: Pair metadata
            
        Returns:
            DataFrame with entry signals
        """
        # Initialize columns
        if 'enter_long' not in dataframe.columns:
            dataframe['enter_long'] = False
        if 'enter_short' not in dataframe.columns:
            dataframe['enter_short'] = False
        
        # If strategy is disabled, don't enter
        if self._is_disabled:
            dataframe['enter_long'] = False
            dataframe['enter_short'] = False
            return dataframe
        
        # Apply entry filters
        for filter_func in self.entry_filters:
            dataframe = filter_func(dataframe)
        
        # Apply risk management
        if hasattr(self, 'check_risk_limits'):
            current_price = dataframe['close'].iloc[-1] if len(dataframe) > 0 else 0
            dataframe = self.check_risk_limits(dataframe, current_price)
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate exit signals with applied conditions
        
        Args:
            dataframe: OHLCV DataFrame
            metadata: Pair metadata
            
        Returns:
            DataFrame with exit signals
        """
        # Initialize columns
        if 'exit_long' not in dataframe.columns:
            dataframe['exit_long'] = False
        if 'exit_short' not in dataframe.columns:
            dataframe['exit_short'] = False
        
        # Apply exit conditions
        for condition_func in self.exit_conditions:
            dataframe = condition_func(dataframe)
        
        return dataframe
    
    def custom_exit(self, pair: str, trade, current_time, current_rate, current_profit, **kwargs) -> Optional[str]:
        """
        Custom exit logic with auto-switching support
        
        Args:
            pair: Trading pair
            trade: Current trade object
            current_time: Current time
            current_rate: Current rate
            current_profit: Current profit percentage
            
        Returns:
            Exit reason string or None
        """
        # Update total PnL
        self._total_pnl += current_profit
        
        # Check if should switch to opposite strategy
        if self.should_switch_to_opposite(self._total_pnl):
            # Disable current strategy
            self._is_disabled = True
            # Note: Actual switching should be handled by live_simulation_engine
            return f"auto_switch_to_{self.opposite_strategy}"
        
        # Check if exceeded max drawdown
        if self._total_pnl <= -self.max_drawdown_pct:
            self._is_disabled = True
            return "max_drawdown_exceeded"
        
        return None
    
    def reset_pnl(self) -> None:
        """Reset total PnL tracking (useful when switching strategies)"""
        self._total_pnl = 0.0
        self._is_disabled = False
    
    def get_total_pnl(self) -> float:
        """Get current total PnL"""
        return self._total_pnl
    
    def is_disabled(self) -> bool:
        """Check if strategy is disabled"""
        return self._is_disabled


# Example filter functions that can be used with BaseStrategyV2

def ema_crossover_filter(ema_fast: int = 9, ema_slow: int = 21) -> Callable:
    """
    Create an EMA crossover entry filter
    
    Args:
        ema_fast: Fast EMA period
        ema_slow: Slow EMA period
        
    Returns:
        Filter function
    """
    if not PANDAS_AVAILABLE:
        raise ImportError("pandas is required for EMA crossover filter")
    
    def filter_func(dataframe: DataFrame) -> DataFrame:
        dataframe[f'ema_{ema_fast}'] = dataframe['close'].ewm(span=ema_fast).mean()
        dataframe[f'ema_{ema_slow}'] = dataframe['close'].ewm(span=ema_slow).mean()
        
        # Long entry when fast EMA crosses above slow EMA
        dataframe.loc[
            (dataframe[f'ema_{ema_fast}'] > dataframe[f'ema_{ema_slow}']) &
            (dataframe[f'ema_{ema_fast}'].shift(1) <= dataframe[f'ema_{ema_slow}'].shift(1)),
            'enter_long'
        ] = True
        
        # Short entry when fast EMA crosses below slow EMA
        dataframe.loc[
            (dataframe[f'ema_{ema_fast}'] < dataframe[f'ema_{ema_slow}']) &
            (dataframe[f'ema_{ema_fast}'].shift(1) >= dataframe[f'ema_{ema_slow}'].shift(1)),
            'enter_short'
        ] = True
        
        return dataframe
    
    return filter_func


def rsi_oversold_filter(rsi_period: int = 14, oversold_level: int = 30) -> Callable:
    """
    Create an RSI oversold entry filter
    
    Args:
        rsi_period: RSI period
        oversold_level: RSI level considered oversold
        
    Returns:
        Filter function
    """
    def filter_func(dataframe: DataFrame) -> DataFrame:
        # Calculate RSI
        delta = dataframe['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        rs = gain / loss
        dataframe['rsi'] = 100 - (100 / (1 + rs))
        
        # Long entry when RSI is oversold
        dataframe.loc[dataframe['rsi'] < oversold_level, 'enter_long'] = True
        
        return dataframe
    
    return filter_func


def volume_spike_filter(volume_multiplier: float = 1.5) -> Callable:
    """
    Create a volume spike filter
    
    Args:
        volume_multiplier: Multiplier for average volume
        
    Returns:
        Filter function
    """
    def filter_func(dataframe: DataFrame) -> DataFrame:
        avg_volume = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_spike'] = dataframe['volume'] > (avg_volume * volume_multiplier)
        
        # Only enter on volume spikes
        dataframe.loc[~dataframe['volume_spike'], 'enter_long'] = False
        dataframe.loc[~dataframe['volume_spike'], 'enter_short'] = False
        
        return dataframe
    
    return filter_func

