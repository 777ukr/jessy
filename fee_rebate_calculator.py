#!/usr/bin/env python3
"""
Калькулятор возврата комиссий (60%) на Gate.io фьючерсах
Использование: python3 fee_rebate_calculator.py <total_paid_fees> <net_profit> <starting_balance>
Или просто запустите скрипт и введите данные вручную
"""

import sys

def calculate_fee_rebate(total_paid_fees, net_profit, starting_balance):
    """
    Рассчитывает возврат комиссий (60%) и влияние на метрики
    """
    # Возврат 60% комиссий
    fee_rebate = total_paid_fees * 0.60
    net_fees_after_rebate = total_paid_fees - fee_rebate
    
    # Текущие метрики
    finishing_balance = starting_balance + net_profit
    net_profit_percentage = (net_profit / starting_balance) * 100
    
    # Новые метрики с учетом возврата
    new_net_profit = net_profit + fee_rebate
    new_finishing_balance = finishing_balance + fee_rebate
    new_net_profit_percentage = (new_net_profit / starting_balance) * 100
    
    # Выводим результаты
    print("=" * 70)
    print("РАСЧЕТ ВОЗВРАТА КОМИССИЙ (60%) НА GATE.IO ФЬЮЧЕРСАХ")
    print("=" * 70)
    print(f"\n📊 ТЕКУЩИЕ МЕТРИКИ:")
    print(f"   Total Paid Fees:        ${total_paid_fees:,.2f}")
    print(f"   Net Profit:             ${net_profit:,.2f} ({net_profit_percentage:.2f}%)")
    print(f"   Starting Balance:       ${starting_balance:,.2f}")
    print(f"   Finishing Balance:      ${finishing_balance:,.2f}")
    
    print(f"\n💰 ВОЗВРАТ КОМИССИЙ (60%):")
    print(f"   Возврат комиссий:       ${fee_rebate:,.2f}")
    print(f"   Чистые комиссии:        ${net_fees_after_rebate:,.2f}")
    print(f"   Экономия:               ${fee_rebate:,.2f} ({fee_rebate/starting_balance*100:.2f}%)")
    
    print(f"\n📈 НОВЫЕ МЕТРИКИ С УЧЕТОМ ВОЗВРАТА:")
    print(f"   Новый Net Profit:       ${new_net_profit:,.2f} ({new_net_profit_percentage:.2f}%)")
    print(f"   Новый Finishing Balance: ${new_finishing_balance:,.2f}")
    print(f"   Улучшение прибыли:      ${fee_rebate:,.2f} ({fee_rebate/starting_balance*100:.2f}%)")
    
    # Сравнение
    improvement_pct = new_net_profit_percentage - net_profit_percentage
    print(f"\n📊 СРАВНЕНИЕ:")
    print(f"   Улучшение Net Profit:   ${fee_rebate:,.2f}")
    print(f"   Улучшение в %:          {improvement_pct:+.2f}%")
    
    print("\n" + "=" * 70)
    
    return {
        'fee_rebate': fee_rebate,
        'new_net_profit': new_net_profit,
        'new_net_profit_percentage': new_net_profit_percentage,
        'improvement': fee_rebate
    }

if __name__ == "__main__":
    if len(sys.argv) >= 4:
        # Данные из аргументов командной строки
        total_paid_fees = float(sys.argv[1])
        net_profit = float(sys.argv[2])
        starting_balance = float(sys.argv[3])
    else:
        # Интерактивный ввод
        print("Введите данные из результатов бектеста:")
        print("(Можно найти в разделе Portfolio Performance)")
        print()
        
        try:
            total_paid_fees = float(input("Total Paid Fees ($): "))
            net_profit = float(input("Net Profit ($): "))
            starting_balance = float(input("Starting Balance ($, обычно 10000): ") or "10000")
        except ValueError:
            print("Ошибка: введите корректные числовые значения")
            sys.exit(1)
        except KeyboardInterrupt:
            print("\nОтменено")
            sys.exit(0)
    
    calculate_fee_rebate(total_paid_fees, net_profit, starting_balance)



