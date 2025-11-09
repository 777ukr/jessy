#!/usr/bin/env python3
"""
Скрипт для расчета возврата комиссий (60%) на Gate.io фьючерсах
"""
import sys
import os
import json

# Добавляем путь к jesse-master
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse-master'))

from jesse.models.BacktestSession import BacktestSession
from jesse.services.db import database

def calculate_fee_rebate(session_id: str = None):
    """
    Рассчитывает возврат комиссий (60%) для последней сессии бектеста
    """
    # Открываем соединение с БД
    if database.is_closed():
        database.open_connection()
    
    # Убеждаемся, что БД открыта
    if not database.is_open():
        database.open_connection()
    
    # Получаем последнюю сессию бектеста
    if session_id:
        try:
            session = BacktestSession.get_by_id(session_id)
        except Exception as e:
            print(f"Сессия {session_id} не найдена: {e}")
            return
    else:
        # Получаем последнюю завершенную сессию
        try:
            sessions = list(BacktestSession.select().where(
                BacktestSession.status == 'finished'
            ).order_by(BacktestSession.created_at.desc()).limit(1))
            if not sessions:
                # Пробуем получить любую последнюю сессию
                sessions = list(BacktestSession.select().order_by(BacktestSession.created_at.desc()).limit(1))
            if not sessions:
                print("Не найдено сессий бектеста")
                return
            session = sessions[0]
        except Exception as e:
            print(f"Ошибка при получении сессии: {e}")
            return
    
    # Получаем метрики
    metrics = session.metrics_json
    if not metrics:
        print("Метрики не найдены")
        return
    
    # Извлекаем Total Paid Fees
    total_paid_fees = metrics.get('total_paid_fees', 0)
    
    # Если нет в метриках, пытаемся вычислить из trades
    if total_paid_fees == 0:
        trades = session.trades_json
        if trades:
            total_paid_fees = sum(trade.get('fee', 0) for trade in trades)
    
    # Рассчитываем возврат 60%
    fee_rebate = total_paid_fees * 0.60
    net_fees_after_rebate = total_paid_fees - fee_rebate
    
    # Получаем текущие метрики
    net_profit = metrics.get('net_profit', 0)
    net_profit_percentage = metrics.get('net_profit_percentage', 0)
    starting_balance = metrics.get('starting_balance', 10000)
    finishing_balance = metrics.get('finishing_balance', starting_balance)
    
    # Рассчитываем новые метрики с учетом возврата комиссий
    new_net_profit = net_profit + fee_rebate
    new_finishing_balance = finishing_balance + fee_rebate
    new_net_profit_percentage = (new_net_profit / starting_balance) * 100
    
    # Выводим результаты
    print("=" * 60)
    print("РАСЧЕТ ВОЗВРАТА КОМИССИЙ (60%) НА GATE.IO ФЬЮЧЕРСАХ")
    print("=" * 60)
    print(f"\nСессия бектеста: {session.id}")
    if session.title:
        print(f"Название: {session.title}")
    print(f"\nТекущие метрики:")
    print(f"  Total Paid Fees: ${total_paid_fees:.2f}")
    print(f"  Net Profit: ${net_profit:.2f} ({net_profit_percentage:.2f}%)")
    print(f"  Starting Balance: ${starting_balance:.2f}")
    print(f"  Finishing Balance: ${finishing_balance:.2f}")
    
    print(f"\nВозврат комиссий (60%):")
    print(f"  Возврат: ${fee_rebate:.2f}")
    print(f"  Чистые комиссии после возврата: ${net_fees_after_rebate:.2f}")
    
    print(f"\nНовые метрики с учетом возврата:")
    print(f"  Новый Net Profit: ${new_net_profit:.2f} ({new_net_profit_percentage:.2f}%)")
    print(f"  Новый Finishing Balance: ${new_finishing_balance:.2f}")
    print(f"  Улучшение: ${fee_rebate:.2f} ({fee_rebate/starting_balance*100:.2f}%)")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    # Можно передать ID сессии как аргумент
    session_id = sys.argv[1] if len(sys.argv) > 1 else None
    calculate_fee_rebate(session_id)

