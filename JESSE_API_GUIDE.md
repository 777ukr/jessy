# Руководство по API Jesse для бектестинга

## 🔗 Прямые ссылки на сервере (порт 9001)

### Базовый URL
```
http://localhost:9001
```

### Авторизация
Все запросы требуют токен авторизации в заголовке `Authorization`.

**Получить токен:**
```bash
POST http://localhost:9001/auth
Content-Type: application/json

{
  "password": "test_password_123"
}

Ответ: {"auth_token": "..."}
```

---

## 📊 API Endpoints для бектестинга

### 1. **Запуск бектеста**
```
POST http://localhost:9001/backtest
Authorization: <token>
Content-Type: application/json

{
  "id": "unique-session-id",
  "debug_mode": false,
  "config": {
    "starting_balance": 10000,
    "fee": 0.001,
    "futures_leverage": 1,
    "futures_leverage_mode": "cross",
    "exchange": "Gate USDT Perpetual",
    "warm_up_candles": 200
  },
  "exchange": "Gate USDT Perpetual",
  "routes": [{
    "exchange": "Gate USDT Perpetual",
    "symbol": "BTC-USDT",
    "timeframe": "5m",
    "strategy": "SuperNinja"
  }],
  "data_routes": [],
  "start_date": "2024-01-01",
  "finish_date": "2025-11-07",
  "export_chart": true,
  "export_tradingview": false,
  "export_csv": false,
  "export_json": false,
  "fast_mode": true,
  "benchmark": null
}
```

### 2. **Получить список всех сессий бектеста**
```
POST http://localhost:9001/backtest/sessions
Authorization: <token>
Content-Type: application/json

{
  "limit": 50,
  "offset": 0,
  "title_search": null,
  "status_filter": null,
  "date_filter": null
}
```

**Ответ содержит:**
- `sessions[]` - массив сессий
- `count` - общее количество

### 3. **Получить данные конкретной сессии (с метриками)**
```
POST http://localhost:9001/backtest/sessions/{session_id}
Authorization: <token>
```

**Ответ содержит:**
- `session.id` - ID сессии
- `session.status` - статус (running/finished/failed/cancelled)
- `session.metrics` - **все показатели стратегии:**
  - `total_trades` - общее количество сделок
  - `winning_trades` - выигрышные сделки
  - `losing_trades` - проигрышные сделки
  - `win_rate` - процент выигрышей
  - `total_net_profit` - чистая прибыль
  - `total_paid_fees` - уплаченные комиссии
  - `starting_balance` - начальный баланс
  - `finishing_balance` - конечный баланс
  - `net_profit_percentage` - ROI в процентах
  - `max_drawdown` - максимальная просадка
  - `sharpe_ratio` - коэффициент Шарпа
  - `total_volume` - общий объем
  - `average_win` - средний выигрыш
  - `average_loss` - средний проигрыш
  - `profit_factor` - фактор прибыли
  - `expectancy` - математическое ожидание
  - И многие другие...

### 4. **Получить данные графика (точки входа/выхода)**
```
POST http://localhost:9001/backtest/sessions/{session_id}/chart-data
Authorization: <token>
```

**Ответ содержит:**
- `chart_data.candles_chart` - данные свечей для графика
- `chart_data.orders_chart` - **точки входа и выхода (ордера)**
- `chart_data.add_line_to_candle_chart` - дополнительные линии
- `chart_data.add_extra_line_chart` - дополнительные графики
- `chart_data.add_horizontal_line_to_candle_chart` - горизонтальные линии

**Структура данных графика:**
```json
{
  "chart_data": {
    "candles_chart": [
      [timestamp, open, high, low, close, volume],
      ...
    ],
    "orders_chart": [
      {
        "timestamp": 1234567890,
        "price": 50000,
        "type": "buy",  // или "sell"
        "qty": 0.1
      },
      ...
    ]
  }
}
```

### 5. **Получить логи бектеста**
```
GET http://localhost:9001/backtest/logs/{session_id}?token=<token>
```

### 6. **Отменить бектест**
```
POST http://localhost:9001/backtest/cancel
Authorization: <token>
Content-Type: application/json

{
  "id": "session-id"
}
```

---

## 📈 WebSocket для отслеживания статуса в реальном времени

### Подключение
```
ws://localhost:9001/ws?token=<token>
```

### События (events):

1. **`alert`** - уведомления о статусе
   ```json
   {
     "type": "alert",
     "data": {
       "message": "Successfully executed backtest simulation in: 10.36 seconds",
       "type": "success"
     }
   }
   ```

2. **`metrics`** - метрики бектеста (отправляются при завершении)
   ```json
   {
     "type": "metrics",
     "data": {
       "total_trades": 100,
       "win_rate": 65.5,
       "total_net_profit": 1234.56,
       ...
     }
   }
   ```

3. **`trades`** - данные о сделках
   ```json
   {
     "type": "trades",
     "data": [
       {
         "entry_time": 1234567890,
         "exit_time": 1234567900,
         "entry_price": 50000,
         "exit_price": 51000,
         "qty": 0.1,
         "pnl": 100,
         "fee": 1.0
       },
       ...
     ]
   }
   ```

4. **`equity_curve`** - кривая капитала
   ```json
   {
     "type": "equity_curve",
     "data": [
       [timestamp, balance],
       ...
     ]
   }
   ```

5. **`hyperparameters`** - гиперпараметры стратегии

---

## 📁 Где хранятся данные

### База данных PostgreSQL
**Таблица:** `backtest_session`

**Поля:**
- `id` - UUID сессии
- `status` - статус (running/finished/failed/cancelled)
- `metrics_json` - **JSON со всеми метриками** (хранится в БД)
- `chart_data` - **JSON с данными графика** (хранится в БД)
- `trades_json` - JSON со всеми сделками
- `equity_curve` - кривая капитала
- `created_at` - время создания
- `updated_at` - время обновления
- `title` - название сессии
- `description` - описание

### Файлы на диске

**Логи:**
```
storage/logs/backtest-mode/{session_id}.txt
```

**Экспортированные данные (если включен экспорт):**
```
storage/exports/backtest/{session_id}/
  - chart.json
  - tradingview.json
  - trades.csv
  - trades.json
```

---

## 🎨 Фронтенд (веб-интерфейс)

### Статические файлы
```
jesse-master/jesse/static/
  - index.html - главная страница
  - _nuxt/ - скомпилированные Vue.js компоненты
```

### Основные компоненты (в исходниках, если есть):
- График с точками входа/выхода
- Таблица метрик
- Список сделок
- Кривая капитала

---

## 🔍 Примеры использования

### Python скрипт для получения метрик:
```python
import requests

BASE_URL = "http://localhost:9001"
TOKEN = "your-token-here"

# Получить сессию
response = requests.post(
    f"{BASE_URL}/backtest/sessions/{session_id}",
    headers={"Authorization": TOKEN}
)

session = response.json()["session"]
metrics = session["metrics"]

print(f"Total Trades: {metrics['total_trades']}")
print(f"Win Rate: {metrics['win_rate']}%")
print(f"Net Profit: ${metrics['total_net_profit']}")
```

### JavaScript для WebSocket:
```javascript
const ws = new WebSocket(`ws://localhost:9001/ws?token=${token}`);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'metrics') {
    console.log('Metrics:', data.data);
  }
  
  if (data.type === 'trades') {
    console.log('Trades:', data.data);
  }
};
```

---

## 📝 Важные файлы в коде

### Контроллеры (API endpoints):
- `jesse-master/jesse/controllers/backtest_controller.py` - все endpoints для бектеста

### Модели (структура данных):
- `jesse-master/jesse/models/BacktestSession.py` - модель сессии бектеста

### Трансформеры (форматирование данных):
- `jesse-master/jesse/services/transformers.py` - преобразование данных для API

### Бектест мод (логика выполнения):
- `jesse-master/jesse/modes/backtest_mode.py` - выполнение бектеста и генерация данных

### WebSocket:
- `jesse-master/jesse/controllers/websocket_controller.py` - WebSocket для real-time обновлений

---

## 🎯 Рекомендации для интеграции

1. **Для отображения графика:**
   - Используйте `/backtest/sessions/{id}/chart-data`
   - Данные уже готовы для отображения (candles + orders)

2. **Для метрик:**
   - Используйте `/backtest/sessions/{id}` → `session.metrics`
   - Все показатели уже рассчитаны

3. **Для real-time обновлений:**
   - Подключитесь к WebSocket
   - Слушайте события `metrics`, `trades`, `equity_curve`

4. **Для статуса выполнения:**
   - Проверяйте `session.status` через API
   - Или слушайте WebSocket события `alert`

