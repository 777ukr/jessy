from jesse.strategies import Strategy


class EMA_BTC_Channel_2_2_10(Strategy):
    """
    Стратегия на 4-часовых свечах с разделением позиции на 3 части:
    - Работа на 4-часовых свечах
    - Вход: если цена падает на 3% от максимума
    - Стоп-лосс: 2.2% для всех частей
    - Часть 1: трейлинг стоп 1.5% при росте 3%
    - Часть 2: трейлинг стоп 0.6% при росте 1.5%
    - Часть 3: закрытие при росте в 3 раза (200%)
    """
    
    def __init__(self):
        super().__init__()
        # Переменные для трейлинга
        self.vars['highest_price'] = 0  # Максимальная цена для отслеживания падения
        self.vars['trailing_1_activated'] = False  # Флаг активации трейлинга для части 1
        self.vars['trailing_2_activated'] = False  # Флаг активации трейлинга для части 2
        self.vars['part1_closed'] = False  # Флаг закрытия части 1
        self.vars['part2_closed'] = False  # Флаг закрытия части 2
        self.vars['part3_closed'] = False  # Флаг закрытия части 3
        self.vars['entry_price'] = 0  # Цена входа
        self.vars['qty_per_part'] = 0  # Количество на каждую часть
        self.vars['highest_after_entry'] = 0  # Максимальная цена после входа
    
    def should_long(self) -> bool:
        """
        Условие для входа в лонг:
        Если цена падает на 3% от максимума за период
        """
        if len(self.candles) < 2:
            return False
        
        current_price = self.close
        
        # Находим максимум за последние свечи
        lookback_period = min(50, len(self.candles) - 1)  # До 50 свечей
        
        # Находим максимум за период
        high_prices = [c[2] for c in self.candles[-lookback_period:]]  # high
        period_high = max(high_prices)
        
        # Сохраняем максимум для отслеживания
        if period_high > self.vars['highest_price']:
            self.vars['highest_price'] = period_high
        
        # Проверяем, что цена упала на 3% от максимума
        if self.vars['highest_price'] > 0:
            drop_pct = ((self.vars['highest_price'] - current_price) / self.vars['highest_price']) * 100
            
            # Вход при падении на 3% или больше
            if drop_pct >= 3.0:
                return True
        
        return False
    
    def should_short(self) -> bool:
        return False
    
    def go_long(self):
        """
        Вход в лонг позицию - разбиваем на 3 части
        """
        from jesse import utils
        
        entry_price = self.price
        
        # Используем 95% доступной маржи с учетом кредитного плеча
        leveraged_margin = self.leveraged_available_margin
        position_size = leveraged_margin * 0.95
        
        # Конвертируем размер позиции в количество
        total_qty = utils.size_to_qty(position_size, entry_price, precision=8)
        
        # Проверяем, что количество больше нуля
        if total_qty <= 0:
            return
        
        # Разбиваем позицию на 3 равные части
        qty_per_part = total_qty / 3
        
        # Вход по рыночной цене (вся позиция)
        self.buy = total_qty, entry_price
        
        # Стоп-лосс 2.2% ниже цены входа для всей позиции
        stop_loss_price = entry_price * (1 - 0.022)
        self.stop_loss = total_qty, stop_loss_price
        
        # Инициализируем переменные для трейлинга
        self.vars['highest_price'] = entry_price  # Сбрасываем максимум на цену входа
        self.vars['highest_after_entry'] = entry_price
        self.vars['trailing_1_activated'] = False
        self.vars['trailing_2_activated'] = False
        self.vars['part1_closed'] = False
        self.vars['part2_closed'] = False
        self.vars['part3_closed'] = False
        self.vars['entry_price'] = entry_price
        self.vars['qty_per_part'] = qty_per_part  # Сохраняем количество на часть
    
    def go_short(self):
        pass
    
    def update_position(self) -> None:
        """
        Обновление позиции с разделением на 3 части:
        1. Часть 1: трейлинг стоп 1.5% при росте 3% - закрывается трейлингом
        2. Часть 2: трейлинг стоп 0.6% при росте 1.5% - закрывается трейлингом
        3. Часть 3: закрытие при росте в 3 раза (200%) - закрывается тейк-профитом
        """
        if not self.is_long or self.position.qty == 0:
            return
        
        current_price = self.close
        entry_price = self.position.entry_price
        qty_per_part = self.vars['qty_per_part']  # Используем сохраненное количество
        
        # Обновляем максимальную цену после входа
        if current_price > self.vars['highest_after_entry']:
            self.vars['highest_after_entry'] = current_price
        
        # Вычисляем текущую прибыль
        profit_pct = ((current_price - entry_price) / entry_price) * 100
        
        # Часть 3: закрытие при росте в 3 раза (200%)
        if not self.vars['part3_closed'] and profit_pct >= 200.0:
            # Закрываем третью часть позиции
            if self.position.qty >= qty_per_part:
                self.broker.reduce_position_at(qty_per_part, current_price, current_price)
                self.vars['part3_closed'] = True
        
        # Часть 1: активируем трейлинг стоп 1.5% при росте 3%
        if profit_pct >= 3.0:
            self.vars['trailing_1_activated'] = True
        
        # Часть 2: активируем трейлинг стоп 0.6% при росте 1.5%
        if profit_pct >= 1.5:
            self.vars['trailing_2_activated'] = True
        
        # Закрываем части 1 и 2 через трейлинг стоп
        # Часть 1: трейлинг стоп 1.5%
        if self.vars['trailing_1_activated'] and not self.vars['part1_closed']:
            trailing_stop_1 = self.vars['highest_after_entry'] * (1 - 0.015)
            if current_price <= trailing_stop_1:
                # Закрываем часть 1
                if self.position.qty >= qty_per_part:
                    self.broker.reduce_position_at(qty_per_part, current_price, current_price)
                    self.vars['part1_closed'] = True
        
        # Часть 2: трейлинг стоп 0.6%
        if self.vars['trailing_2_activated'] and not self.vars['part2_closed']:
            trailing_stop_2 = self.vars['highest_after_entry'] * (1 - 0.006)
            if current_price <= trailing_stop_2:
                # Закрываем часть 2
                if self.position.qty >= qty_per_part:
                    self.broker.reduce_position_at(qty_per_part, current_price, current_price)
                    self.vars['part2_closed'] = True
        
        # Управление основным стоп-лоссом для оставшейся позиции
        # Базовый стоп-лосс 2.2%
        base_stop_loss = entry_price * (1 - 0.022)
        
        # Вычисляем трейлинг стопы для незакрытых частей
        trailing_stop_1 = None
        trailing_stop_2 = None
        
        if self.vars['trailing_1_activated'] and not self.vars['part1_closed']:
            trailing_stop_1 = self.vars['highest_after_entry'] * (1 - 0.015)
        
        if self.vars['trailing_2_activated'] and not self.vars['part2_closed']:
            trailing_stop_2 = self.vars['highest_after_entry'] * (1 - 0.006)
        
        # Выбираем самый высокий стоп-лосс для защиты прибыли
        final_stop_loss = base_stop_loss
        if trailing_stop_1 is not None and trailing_stop_1 > final_stop_loss:
            final_stop_loss = trailing_stop_1
        if trailing_stop_2 is not None and trailing_stop_2 > final_stop_loss:
            final_stop_loss = trailing_stop_2
        
        # Обновляем стоп-лосс только если он выше текущего
        remaining_qty = self.position.qty
        if remaining_qty > 0:
            if self.stop_loss is not None:
                current_stop_loss = self.stop_loss[1] if isinstance(self.stop_loss, tuple) else self.stop_loss[0][1]
                if final_stop_loss > current_stop_loss:
                    self.stop_loss = remaining_qty, final_stop_loss
            else:
                self.stop_loss = remaining_qty, final_stop_loss
        
        # Устанавливаем тейк-профит для части 3 (при росте в 3 раза)
        if not self.vars['part3_closed'] and remaining_qty >= qty_per_part:
            take_profit_price_part3 = entry_price * 3.0
            self.take_profit = qty_per_part, take_profit_price_part3
        elif self.vars['part3_closed']:
            self.take_profit = None
    
    def should_cancel_entry(self) -> bool:
        return False
    
    def filters(self) -> list:
        return []
