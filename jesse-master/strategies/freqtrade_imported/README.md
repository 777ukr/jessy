# Стратегии Freqtrade (импортированы)

Эти стратегии были импортированы из Freqtrade и требуют конвертации для использования в Jesse.

## Формат стратегий

Стратегии Freqtrade используют:
- `IStrategy` интерфейс из Freqtrade
- Pandas DataFrame для данных
- Методы `populate_indicators()`, `populate_entry_trend()`, `populate_exit_trend()`

Стратегии Jesse используют:
- Наследование от `Strategy` класса Jesse
- Массивы свечей (candles)
- Методы `should_long()`, `go_long()`, `update_position()`

## Доступные стратегии

1. **SimpleEMAStrategy.py** - Простая EMA стратегия
   - EMA 9/21 crossover
   - Стоп-лосс: -2%
   - Тейк-профит: 5%

2. **EMA_05_02_10_05_02.py** - Чувствительная EMA стратегия
   - Таймфрейм: 30 секунд
   - Стоп-лосс: -0.2%
   - Тейк-профит: 10%

3. **DipBuyStrategy.py** - Стратегия покупки на просадках

4. **EMA_PullbackStrategy.py** - Стратегия покупки на откатах к EMA

5. **PullbackBuyStrategy.py** - Стратегия покупки на откатах

6. **ReversalBuyStrategy.py** - Стратегия покупки на разворотах

7. **ShortBreakdownStrategy.py** - Шорт стратегия на пробоях

8. **ShortScalpingStrategy.py** - Шорт скальпинг стратегия

9. **ShortTrendStrategy.py** - Шорт трендовая стратегия

10. **AdvancedIndicatorStrategy.py** - Продвинутая стратегия с индикаторами

11. **MShotStrategy.py** - M-образная стратегия

12. **MStrikeStrategy.py** - M-страйк стратегия

13. **HookStrategy.py** - Хук стратегия

14. **ElliotV5_SMA.py** - Эллиотт волны со SMA

15. **E0V1E_20231004_085308.py** - Оптимизированная стратегия

16. **SimpleRSIStrategy.py** - Простая RSI стратегия

17. **TestStrategy.py** - Тестовая стратегия

## Конвертация

Для использования этих стратегий в Jesse необходимо:
1. Переписать логику входа/выхода под формат Jesse
2. Конвертировать индикаторы (EMA, RSI и т.д.) в формат Jesse
3. Адаптировать управление позицией (стоп-лосс, тейк-профит, трейлинг)

## Примечание

Эти файлы сохранены для справки. Они **не будут работать** в Jesse без конвертации.



