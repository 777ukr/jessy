from jesse.strategies import Strategy
import jesse.indicators as ta
import jesse.helpers as jh


class EMA_BTC_Simple(Strategy):
    """
    Улучшенная стратегия для BTC с учетом комиссий Gate.io:
    - EMA 50 и EMA 100 для фильтрации тренда (более длинные движения)
    - Покупка при просадке 1.5% за месяц (глубокий откат)
    - Покупка на откате к EMA 50 (не на пике)
    - Стоп-лосс 0.7% (дает больше пространства для движения)
    - Тейк-профит 2.0% (покрывает комиссию 0.02% * 2 = 0.04% и дает прибыль 1.96%)
    - Трейлинг стоп с отступом 0.6% на рост (для длинных движений)
    - Фильтр: EMA 50 > EMA 100 (сильный восходящий тренд)
    """
    
    def __init__(self):
        super().__init__()
        # Переменные для трейлинга
        self.vars['highest_price'] = 0
        self.vars['trailing_activated'] = False
    
    def should_long(self) -> bool:
        """
        Улучшенное условие для входа в лонг:
        1. Цена выше EMA 50 и EMA 100 (сильный восходящий тренд)
        2. EMA 50 выше EMA 100 (тренд подтвержден)
        3. Просадка за месяц >= 1.5% (более глубокая просадка для лучшего входа)
        4. Цена откатилась к EMA 50 (покупка на откате)
        """
        if len(self.candles) < 100:
            return False
        
        # Вычисляем EMA 50 и EMA 100
        ema_50 = ta.ema(self.candles, period=50, sequential=True)
        ema_100 = ta.ema(self.candles, period=100, sequential=True)
        
        current_ema_50 = ema_50[-1]
        current_ema_100 = ema_100[-1]
        current_price = self.close
        
        # Фильтр 1: EMA 50 должна быть выше EMA 100 (восходящий тренд)
        if current_ema_50 <= current_ema_100:
            return False
        
        # Фильтр 2: Цена должна быть выше EMA 50 (тренд вверх)
        if current_price < current_ema_50:
            return False
        
        # Фильтр 3: Цена должна быть близко к EMA 50 (покупка на откате, не на пике)
        # Разрешаем покупку если цена в пределах 0.3% от EMA 50
        price_to_ema50_pct = ((current_price - current_ema_50) / current_ema_50) * 100
        if price_to_ema50_pct > 0.3:
            return False  # Цена слишком далеко от EMA 50, ждем отката
        
        # Вычисляем просадку за месяц
        timeframe_minutes = jh.timeframe_to_one_minutes(self.timeframe)
        days_back = 30
        minutes_per_month = days_back * 24 * 60
        lookback_candles = minutes_per_month // timeframe_minutes
        
        if len(self.candles) < lookback_candles + 1:
            lookback_candles = min(len(self.candles) - 1, 100)
        
        if lookback_candles > 0 and len(self.candles) > lookback_candles:
            # Берем цену месяц назад
            price_month_ago = self.candles[-lookback_candles - 1][4]
            price_drop_pct = ((price_month_ago - current_price) / price_month_ago) * 100
            
            # Покупка при просадке >= 1.5% (более глубокая просадка)
            if price_drop_pct >= 1.5:
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
        
        # Используем 95% доступной маржи с учетом кредитного плеча
        # leveraged_available_margin уже учитывает leverage
        leveraged_margin = self.leveraged_available_margin
        
        # Используем 95% от доступной маржи для безопасности
        position_size = leveraged_margin * 0.95
        
        # Конвертируем размер позиции в количество
        qty = utils.size_to_qty(position_size, entry_price, precision=8)
        
        # Проверяем, что количество больше нуля
        if qty <= 0:
            return
        
        # Вход по рыночной цене
        self.buy = qty, entry_price
        
        # Стоп-лосс 0.7% ниже цены входа (больше пространства для движения)
        # Учитываем комиссию: 0.02% (тейкер, округлено) при входе и выходе = 0.04%
        stop_loss_price = entry_price * (1 - 0.007)
        self.stop_loss = qty, stop_loss_price
        
        # Тейк-профит 2.0% выше цены входа
        # Комиссия: 0.02% * 2 = 0.04%, остаток 1.96% прибыли (хороший запас)
        take_profit_price = entry_price * (1 + 0.02)
        self.take_profit = qty, take_profit_price
        
        # Инициализируем переменные для трейлинга
        self.vars['highest_price'] = entry_price
        self.vars['trailing_activated'] = False
    
    def go_short(self):
        pass
    
    def update_position(self) -> None:
        """
        Обновление позиции для трейлинга стоп-лосса и тейк-профита
        """
        if not self.is_long or self.position.qty == 0:
            return
        
        current_price = self.close
        entry_price = self.position.entry_price
        qty = self.position.qty
        
        # Обновляем максимальную цену
        if current_price > self.vars['highest_price']:
            self.vars['highest_price'] = current_price
        
        # Активируем трейлинг когда цена выросла на 1.2% (защита прибыли)
        if current_price >= entry_price * 1.012:
            self.vars['trailing_activated'] = True
        
        # Если трейлинг активирован, обновляем стоп-лосс и тейк-профит
        if self.vars['trailing_activated']:
            # Трейлинг стоп: отступ 0.6% от максимальной цены на рост
            # Больший отступ для более длинных движений
            trailing_stop_price = self.vars['highest_price'] * (1 - 0.006)
            
            # Обновляем стоп-лосс только если он выше текущего (защита прибыли)
            if self.stop_loss is not None:
                current_stop_loss = self.stop_loss[1] if isinstance(self.stop_loss, tuple) else self.stop_loss[0][1]
                if trailing_stop_price > current_stop_loss:
                    self.stop_loss = qty, trailing_stop_price
            else:
                self.stop_loss = qty, trailing_stop_price
            
            # Обновляем тейк-профит: 2.0% от максимальной цены (трейлинг тейк-профит)
            new_take_profit = self.vars['highest_price'] * (1 + 0.02)
            if self.take_profit is not None:
                current_take_profit = self.take_profit[1] if isinstance(self.take_profit, tuple) else self.take_profit[0][1]
                if new_take_profit > current_take_profit:
                    self.take_profit = qty, new_take_profit
            else:
                self.take_profit = qty, new_take_profit
    
    def should_cancel_entry(self) -> bool:
        return False
    
    def filters(self) -> list:
        return []

