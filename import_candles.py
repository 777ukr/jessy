#!/usr/bin/env python3
"""
Скрипт для импорта свечей через API Jesse
"""
import requests
import time
import sys
import uuid

def import_candles(exchange: str, symbol: str, start_date: str):
    """
    Импортирует свечи через API Jesse
    
    Args:
        exchange: Название биржи (например, "Gate USDT Perpetual")
        symbol: Пара (например, "BTC-USDT")
        start_date: Дата начала в формате YYYY-MM-DD
    """
    # Аутентификация
    print(f"🔐 Аутентификация...")
    response = requests.post('http://localhost:9001/auth', 
        json={'password': 'test_password_123'}, 
        timeout=10)
    
    if response.status_code != 200:
        print(f"❌ Ошибка аутентификации: {response.status_code}")
        return None
    
    token = response.json().get('auth_token')
    print(f"✅ Аутентификация успешна")
    
    # Создаем ID для задачи импорта
    import_id = str(uuid.uuid4())
    
    # Запускаем импорт
    print(f"\n📥 Запуск импорта свечей...")
    print(f"   Биржа: {exchange}")
    print(f"   Пара: {symbol}")
    print(f"   Дата начала: {start_date}")
    
    response = requests.post('http://localhost:9001/candles/import',
        json={
            'id': import_id,
            'exchange': exchange,
            'symbol': symbol,
            'start_date': start_date
        },
        headers={'Authorization': token, 'Content-Type': 'application/json'},
        timeout=10)
    
    if response.status_code == 202:
        print(f"✅ Импорт запущен (ID: {import_id[:8]}...)")
        print(f"\n⏳ Ожидание завершения импорта...")
        print(f"   (Проверьте статус в веб-интерфейсе: http://localhost:9001)")
        return import_id
    else:
        print(f"❌ Ошибка запуска импорта: {response.status_code}")
        print(f"   Ответ: {response.text}")
        return None


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Использование: python3 import_candles.py <exchange> <symbol> <start_date>")
        print("\nПример:")
        print('  python3 import_candles.py "Gate USDT Perpetual" "BTC-USDT" "2023-11-01"')
        sys.exit(1)
    
    exchange = sys.argv[1]
    symbol = sys.argv[2]
    start_date = sys.argv[3]
    
    import_candles(exchange, symbol, start_date)

