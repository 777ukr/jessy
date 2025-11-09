from jesse.strategies import Strategy
import jesse.indicators as ta
import jesse.helpers as jh
import numpy as np


def ewo(candles, ema_length=5, ema2_length=35):
    """
    EWO (Elliott Wave Oscillator) индикатор
    Использует SMA как в оригинальной стратегии Freqtrade
    """
    if len(candles) < ema2_length:
        return np.array([])
    
    # Вычисляем SMA (в оригинале используется SMA)
    ema1 = ta.sma(candles, period=ema_length, sequential=True)
    ema2 = ta.sma(candles, period=ema2_length, sequential=True)
    
    # Вычисляем разницу в процентах от цены закрытия
    close_prices = candles[:, 4]  # close
    emadif = ((ema1 - ema2) / close_prices) * 100
    
    return emadif


class ElliotV5_SMA(Strategy):
    """
    Конвертированная стратегия ElliotV5_SMA из Freqtrade:
    - Использует EWO (Elliott Wave Oscillator) индикатор
    - EMA для входа и выхода
    - RSI для фильтрации
    - Трейлинг стоп
    """
    
    def __init__(self):
        super().__init__()
        # Параметры из buy_params
        self.base_nb_candles_buy = 17
        self.ewo_high = 3.34
        self.ewo_low = -17.457
        self.low_offset = 0.978
        self.rsi_buy = 65
        
        # Параметры из sell_params
        self.base_nb_candles_sell = 49
        self.high_offset = 1.019
        
        # Параметры EWO
        self.fast_ewo = 50
        self.slow_ewo = 200
        
        # Параметры трейлинга
        self.trailing_stop_positive = 0.005  # 0.5%
        self.trailing_stop_positive_offset = 0.03  # 3%
        
        # Переменные для трейлинга
        self.vars['highest_price'] = 0
        self.vars['trailing_activated'] = False
    
    def should_long(self) -> bool:
        """
        Условия для входа в лонг:
        1. Цена ниже EMA * low_offset И EWO > ewo_high И RSI < rsi_buy
        2. ИЛИ цена ниже EMA * low_offset И EWO < ewo_low
        """
        if len(self.candles) < max(self.slow_ewo, self.base_nb_candles_buy, 50):
            return False
        
        current_price = self.close
        
        # Вычисляем EMA для входа
        ema_buy = ta.ema(self.candles, period=self.base_nb_candles_buy, sequential=True)
        current_ema_buy = ema_buy[-1]
        
        # Вычисляем EWO
        ewo_values = ewo(self.candles, self.fast_ewo, self.slow_ewo)
        if len(ewo_values) == 0:
            return False
        current_ewo = ewo_values[-1]
        
        # Вычисляем RSI
        rsi = ta.rsi(self.candles, period=14, sequential=True)
        current_rsi = rsi[-1]
        
        # Условие 1: цена ниже EMA * low_offset И EWO > ewo_high И RSI < rsi_buy
        condition1 = (
            current_price < (current_ema_buy * self.low_offset) and
            current_ewo > self.ewo_high and
            current_rsi < self.rsi_buy
        )
        
        # Условие 2: цена ниже EMA * low_offset И EWO < ewo_low
        condition2 = (
            current_price < (current_ema_buy * self.low_offset) and
            current_ewo < self.ewo_low
        )
        
        return condition1 or condition2
    
    def should_short(self) -> bool:
        return False
    
    def go_long(self):
        """
        Вход в лонг позицию
        """
        from jesse import utils
        
        entry_price = self.price
        
        # Используем 95% доступной маржи с учетом кредитного плеча
        leveraged_margin = self.leveraged_available_margin
        position_size = leveraged_margin * 0.95
        
        # Конвертируем размер позиции в количество
        qty = utils.size_to_qty(position_size, entry_price, precision=8)
        
        # Проверяем, что количество больше нуля
        if qty <= 0:
            return
        
        # Вход по рыночной цене
        self.buy = qty, entry_price
        
        # Стоп-лосс -18.9% (из оригинальной стратегии)
        stop_loss_price = entry_price * (1 - 0.189)
        self.stop_loss = qty, stop_loss_price
        
        # Инициализируем переменные для трейлинга
        self.vars['highest_price'] = entry_price
        self.vars['trailing_activated'] = False
    
    def go_short(self):
        pass
    
    def update_position(self) -> None:
        """
        Обновление позиции:
        1. Проверка условий выхода (цена выше EMA * high_offset)
        2. Трейлинг стоп
        """
        if not self.is_long or self.position.qty == 0:
            return
        
        current_price = self.close
        entry_price = self.position.entry_price
        qty = self.position.qty
        
        # Обновляем максимальную цену
        if current_price > self.vars['highest_price']:
            self.vars['highest_price'] = current_price
        
        # Условие выхода: цена выше EMA * high_offset
        if len(self.candles) >= self.base_nb_candles_sell:
            ema_sell = ta.ema(self.candles, period=self.base_nb_candles_sell, sequential=True)
            current_ema_sell = ema_sell[-1]
            
            if current_price > (current_ema_sell * self.high_offset):
                # Закрываем позицию
                self.liquidate()
                return
        
        # Трейлинг стоп
        profit_pct = ((current_price - entry_price) / entry_price) * 100
        
        # Активируем трейлинг когда прибыль >= trailing_stop_positive_offset (3%)
        if profit_pct >= (self.trailing_stop_positive_offset * 100):
            self.vars['trailing_activated'] = True
        
        # Если трейлинг активирован, используем трейлинг стоп
        if self.vars['trailing_activated']:
            # Трейлинг стоп: отступ trailing_stop_positive (0.5%) от максимальной цены
            trailing_stop_price = self.vars['highest_price'] * (1 - self.trailing_stop_positive)
            
            # Обновляем стоп-лосс только если он выше текущего (защита прибыли)
            if self.stop_loss is not None:
                current_stop_loss = self.stop_loss[1] if isinstance(self.stop_loss, tuple) else self.stop_loss[0][1]
                if trailing_stop_price > current_stop_loss:
                    self.stop_loss = qty, trailing_stop_price
            else:
                self.stop_loss = qty, trailing_stop_price
    
    def should_cancel_entry(self) -> bool:
        return False
    
    def filters(self) -> list:
        return []

