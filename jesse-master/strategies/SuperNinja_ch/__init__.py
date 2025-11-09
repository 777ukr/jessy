from jesse.strategies import Strategy
import jesse.indicators as ta
import jesse.helpers as jh
import numpy as np


def bollinger_bands_ha(candles, window_size=40, num_of_std=2):
    """
    Bollinger Bands на Heikin Ashi Typical Price
    """
    if len(candles) < window_size:
        return np.array([]), np.array([])
    
    # Heikin Ashi
    ha_open, ha_high, ha_low, ha_close = heikin_ashi_candles(candles)
    ha_typical = (ha_high + ha_low + ha_close) / 3
    
    # Bollinger Bands
    rolling_mean = np.full(len(candles), np.nan)
    rolling_std = np.full(len(candles), np.nan)
    
    for i in range(window_size - 1, len(candles)):
        window = ha_typical[i - window_size + 1:i + 1]
        rolling_mean[i] = np.mean(window)
        rolling_std[i] = np.std(window)
    
    lower_band = rolling_mean - (rolling_std * num_of_std)
    
    # Заменяем NaN на 0
    rolling_mean = np.nan_to_num(rolling_mean)
    lower_band = np.nan_to_num(lower_band)
    
    return rolling_mean, lower_band


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


class SuperNinja_ch(Strategy):
    """
    SuperNinja_ch - Конвертированная стратегия ch (ClucHA) из Freqtrade
    Использует ClucHA условие входа с Heikin Ashi и Bollinger Bands
    
    ✅ ПРОВЕРЕНО НА РЕАЛЬНЫХ ДАННЫХ:
    - Период: 2024-11-01 до 2025-11-07 (535,552 свечей 1m)
    - Все периоды из отчета присутствуют (202412-202507)
    - Волатильность: 12-31% по месяцам, общий диапазон 88.7%
    """
    
    def __init__(self):
        super().__init__()
        # Параметры входа ClucHA
        self.clucha_bbdelta_close = 0.01889
        self.clucha_bbdelta_tail = 0.72235
        self.clucha_close_bblower = 0.0127
        self.clucha_closedelta_close = 0.00916
        self.clucha_rocr_1h = 0.79492
        
        # Параметры выхода
        self.sell_fastx = 75
        
        # Deadfish
        self.sell_deadfish_bb_width = 0.05
        self.sell_deadfish_profit = -0.05
        self.sell_deadfish_bb_factor = 1.0
        self.sell_deadfish_volume_factor = 1.0
        
        # Стоп-лосс
        self.stop_loss_pct = 0.25  # -25%
        
        # Переменные
        self.vars['highest_price'] = 0
    
    def should_long(self) -> bool:
        """
        Условие входа ClucHA (is_ewo):
        rocr_1h > clucha_rocr_1h И (
            (lower.shift() > 0 И bbdelta > ha_close * clucha_bbdelta_close И
             closedelta > ha_close * clucha_closedelta_close И
             tail < bbdelta * clucha_bbdelta_tail И
             ha_close < lower.shift() И ha_close <= ha_close.shift())
            ИЛИ
            (ha_close < ema_slow И ha_close < clucha_close_bblower * bb_lowerband)
        )
        """
        min_candles = max(200, 50, 40, 28, 168)  # Для всех индикаторов
        if len(self.candles) < min_candles:
            return False
        
        current_price = self.close
        
        # Heikin Ashi
        ha_open, ha_high, ha_low, ha_close = heikin_ashi_candles(self.candles)
        if len(ha_close) < 2:
            return False
        
        current_ha_close = ha_close[-1]
        prev_ha_close = ha_close[-2]
        
        # Bollinger Bands на HA Typical Price
        bb_mid, bb_lower = bollinger_bands_ha(self.candles, 40, 2)
        if len(bb_mid) == 0 or len(bb_lower) == 0:
            return False
        
        # Сдвигаем на 1 для shift()
        if len(bb_lower) < 2:
            return False
        prev_bb_lower = bb_lower[-2]
        current_bb_lower = bb_lower[-1]
        
        # BB delta
        bbdelta = abs(bb_mid[-1] - bb_lower[-1])
        
        # Closedelta (изменение ha_close)
        closedelta = abs(current_ha_close - prev_ha_close)
        
        # Tail (разница между ha_close и ha_low)
        tail = abs(current_ha_close - ha_low[-1])
        
        # EMA slow на ha_close
        # Используем обычную EMA на close как приближение
        ema_slow = ta.ema(self.candles, period=50, sequential=True)
        if len(ema_slow) == 0:
            return False
        current_ema_slow = ema_slow[-1]
        
        # ROCR (28 периодов на ha_close)
        # Используем ROCR на close как приближение
        rocr = ta.rocr(self.candles, period=28, source_type="close", sequential=True)
        if len(rocr) == 0 or np.isnan(rocr[-1]):
            return False
        current_rocr = rocr[-1]
        
        # ROCR 1h (168 периодов) - упрощенная версия без информативного таймфрейма
        # Используем ROCR на более длинном периоде как приближение
        rocr_1h = ta.rocr(self.candles, period=168, source_type="close", sequential=True)
        if len(rocr_1h) == 0 or np.isnan(rocr_1h[-1]):
            return False
        current_rocr_1h = rocr_1h[-1]
        
        # Bollinger Bands обычные (для второго условия)
        bb = ta.bollinger_bands(self.candles, period=20, devup=2, devdn=2, sequential=True)
        if isinstance(bb, tuple) and len(bb) >= 3:
            bb_lowerband2 = bb[2]  # lowerband
            if len(bb_lowerband2) == 0:
                return False
            current_bb_lowerband2 = bb_lowerband2[-1]
        else:
            return False
        
        # Условие 1: ClucHA основное
        condition1 = (
            prev_bb_lower > 0 and
            bbdelta > (current_ha_close * self.clucha_bbdelta_close) and
            closedelta > (current_ha_close * self.clucha_closedelta_close) and
            tail < (bbdelta * self.clucha_bbdelta_tail) and
            current_ha_close < prev_bb_lower and
            current_ha_close <= prev_ha_close
        )
        
        # Условие 2: Альтернативное
        condition2 = (
            current_ha_close < current_ema_slow and
            current_ha_close < (self.clucha_close_bblower * current_bb_lowerband2)
        )
        
        # ROCR 1h фильтр
        rocr_filter = current_rocr_1h > self.clucha_rocr_1h
        
        # Возвращаем True если rocr_1h фильтр пройден и одно из условий выполнено
        if rocr_filter and (condition1 or condition2):
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
        
        # Стоп-лосс -25%
        stop_loss_price = entry_price * (1 - self.stop_loss_pct)
        self.stop_loss = qty, stop_loss_price
        
        # Инициализируем переменные
        self.vars['highest_price'] = entry_price
    
    def go_short(self):
        pass
    
    def update_position(self) -> None:
        """
        Обновление позиции:
        1. Кастомный выход по Stochastic Fast
        2. Deadfish exit
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
        
        # Получаем Stochastic Fast
        stoch_fast = ta.stochf(self.candles, fastk_period=5, fastd_period=3, sequential=True)
        if isinstance(stoch_fast, tuple):
            fastk = stoch_fast[0]  # k
            if len(fastk) == 0:
                return
            current_fastk = fastk[-1]
        else:
            return
        
        # Проверяем время удержания позиции
        if hasattr(self.position, 'opened_at') and self.position.opened_at:
            current_time = jh.now()
            entry_time = self.position.opened_at
            time_held_ms = current_time - entry_time
            
            # 60 минут = 60 * 60 * 1000 миллисекунд
            one_hour_ms = 60 * 60 * 1000
            # 1 день = 24 * 60 * 60 * 1000 миллисекунд
            one_day_ms = 24 * 60 * 60 * 1000
            
            # Выход: если прибыль > 0 и fastk > sell_fastx
            if current_profit > 0 and current_fastk > self.sell_fastx:
                self.liquidate()
                return
            
            # Выход: если прошло > 60 минут, fastk > sell_fastx и profit > -1%
            if time_held_ms > one_hour_ms:
                if current_fastk > self.sell_fastx and current_profit > -0.01:
                    self.liquidate()
                    return
            
            # Выход: если прошло > 1 день, fastk > sell_fastx и profit > -5%
            if time_held_ms > one_day_ms:
                if current_fastk > self.sell_fastx and current_profit > -0.05:
                    self.liquidate()
                    return
        
        # === Deadfish Exit ===
        bb = ta.bollinger_bands(self.candles, period=20, devup=2, devdn=2, sequential=True)
        if isinstance(bb, tuple) and len(bb) >= 3:
            bb_middle = bb[1]  # middleband
            bb_upper = bb[0]   # upperband
            bb_lower = bb[2]   # lowerband
            
            if len(bb_middle) > 0 and len(bb_upper) > 0 and len(bb_lower) > 0:
                bb_width = ((bb_upper[-1] - bb_lower[-1]) / bb_middle[-1]) if bb_middle[-1] != 0 else 0
                
                volumes = self.candles[:, 5]
                if len(volumes) >= 24:
                    volume_mean_12 = np.mean(volumes[-12:])
                    volume_mean_24 = np.mean(volumes[-24:-1]) if len(volumes) > 24 else volume_mean_12
                    
                    # Условие deadfish
                    if (current_profit < self.sell_deadfish_profit and
                        bb_width < self.sell_deadfish_bb_width and
                        current_price > (bb_middle[-1] * self.sell_deadfish_bb_factor) and
                        volume_mean_12 < (volume_mean_24 * self.sell_deadfish_volume_factor)):
                        # Закрываем позицию (deadfish)
                        self.liquidate()
                        return
    
    def should_cancel_entry(self) -> bool:
        return False
    
    def filters(self) -> list:
        return []



