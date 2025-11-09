#!/usr/bin/env python3
"""
Скрипт для просмотра данных по биткоину из базы данных Jesse
Использование:
    python3 view_candles.py
    python3 view_candles.py --exchange "Gate USDT Perpetual" --symbol "USDT-USDT"
    python3 view_candles.py --count 10
"""

import sys
import os
import psycopg2
from datetime import datetime
import argparse

# Добавляем путь к jesse-master
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse-master'))

# Настройки подключения к БД (из .env)
DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 5432,
    'database': 'jesse_test_db',
    'user': 'jesse_user',
    'password': 'jesse_password'
}

def get_candles_info(exchange=None, symbol=None, timeframe='1m', limit=10):
    """Получить информацию о свечах из базы данных"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Формируем запрос
        query = """
            SELECT 
                exchange, 
                symbol, 
                timeframe,
                COUNT(*) as count,
                MIN(timestamp) as first_timestamp,
                MAX(timestamp) as last_timestamp
            FROM candle
        """
        
        conditions = []
        params = []
        
        if exchange:
            conditions.append("exchange = %s")
            params.append(exchange)
        
        if symbol:
            conditions.append("symbol = %s")
            params.append(symbol)
        
        if timeframe:
            conditions.append("timeframe = %s")
            params.append(timeframe)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " GROUP BY exchange, symbol, timeframe ORDER BY exchange, symbol, timeframe"
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return results
        
    except psycopg2.Error as e:
        print(f"Ошибка подключения к базе данных: {e}")
        return None

def get_candles_sample(exchange, symbol, timeframe='1m', limit=10):
    """Получить примеры свечей"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        query = """
            SELECT 
                timestamp,
                open,
                high,
                low,
                close,
                volume
            FROM candle
            WHERE exchange = %s AND symbol = %s AND timeframe = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """
        
        cursor.execute(query, (exchange, symbol, timeframe, limit))
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return results
        
    except psycopg2.Error as e:
        print(f"Ошибка получения данных: {e}")
        return None

def format_timestamp(ts):
    """Форматировать timestamp в читаемый формат"""
    return datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S')

def main():
    parser = argparse.ArgumentParser(description='Просмотр данных по биткоину из базы Jesse')
    parser.add_argument('--exchange', default='Gate USDT Perpetual', help='Название биржи')
    parser.add_argument('--symbol', default='USDT-USDT', help='Символ (например, USDT-USDT)')
    parser.add_argument('--timeframe', default='1m', help='Таймфрейм (1m, 5m, 1h и т.д.)')
    parser.add_argument('--count', type=int, default=10, help='Количество свечей для показа')
    parser.add_argument('--list', action='store_true', help='Показать список всех доступных данных')
    
    args = parser.parse_args()
    
    if args.list:
        print("=" * 80)
        print("Доступные данные в базе:")
        print("=" * 80)
        
        results = get_candles_info()
        if results:
            print(f"{'Exchange':<30} {'Symbol':<20} {'Timeframe':<10} {'Count':<15} {'First':<20} {'Last':<20}")
            print("-" * 80)
            for row in results:
                exchange, symbol, timeframe, count, first_ts, last_ts = row
                first_str = format_timestamp(first_ts) if first_ts else 'N/A'
                last_str = format_timestamp(last_ts) if last_ts else 'N/A'
                print(f"{exchange:<30} {symbol:<20} {timeframe:<10} {count:<15} {first_str:<20} {last_str:<20}")
        else:
            print("Данные не найдены или ошибка подключения")
    else:
        print("=" * 80)
        print(f"Данные для: {args.exchange} - {args.symbol} ({args.timeframe})")
        print("=" * 80)
        
        # Сначала показываем статистику
        results = get_candles_info(args.exchange, args.symbol, args.timeframe)
        if results:
            for row in results:
                exchange, symbol, timeframe, count, first_ts, last_ts = row
                print(f"\nСтатистика:")
                print(f"  Exchange: {exchange}")
                print(f"  Symbol: {symbol}")
                print(f"  Timeframe: {timeframe}")
                print(f"  Всего свечей: {count}")
                if first_ts:
                    print(f"  Первая свеча: {format_timestamp(first_ts)}")
                if last_ts:
                    print(f"  Последняя свеча: {format_timestamp(last_ts)}")
        
        # Показываем примеры свечей
        print(f"\nПоследние {args.count} свечей:")
        print("-" * 80)
        print(f"{'Timestamp':<20} {'Open':<15} {'High':<15} {'Low':<15} {'Close':<15} {'Volume':<15}")
        print("-" * 80)
        
        candles = get_candles_sample(args.exchange, args.symbol, args.timeframe, args.count)
        if candles:
            for candle in candles:
                ts, open_price, high, low, close, volume = candle
                ts_str = format_timestamp(ts)
                print(f"{ts_str:<20} {open_price:<15.2f} {high:<15.2f} {low:<15.2f} {close:<15.2f} {volume:<15.2f}")
        else:
            print("Свечи не найдены")
        
        print("=" * 80)

if __name__ == "__main__":
    main()

