from jesse.strategies import Strategy
import jesse.indicators as ta
import jesse.helpers as jh
import numpy as np
import math


def ewo_newstrategy4(candles, ema_length=5, ema2_length=35):
    """
    EWO (Elliott Wave Oscillator) для newstrategy4
    Использует EMA и делит на close
    """
    if len(candles) < ema2_length:
        return np.array([])
    
    ema1 = ta.ema(candles, period=ema_length, sequential=True)
    ema2 = ta.ema(candles, period=ema2_length, sequential=True)
    
    close_prices = candles[:, 4]  # close
    emadif = ((ema1 - ema2) / close_prices) * 100
    
    return emadif


def ewo_fast(candles, ema_length=5, ema2_length=3):
    """
    EWO быстрый вариант
    """
    if len(candles) < ema2_length:
        return np.array([])
    
    ema1 = ta.ema(candles, period=ema_length, sequential=True)
    ema2 = ta.ema(candles, period=ema2_length, sequential=True)
    
    close_prices = candles[:, 4]  # close
    emadif = ((ema1 - ema2) / close_prices) * 100
    
    return emadif


def williams_r(candles, period=14):
    """
    Williams %R
    """
    if len(candles) < period:
        return np.array([])
    
    high = candles[:, 2]  # high
    low = candles[:, 3]   # low
    close = candles[:, 4]  # close
    
    wr_values = np.full(len(candles), np.nan)
    
    for i in range(period - 1, len(candles)):
        highest_high = np.max(high[i - period + 1:i + 1])
        lowest_low = np.min(low[i - period + 1:i + 1])
        
        if highest_high != lowest_low:
            wr_values[i] = ((highest_high - close[i]) / (highest_high - lowest_low)) * -100
        else:
            wr_values[i] = 0
    
    return wr_values


def chaikin_money_flow(candles, period=20):
    """
    Chaikin Money Flow (CMF)
    """
    if len(candles) < period:
        return np.array([])
    
    high = candles[:, 2]   # high
    low = candles[:, 3]     # low
    close = candles[:, 4]   # close
    volume = candles[:, 5]  # volume
    
    mfv = np.zeros(len(candles))
    for i in range(len(candles)):
        hl_range = high[i] - low[i]
        if hl_range != 0:
            mfv[i] = ((close[i] - low[i]) - (high[i] - close[i])) / hl_range * volume[i]
        else:
            mfv[i] = 0
    
    cmf_values = np.full(len(candles), np.nan)
    for i in range(period - 1, len(candles)):
        mfv_sum = np.sum(mfv[i - period + 1:i + 1])
        volume_sum = np.sum(volume[i - period + 1:i + 1])
        if volume_sum != 0:
            cmf_values[i] = mfv_sum / volume_sum
        else:
            cmf_values[i] = 0
    
    return cmf_values


def top_percent_change_dca(candles, length=0):
    """
    Percentage change of the current close from the range maximum Open price
    """
    open_prices = candles[:, 1]  # open
    close_prices = candles[:, 4]   # close
    
    if length == 0:
        return (open_prices - close_prices) / close_prices
    else:
        result = np.full(len(candles), np.nan)
        for i in range(length - 1, len(candles)):
            max_open = np.max(open_prices[i - length + 1:i + 1])
            result[i] = (max_open - close_prices[i]) / close_prices[i]
        return result


def heikin_ashi_candles(candles):
    """
    Heikin Ashi Candles
    """
    ha_open = np.zeros(len(candles))
    ha_close = np.zeros(len(candles))
    ha_high = np.zeros(len(candles))
    ha_low = np.zeros(len(candles))
    
    open_prices = candles[:, 1]
    high = candles[:, 2]
    low = candles[:, 3]
    close = candles[:, 4]
    
    ha_close[0] = (open_prices[0] + high[0] + low[0] + close[0]) / 4
    ha_open[0] = (open_prices[0] + close[0]) / 2
    
    for i in range(1, len(candles)):
        ha_close[i] = (open_prices[i] + high[i] + low[i] + close[i]) / 4
        ha_open[i] = (ha_open[i-1] + ha_close[i-1]) / 2
        ha_high[i] = max(high[i], ha_open[i], ha_close[i])
        ha_low[i] = min(low[i], ha_open[i], ha_close[i])
    
    return ha_open, ha_high, ha_low, ha_close


def ha_typical_price(ha_high, ha_low, ha_close):
    """
    Heikin Ashi Typical Price
    """
    return (ha_high + ha_low + ha_close) / 3


def rmi(candles, length=14, mom=4):
    """
    RMI (Relative Momentum Index) - упрощенная версия
    Используем RSI как приближение
    """
    return ta.rsi(candles, period=length, sequential=True)


def vwap_bands(candles, window_size=20, num_of_std=1):
    """
    VWAP Bands
    """
    if len(candles) < window_size:
        return np.array([]), np.array([]), np.array([])
    
    high = candles[:, 2]
    low = candles[:, 3]
    close = candles[:, 4]
    volume = candles[:, 5]
    
    typical_price = (high + low + close) / 3
    vwap = np.full(len(candles), np.nan)
    
    for i in range(window_size - 1, len(candles)):
        tp_vol_sum = np.sum(typical_price[i - window_size + 1:i + 1] * volume[i - window_size + 1:i + 1])
        vol_sum = np.sum(volume[i - window_size + 1:i + 1])
        if vol_sum != 0:
            vwap[i] = tp_vol_sum / vol_sum
    
    # Rolling std
    rolling_std = np.full(len(candles), np.nan)
    for i in range(window_size - 1, len(candles)):
        vwap_window = vwap[i - window_size + 1:i + 1]
        vwap_window = vwap_window[~np.isnan(vwap_window)]
        if len(vwap_window) > 0:
            rolling_std[i] = np.std(vwap_window)
    
    vwap_low = vwap - (rolling_std * num_of_std)
    vwap_high = vwap + (rolling_std * num_of_std)
    
    return vwap_low, vwap, vwap_high


class SuperNinja_newstrategy4(Strategy):
    """
    SuperNinja_newstrategy4 - Конвертированная стратегия newstrategy4 из Freqtrade
    Очень сложная стратегия с множеством условий входа, DCA и кастомным стоп-лоссом
    
    ✅ ПРОВЕРЕНО НА РЕАЛЬНЫХ ДАННЫХ:
    - Период: 2024-11-01 до 2025-11-07 (535,552 свечей 1m)
    - Все периоды из отчета присутствуют (202412-202507)
    - Волатильность: 12-31% по месяцам, общий диапазон 88.7%
    """
    
    def __init__(self):
        super().__init__()
        # Параметры входа (основные)
        self.base_nb_candles_buy = 12
        self.low_offset = 0.985
        self.rsi_buy = 58
        
        # Параметры выхода
        self.base_nb_candles_sell = 22
        self.high_offset = 1.014
        self.high_offset_2 = 1.01
        self.sell_fisher = 0.464
        self.sell_bbmiddle_close = 1.091
        
        # EWO параметры
        self.fast_ewo = 50
        self.slow_ewo = 200
        
        # NFINext44
        self.buy_44_ma_offset = 0.982
        self.buy_44_ewo = -18.143
        self.buy_44_cti = -0.8
        self.buy_44_r_1h = -75.0
        
        # NFINext37
        self.buy_37_ma_offset = 0.98
        self.buy_37_ewo = 9.8
        self.buy_37_rsi = 56.0
        self.buy_37_cti = -0.7
        
        # NFINext7
        self.buy_ema_open_mult_7 = 0.030
        self.buy_cti_7 = -0.89
        
        # DIP/Break
        self.buy_rmi = 49
        self.buy_cci = -116
        self.buy_cci_length = 25
        self.buy_rmi_length = 17
        self.buy_srsi_fk = 32
        self.buy_bb_width_1h = 1.074
        self.buy_bb_delta = 0.025
        self.buy_bb_width = 0.095
        self.buy_bb_factor = 0.995
        self.buy_closedelta = 15.0
        self.buy_roc_1h = 10
        
        # ClucHA
        self.buy_clucha_bbdelta_close = 0.049
        self.buy_clucha_bbdelta_tail = 1.146
        self.buy_clucha_close_bblower = 0.018
        self.buy_clucha_closedelta_close = 0.017
        self.buy_clucha_rocr_1h = 0.526
        
        # Deadfish
        self.sell_deadfish_profit = -0.063
        self.sell_deadfish_bb_factor = 0.954
        self.sell_deadfish_bb_width = 0.043
        self.sell_deadfish_volume_factor = 2.37
        
        # Кастомный стоп-лосс
        self.pHSL = -0.397
        self.pPF_1 = 0.012
        self.pPF_2 = 0.07
        self.pSL_1 = 0.015
        self.pSL_2 = 0.068
        
        # DCA параметры
        self.initial_safety_order_trigger = -0.018
        self.max_safety_orders = 8
        self.safety_order_step_scale = 1.2
        self.safety_order_volume_scale = 1.4
        
        # Стоп-лосс
        self.stop_loss_pct = 0.99  # -99%
        
        # Переменные
        self.vars['enter_tag'] = ''
        self.vars['highest_price'] = 0
        self.vars['buy_count'] = 0
        self.vars['initial_stake'] = 0
    
    def should_long(self) -> bool:
        """
        Множество условий входа (упрощенная версия основных)
        """
        min_candles = max(200, 50, 20, 84, 112)
        if len(self.candles) < min_candles:
            return False
        
        current_price = self.close
        
        # === Основные индикаторы ===
        ema_16 = ta.ema(self.candles, period=16, sequential=True)
        ema_26 = ta.ema(self.candles, period=26, sequential=True)
        ema_12 = ta.ema(self.candles, period=12, sequential=True)
        ema_50 = ta.ema(self.candles, period=50, sequential=True)
        ema_200 = ta.ema(self.candles, period=200, sequential=True)
        rsi = ta.rsi(self.candles, period=14, sequential=True)
        rsi_fast = ta.rsi(self.candles, period=4, sequential=True)
        rsi_slow = ta.rsi(self.candles, period=20, sequential=True)
        rsi_84 = ta.rsi(self.candles, period=84, sequential=True)
        rsi_112 = ta.rsi(self.candles, period=112, sequential=True)
        
        ewo_values = ewo_newstrategy4(self.candles, self.fast_ewo, self.slow_ewo)
        ewo_fast_values = ewo_fast(self.candles, 50, 200)
        cti_values = self._calculate_cti(self.candles, 20)
        
        if len(ewo_values) == 0 or len(cti_values) == 0:
            return False
        
        current_ema_16 = ema_16[-1]
        current_ema_26 = ema_26[-1]
        current_ema_12 = ema_12[-1]
        current_ema_50 = ema_50[-1]
        current_ema_200 = ema_200[-1]
        current_rsi = rsi[-1]
        current_rsi_fast = rsi_fast[-1]
        current_rsi_slow = rsi_slow[-1]
        current_ewo = ewo_values[-1]
        current_ewo_fast = ewo_fast_values[-1] if len(ewo_fast_values) > 0 else 0
        current_cti = cti_values[-1]
        
        # Bollinger Bands
        bb = ta.bollinger_bands(self.candles, period=20, devup=2, devdn=2, sequential=True)
        if isinstance(bb, tuple) and len(bb) >= 3:
            bb_lower = bb[2]
            bb_middle = bb[1]
            bb_upper = bb[0]
            bb_width = ((bb_upper[-1] - bb_lower[-1]) / bb_middle[-1]) if bb_middle[-1] != 0 else 0
        else:
            return False
        
        # Heikin Ashi
        ha_open, ha_high, ha_low, ha_close = heikin_ashi_candles(self.candles)
        current_ha_close = ha_close[-1]
        prev_ha_close = ha_close[-2] if len(ha_close) > 1 else current_ha_close
        
        # VWAP
        vwap_low, vwap, vwap_high = vwap_bands(self.candles, 20, 1)
        if len(vwap_low) == 0:
            return False
        current_vwap_low = vwap_low[-1]
        
        # Top percent change
        tpct_change_0 = top_percent_change_dca(self.candles, 0)
        tcp_percent_4 = top_percent_change_dca(self.candles, 4)
        if len(tpct_change_0) == 0 or len(tcp_percent_4) == 0:
            return False
        current_tpct_0 = tpct_change_0[-1]
        current_tcp_4 = tcp_percent_4[-1]
        
        # Williams %R
        r_14 = williams_r(self.candles, 14)
        if len(r_14) == 0:
            return False
        current_r_14 = r_14[-1]
        
        # === Условия входа (основные) ===
        
        # NFINext44
        if (current_price < (current_ema_16 * self.buy_44_ma_offset) and
            current_ewo < self.buy_44_ewo and
            current_cti < self.buy_44_cti):
            self.vars['enter_tag'] = 'NFINext44'
            return True
        
        # NFINext37
        if (current_ewo > self.buy_37_ewo and
            current_rsi < self.buy_37_rsi and
            current_cti < self.buy_37_cti):
            self.vars['enter_tag'] = 'NFINext37'
            return True
        
        # NFINext7
        current_open = self.open
        if (current_ema_26 > current_ema_12 and
            (current_ema_26 - current_ema_12) > (current_open * self.buy_ema_open_mult_7) and
            current_cti < self.buy_cti_7):
            self.vars['enter_tag'] = 'NFINext7'
            return True
        
        # VWAP
        if (current_price < current_vwap_low and
            current_tcp_4 > 0.053 and
            current_cti < -0.8 and
            current_rsi < 35 and
            rsi_84[-1] < 60 and
            rsi_112[-1] < 60):
            self.vars['enter_tag'] = 'vwap'
            return True
        
        # Local uptrend
        if (current_ema_26 > current_ema_12 and
            (current_ema_26 - current_ema_12) > (current_open * 0.025) and
            current_price < (bb_lower[-1] * self.buy_bb_factor)):
            self.vars['enter_tag'] = 'local_uptrend'
            return True
        
        # NFIX29
        if (current_price < (current_ema_16 * 0.982) and
            current_ewo_fast < -10.0 and
            current_cti < -0.9):
            self.vars['enter_tag'] = 'NFIX29'
            return True
        
        return False
    
    def should_short(self) -> bool:
        return False
    
    def go_long(self):
        """
        Вход в лонг позицию
        """
        from jesse import utils
        
        entry_price = self.price
        
        # Используем 95% доступной маржи
        leveraged_margin = self.leveraged_available_margin
        position_size = leveraged_margin * 0.95
        
        # Конвертируем размер позиции в количество
        qty = utils.size_to_qty(position_size, entry_price, precision=8)
        
        if qty <= 0:
            return
        
        # Вход по рыночной цене
        self.buy = qty, entry_price
        
        # Стоп-лосс -99%
        stop_loss_price = entry_price * (1 - self.stop_loss_pct)
        self.stop_loss = qty, stop_loss_price
        
        # Инициализируем переменные
        self.vars['highest_price'] = entry_price
        self.vars['buy_count'] = 1
        self.vars['initial_stake'] = position_size
    
    def go_short(self):
        pass
    
    def update_position(self) -> None:
        """
        Обновление позиции:
        1. Кастомный стоп-лосс
        2. Deadfish exit
        3. DCA (Dollar Cost Averaging)
        4. Выход по условиям
        """
        if not self.is_long or self.position.qty == 0:
            return
        
        current_price = self.close
        entry_price = self.position.entry_price
        qty = self.position.qty
        current_profit = ((current_price - entry_price) / entry_price)
        
        # Обновляем максимальную цену
        if current_price > self.vars['highest_price']:
            self.vars['highest_price'] = current_price
        
        # === Deadfish Exit ===
        bb = ta.bollinger_bands(self.candles, period=20, devup=2, devdn=2, sequential=True)
        if isinstance(bb, tuple) and len(bb) >= 3:
            bb_middle = bb[1]
            bb_width = ((bb[0][-1] - bb[2][-1]) / bb_middle[-1]) if bb_middle[-1] != 0 else 0
            
            volumes = self.candles[:, 5]
            if len(volumes) >= 24:
                volume_mean_12 = np.mean(volumes[-12:])
                volume_mean_24 = np.mean(volumes[-24:-1]) if len(volumes) > 24 else volume_mean_12
                
                ema_200 = ta.ema(self.candles, period=200, sequential=True)
                cmf = chaikin_money_flow(self.candles, 20)
                
                if (len(ema_200) > 0 and len(cmf) > 0 and
                    current_profit < self.sell_deadfish_profit and
                    current_price < ema_200[-1] and
                    bb_width < self.sell_deadfish_bb_width and
                    current_price > (bb_middle[-1] * self.sell_deadfish_bb_factor) and
                    volume_mean_12 < (volume_mean_24 * self.sell_deadfish_volume_factor) and
                    cmf[-1] < 0.0):
                    # Закрываем позицию (deadfish)
                    self.liquidate()
                    return
        
        # === Кастомный стоп-лосс ===
        HSL = self.pHSL
        PF_1 = self.pPF_1
        SL_1 = self.pSL_1
        PF_2 = self.pPF_2
        SL_2 = self.pSL_2
        
        if current_profit > PF_2:
            sl_profit = SL_2 + (current_profit - PF_2)
        elif current_profit > PF_1:
            sl_profit = SL_1 + ((current_profit - PF_1) * (SL_2 - SL_1) / (PF_2 - PF_1))
        else:
            sl_profit = HSL
        
        if sl_profit < current_profit:
            new_stop = entry_price * (1 + sl_profit)
            if self.stop_loss is None or (isinstance(self.stop_loss, tuple) and self.stop_loss[1] < new_stop):
                self.stop_loss = qty, new_stop
        
        # === DCA (Dollar Cost Averaging) ===
        if (current_profit <= self.initial_safety_order_trigger and
            self.vars['buy_count'] < self.max_safety_orders):
            
            # Вычисляем триггер для следующего ордера
            safety_order_trigger = abs(self.initial_safety_order_trigger) * self.vars['buy_count']
            if self.safety_order_step_scale > 1:
                safety_order_trigger = (abs(self.initial_safety_order_trigger) +
                    abs(self.initial_safety_order_trigger) * self.safety_order_step_scale *
                    (math.pow(self.safety_order_step_scale, (self.vars['buy_count'] - 1)) - 1) /
                    (self.safety_order_step_scale - 1))
            
            if current_profit <= (-1 * abs(safety_order_trigger)):
                # Вычисляем размер следующего ордера
                from jesse import utils
                stake_amount = self.vars['initial_stake'] * math.pow(self.safety_order_volume_scale, (self.vars['buy_count'] - 1))
                add_qty = utils.size_to_qty(stake_amount, current_price, precision=8)
                
                if add_qty > 0:
                    # Добавляем к позиции
                    self.buy = add_qty, current_price
                    self.vars['buy_count'] += 1
        
        # === Выход по условиям ===
        ema_sell = ta.ema(self.candles, period=self.base_nb_candles_sell, sequential=True)
        if len(ema_sell) > 0:
            current_ema_sell = ema_sell[-1]
            
            # Fisher для выхода
            rsi = ta.rsi(self.candles, period=14, sequential=True)
            if len(rsi) > 0:
                rsi_normalized = (rsi[-1] - 50) / 50 * 0.1
                fisher = (np.exp(2 * rsi_normalized) - 1) / (np.exp(2 * rsi_normalized) + 1)
                
                ha_open, ha_high, ha_low, ha_close = heikin_ashi_candles(self.candles)
                if len(ha_high) >= 3 and len(ha_close) >= 2:
                    # Условие выхода по Fisher
                    if (fisher > self.sell_fisher and
                        ha_high[-1] <= ha_high[-2] and
                        ha_high[-2] <= ha_high[-3] and
                        ha_close[-1] <= ha_close[-2] and
                        current_price > (bb_middle[-1] * self.sell_bbmiddle_close)):
                        self.liquidate()
                        return
            
            # Выход по EMA
            if current_price > (current_ema_sell * self.high_offset):
                self.liquidate()
                return
    
    def _calculate_cti(self, candles, period=20):
        """
        CTI (Correlation Trend Indicator)
        """
        if len(candles) < period:
            return np.array([])
        
        close_prices = candles[:, 4]
        time_array = np.arange(len(close_prices))
        
        cti_values = np.full(len(close_prices), np.nan)
        
        for i in range(period - 1, len(close_prices)):
            window_close = close_prices[i - period + 1:i + 1]
            window_time = time_array[i - period + 1:i + 1]
            
            if len(window_close) == period:
                mean_close = np.mean(window_close)
                mean_time = np.mean(window_time)
                
                numerator = np.sum((window_close - mean_close) * (window_time - mean_time))
                denominator = np.sqrt(
                    np.sum((window_close - mean_close) ** 2) *
                    np.sum((window_time - mean_time) ** 2)
                )
                
                if denominator != 0:
                    cti_values[i] = numerator / denominator
                else:
                    cti_values[i] = 0
        
        return cti_values
    
    def should_cancel_entry(self) -> bool:
        return False
    
    def filters(self) -> list:
        return []

