#!/usr/bin/env python3
"""
Скрипт для запуска бектеста через API
Использование:
    python3 run_backtest.py SuperNinja "2024-01-01" "2025-11-07"
    python3 run_backtest.py SuperNinja "2024-01-01" "2025-11-07" --timeframe 5m
"""

import sys
import json
import requests
import uuid
from datetime import datetime

# Настройки
BASE_URL = "http://localhost:9001"
PASSWORD = "test_password_123"  # Пароль из .env

def get_auth_token():
    """Получить токен авторизации"""
    response = requests.post(
        f"{BASE_URL}/auth",
        json={"password": PASSWORD},
        headers={"Content-Type": "application/json"}
    )
    if response.status_code == 200:
        return response.json().get("auth_token")
    else:
        print(f"Ошибка авторизации: {response.status_code} - {response.text}")
        sys.exit(1)

def run_backtest(strategy_name, start_date, finish_date, timeframe="5m", exchange="Gate USDT Perpetual"):
    """Запустить бектест"""
    token = get_auth_token()
    
    # Генерируем уникальный ID сессии
    session_id = str(uuid.uuid4())
    
    # Формируем запрос
    backtest_request = {
        "id": session_id,
        "debug_mode": False,
        "config": {
            "starting_balance": 10000,
            "fee": 0.001,
            "futures_leverage": 1,
            "futures_leverage_mode": "cross",
            "exchange": exchange,
            "warm_up_candles": 200
        },
        "exchange": exchange,
        "routes": [
            {
                "exchange": exchange,
                "symbol": "BTC-USDT",
                "timeframe": timeframe,
                "strategy": strategy_name
            }
        ],
        "data_routes": [],
        "start_date": start_date,
        "finish_date": finish_date,
        "export_chart": False,
        "export_tradingview": False,
        "export_csv": False,
        "export_json": False,
        "fast_mode": True,
        "benchmark": False
    }
    
    print(f"Запуск бектеста для стратегии '{strategy_name}'...")
    print(f"Период: {start_date} - {finish_date}")
    print(f"Таймфрейм: {timeframe}")
    print(f"Exchange: {exchange}")
    print(f"Session ID: {session_id}")
    print()
    
    # Отправляем запрос
    response = requests.post(
        f"{BASE_URL}/backtest",
        json=backtest_request,
        headers={
            "Content-Type": "application/json",
            "Authorization": token
        }
    )
    
    if response.status_code == 202:
        print("✅ Бектест успешно запущен!")
        print(f"Session ID: {session_id}")
        print(f"Проверьте результаты в браузере: {BASE_URL}")
        print(f"Или используйте: python3 check_backtest.py {session_id}")
        return session_id
    else:
        print(f"❌ Ошибка запуска бектеста: {response.status_code}")
        print(f"Ответ: {response.text}")
        return None

def get_available_dates(exchange="Gate USDT Perpetual", symbol="BTC-USDT"):
    """Получить доступные даты из базы данных"""
    try:
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse-master'))
        
        from jesse.services.db import database
        from jesse.models.Candle import Candle
        import jesse.helpers as jh
        
        # Убеждаемся, что БД закрыта перед открытием
        if database.is_open():
            database.close_connection()
        
        database.open_connection()
        
        try:
            first = Candle.select().where(
                Candle.exchange == exchange,
                Candle.symbol == symbol
            ).order_by(Candle.timestamp.asc()).first()
            
            last = Candle.select().where(
                Candle.exchange == exchange,
                Candle.symbol == symbol
            ).order_by(Candle.timestamp.desc()).first()
            
            if first and last:
                start_date = jh.timestamp_to_date(first.timestamp)[:10]
                end_date = jh.timestamp_to_date(last.timestamp)[:10]
                return (start_date, end_date)
        finally:
            if database.is_open():
                database.close_connection()
    except Exception as e:
        # Игнорируем ошибки, возвращаем None
        pass
    
    return None, None

def main():
    # Получаем доступные даты
    available_start, available_end = get_available_dates()
    
    if len(sys.argv) < 2:
        print(__doc__)
        print("\n📊 Доступные даты в базе данных:")
        if available_start and available_end:
            print(f"   Первая свеча: {available_start}")
            print(f"   Последняя свеча: {available_end}")
        else:
            print("   Не удалось определить доступные даты")
        print("\nПримеры:")
        if available_start and available_end:
            print(f'  python3 run_backtest.py SuperNinja "{available_start}" "{available_end}"')
            print(f'  python3 run_backtest.py SuperNinja "{available_start}" "{available_end}" --timeframe 5m')
        else:
            print('  python3 run_backtest.py SuperNinja "2024-11-01" "2024-11-07"')
            print('  python3 run_backtest.py SuperNinja "2024-11-01" "2024-11-07" --timeframe 5m')
        sys.exit(1)
    
    strategy_name = sys.argv[1]
    
    # Если даты не указаны, используем доступные из БД
    if len(sys.argv) < 4:
        if available_start and available_end:
            start_date = available_start
            finish_date = available_end
            print(f"📊 Используются доступные даты из БД:")
            print(f"   Начало: {start_date}")
            print(f"   Конец: {finish_date}")
            print()
        else:
            print("❌ Ошибка: не удалось определить доступные даты")
            print("   Укажите даты вручную:")
            print('   python3 run_backtest.py SuperNinja "2024-11-01" "2024-11-07"')
            sys.exit(1)
    else:
        start_date = sys.argv[2]
        finish_date = sys.argv[3]
        
        # Проверяем, что указанные даты доступны
        if available_start and available_end:
            if start_date < available_start:
                print(f"⚠️  Внимание: Дата начала {start_date} раньше первой доступной даты {available_start}")
                print(f"   Используйте даты в диапазоне: {available_start} - {available_end}")
            if finish_date > available_end:
                print(f"⚠️  Внимание: Дата окончания {finish_date} позже последней доступной даты {available_end}")
                print(f"   Используйте даты в диапазоне: {available_start} - {available_end}")
    
    # Парсим дополнительные параметры
    timeframe = "5m"
    exchange = "Gate USDT Perpetual"
    
    i = 4
    while i < len(sys.argv):
        if sys.argv[i] == "--timeframe" and i + 1 < len(sys.argv):
            timeframe = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--exchange" and i + 1 < len(sys.argv):
            exchange = sys.argv[i + 1]
            i += 2
        else:
            i += 1
    
    run_backtest(strategy_name, start_date, finish_date, timeframe, exchange)

if __name__ == "__main__":
    main()

