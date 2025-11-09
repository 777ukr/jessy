#!/usr/bin/env python3
"""
Скрипт для проверки статуса бектеста
Использование:
    python3 check_backtest.py <session_id>
"""

import sys
import requests
import time
import json

BASE_URL = "http://localhost:9001"
PASSWORD = "test_password_123"

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
        print(f"Ошибка авторизации: {response.status_code}")
        sys.exit(1)

def get_session(session_id):
    """Получить информацию о сессии"""
    token = get_auth_token()
    
    response = requests.get(
        f"{BASE_URL}/backtest/sessions/{session_id}",
        headers={"Authorization": token}
    )
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Ошибка получения сессии: {response.status_code}")
        print(f"Ответ: {response.text}")
        return None

def print_session_info(session):
    """Вывести информацию о сессии"""
    if not session:
        return
    
    print("=" * 60)
    print(f"Session ID: {session.get('id', 'N/A')}")
    print(f"Status: {session.get('status', 'N/A')}")
    print(f"Title: {session.get('title', 'N/A')}")
    print()
    
    if session.get('status') == 'finished':
        metrics = session.get('metrics', {})
        if metrics:
            print("📊 Результаты:")
            print(f"  Total Trades: {metrics.get('total_trades', 0)}")
            print(f"  Winning Trades: {metrics.get('winning_trades', 0)}")
            print(f"  Losing Trades: {metrics.get('losing_trades', 0)}")
            print(f"  Win Rate: {metrics.get('win_rate', 0):.2f}%")
            print(f"  Net Profit: ${metrics.get('total_net_profit', 0):.2f}")
            print(f"  Total Paid Fees: ${metrics.get('total_paid_fees', 0):.2f}")
            print(f"  Starting Balance: ${metrics.get('starting_balance', 0):.2f}")
            print(f"  Finishing Balance: ${metrics.get('finishing_balance', 0):.2f}")
            print(f"  ROI: {metrics.get('net_profit_percentage', 0):.2f}%")
            print(f"  Max Drawdown: {metrics.get('max_drawdown', 0):.2f}%")
            print(f"  Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")
    elif session.get('status') == 'running':
        print("⏳ Бектест выполняется...")
    elif session.get('status') == 'cancelled':
        print("❌ Бектест отменен")
    elif session.get('status') == 'failed':
        print("❌ Бектест завершился с ошибкой")
        if session.get('exception'):
            print(f"Ошибка: {session.get('exception')}")
    
    print("=" * 60)

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    session_id = sys.argv[1]
    
    session = get_session(session_id)
    if session:
        print_session_info(session)
    else:
        print(f"Сессия {session_id} не найдена")

if __name__ == "__main__":
    main()

