# 🚀 Быстрая справка по Jesse API

## 🔗 Прямые ссылки (порт 9001)

### Веб-интерфейс
```
http://localhost:9001
```

### API Endpoints

#### 1. Авторизация
```
POST http://localhost:9001/auth
Body: {"password": "test_password_123"}
```

#### 2. Список всех бектестов
```
POST http://localhost:9001/backtest/sessions
Headers: Authorization: <token>
Body: {"limit": 50, "offset": 0}
```

#### 3. Данные конкретного бектеста (метрики + все данные)
```
POST http://localhost:9001/backtest/sessions/{session_id}
Headers: Authorization: <token>
```

**Ответ:**
```json
{
  "session": {
    "id": "...",
    "status": "finished",
    "metrics": {
      "total_trades": 100,
      "win_rate": 65.5,
      "total_net_profit": 1234.56,
      "total_paid_fees": 50.0,
      "starting_balance": 10000,
      "finishing_balance": 11234.56,
      "net_profit_percentage": 12.35,
      "max_drawdown": -5.2,
      "sharpe_ratio": 1.5,
      "profit_factor": 1.8,
      "expectancy": 12.35,
      "average_win": 50.0,
      "average_loss": -30.0,
      ...
    },
    "trades": [...],
    "equity_curve": [...],
    "has_chart_data": true
  }
}
```

#### 4. График с точками входа/выхода
```
POST http://localhost:9001/backtest/sessions/{session_id}/chart-data
Headers: Authorization: <token>
```

**Ответ:**
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
        "type": "buy",
        "qty": 0.1
      },
      {
        "timestamp": 1234568000,
        "price": 51000,
        "type": "sell",
        "qty": 0.1
      },
      ...
    ],
    "add_line_to_candle_chart": [...],
    "add_extra_line_chart": [...]
  }
}
```

#### 5. Логи бектеста
```
GET http://localhost:9001/backtest/logs/{session_id}?token=<token>
```

#### 6. WebSocket (real-time обновления)
```
ws://localhost:9001/ws?token=<token>
```

**События:**
- `alert` - уведомления
- `metrics` - метрики (при завершении)
- `trades` - сделки
- `equity_curve` - кривая капитала
- `hyperparameters` - параметры стратегии

---

## 📁 Где хранятся данные

### База данных PostgreSQL
**Таблица:** `backtest_session`

**Ключевые поля:**
- `metrics` (JSON) - **все показатели стратегии**
- `chart_data` (JSON) - **данные графика с точками входа/выхода**
- `trades` (JSON) - все сделки
- `equity_curve` (JSON) - кривая капитала
- `status` - статус выполнения

### Файлы
```
storage/logs/backtest-mode/{session_id}.txt  # Логи
storage/exports/backtest/{session_id}/        # Экспорты (если включены)
```

---

## 📂 Важные файлы в коде

### API Endpoints
- `jesse-master/jesse/controllers/backtest_controller.py` - все endpoints

### Модель данных
- `jesse-master/jesse/models/BacktestSession.py` - структура сессии

### Трансформеры
- `jesse-master/jesse/services/transformers.py` - форматирование данных

### WebSocket
- `jesse-master/jesse/controllers/websocket_controller.py` - real-time обновления

### Логика бектеста
- `jesse-master/jesse/modes/backtest_mode.py` - выполнение и генерация данных

---

## 🎯 Примеры использования

### Python - получить метрики
```python
import requests

BASE_URL = "http://localhost:9001"
TOKEN = requests.post(
    f"{BASE_URL}/auth",
    json={"password": "test_password_123"}
).json()["auth_token"]

# Получить сессию
session = requests.post(
    f"{BASE_URL}/backtest/sessions/{session_id}",
    headers={"Authorization": TOKEN}
).json()["session"]

# Метрики
metrics = session["metrics"]
print(f"Trades: {metrics['total_trades']}")
print(f"Win Rate: {metrics['win_rate']}%")
print(f"Profit: ${metrics['total_net_profit']}")

# График
chart = requests.post(
    f"{BASE_URL}/backtest/sessions/{session_id}/chart-data",
    headers={"Authorization": TOKEN}
).json()["chart_data"]

# Точки входа/выхода
orders = chart["orders_chart"]
for order in orders:
    print(f"{order['type']} at {order['price']} on {order['timestamp']}")
```

### JavaScript - WebSocket
```javascript
const token = 'your-token';
const ws = new WebSocket(`ws://localhost:9001/ws?token=${token}`);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch(data.type) {
    case 'metrics':
      console.log('Metrics:', data.data);
      break;
    case 'trades':
      console.log('Trades:', data.data);
      break;
    case 'equity_curve':
      console.log('Equity Curve:', data.data);
      break;
    case 'alert':
      console.log('Alert:', data.data.message);
      break;
  }
};
```

### cURL - получить метрики
```bash
# Авторизация
TOKEN=$(curl -s -X POST http://localhost:9001/auth \
  -H "Content-Type: application/json" \
  -d '{"password":"test_password_123"}' | jq -r '.auth_token')

# Получить сессию
curl -X POST http://localhost:9001/backtest/sessions/{session_id} \
  -H "Authorization: $TOKEN" \
  -H "Content-Type: application/json" | jq '.session.metrics'

# Получить график
curl -X POST http://localhost:9001/backtest/sessions/{session_id}/chart-data \
  -H "Authorization: $TOKEN" \
  -H "Content-Type: application/json" | jq '.chart_data.orders_chart'
```

---

## 📊 Структура данных графика

### Свечи (candles_chart)
```javascript
[
  [timestamp, open, high, low, close, volume],
  [1704067200000, 50000, 51000, 49000, 50500, 100.5],
  ...
]
```

### Ордера (orders_chart) - точки входа/выхода
```javascript
[
  {
    "timestamp": 1704067200000,
    "price": 50000,
    "type": "buy",  // или "sell"
    "qty": 0.1
  },
  ...
]
```

---

## 🔍 Статус выполнения бектеста

**Статусы:**
- `running` - выполняется
- `finished` - завершен успешно
- `failed` - завершен с ошибкой
- `cancelled` - отменен
- `stopped` - остановлен

**Проверка:**
```python
session = requests.post(
    f"{BASE_URL}/backtest/sessions/{session_id}",
    headers={"Authorization": TOKEN}
).json()["session"]

status = session["status"]
if status == "running":
    print("Бектест выполняется...")
elif status == "finished":
    print("Бектест завершен!")
    print(f"Метрики: {session['metrics']}")
```

