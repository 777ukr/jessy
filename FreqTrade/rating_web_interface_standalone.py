#!/usr/bin/env python3
"""
Web Interface for Strategy Rating System - Standalone version
Reads from JSON files instead of PostgreSQL
"""

import json
from pathlib import Path
from datetime import datetime

FREQTRADE_DIR = Path(__file__).parent
RATINGS_DIR = FREQTRADE_DIR / "user_data" / "ratings"
WEB_DIR = FREQTRADE_DIR / "user_data" / "web"


# Автоматическое обнаружение всех стратегий
def get_all_strategies():
    """Автоматически находит все стратегии"""
    strategies_dir = FREQTRADE_DIR / "user_data" / "strategies"
    strategies = []
    for file in strategies_dir.glob("*.py"):
        if file.name != "__init__.py" and not file.name.startswith("_"):
            strategies.append(file.stem)
    return sorted(strategies)

def get_rankings_from_json(limit: int = 100):
    """Get strategy rankings from JSON file"""
    rankings_file = RATINGS_DIR / "rankings.json"
    
    if not rankings_file.exists():
        return []
    
    try:
        data = json.loads(rankings_file.read_text())
        rankings = data.get("rankings", [])
        
        # Фильтруем стратегии (автообнаружение - все стратегии из файловой системы)
        all_strategies = get_all_strategies()
        filtered = []
        for r in rankings:
            strategy_name = r.get("strategy_name", "")
            strategy_key = r.get("strategy_key", "")
            
            # Проверяем как полное имя, так и базовое (на случай если стратегия называется по-другому)
            base_strategy = strategy_name.split("_")[0] if "_" in strategy_name else strategy_name
            
            # Проверяем существование стратегии:
            # 1. Точное совпадение
            # 2. Базовое имя совпадает
            # 3. Есть стратегии, начинающиеся с базового имени (например, "EMA" -> "EMA_05_02_10_05_02")
            # 4. Проверяем strategy_key (может содержать полное имя стратегии)
            strategy_exists = (
                strategy_name in all_strategies or
                base_strategy in all_strategies or
                any(s.startswith(base_strategy + "_") or s == base_strategy for s in all_strategies) or
                (strategy_key.split("_")[0] in all_strategies if strategy_key and "_" in strategy_key else False)
            )
            
            # Включаем стратегию если она существует в файловой системе
            # Показываем ВСЕ стратегии с разными периодами тестирования (не группируем)
            # Игнорируем is_active - показываем все стратегии с бэктестами
            if strategy_exists and not r.get("has_lookahead_bias", False):
                filtered.append(r)
        
        return filtered[:limit]
    except Exception as e:
        print(f"❌ Ошибка при чтении рейтинга: {e}")
        return []


def create_ranking_html(rankings):
    """Create HTML page with strategy rankings"""
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Strategy Rankings - Ninja Style</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            min-height: 100vh;
            padding: 20px;
            color: #333;
        }}
        .container {{
            max-width: 1600px;
            margin: 0 auto;
        }}
        .header {{
            background: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header h1 {{
            color: #1e3c72;
            margin-bottom: 10px;
            font-size: 32px;
        }}
        .stats-bar {{
            display: flex;
            gap: 20px;
            margin-top: 20px;
        }}
        .stat-badge {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 10px 20px;
            border-radius: 5px;
            font-weight: 600;
        }}
        .ranking-table {{
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        thead {{
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white;
        }}
        th {{
            padding: 15px;
            text-align: left;
            font-weight: 600;
            font-size: 14px;
        }}
        th.rank {{
            width: 60px;
            text-align: center;
        }}
        th.score {{
            width: 120px;
            text-align: center;
        }}
        td {{
            padding: 12px 15px;
            border-bottom: 1px solid #e0e0e0;
        }}
        tr:hover {{
            background: #f5f5f5;
        }}
        .rank-badge {{
            display: inline-block;
            width: 40px;
            height: 40px;
            line-height: 40px;
            text-align: center;
            border-radius: 50%;
            font-weight: bold;
            font-size: 18px;
        }}
        .rank-1 {{
            background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%);
            color: white;
        }}
        .rank-2 {{
            background: linear-gradient(135deg, #C0C0C0 0%, #808080 100%);
            color: white;
        }}
        .rank-3 {{
            background: linear-gradient(135deg, #CD7F32 0%, #8B4513 100%);
            color: white;
        }}
        .rank-other {{
            background: #e0e0e0;
            color: #666;
        }}
        .score-cell {{
            text-align: center;
            font-weight: bold;
            font-size: 18px;
        }}
        .score-high {{
            color: #4CAF50;
        }}
        .score-medium {{
            color: #FF9800;
        }}
        .score-low {{
            color: #f44336;
        }}
        .positive {{
            color: #4CAF50;
            font-weight: 600;
        }}
        .negative {{
            color: #f44336;
            font-weight: 600;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            margin: 2px;
        }}
        .badge-active {{
            background: #4CAF50;
            color: white;
        }}
        .badge-stalled {{
            background: #f44336;
            color: white;
        }}
        .badge-bias {{
            background: #FF9800;
            color: white;
        }}
        .footer {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
            text-align: center;
            color: #666;
            font-size: 14px;
        }}
        .info-box {{
            background: #e3f2fd;
            border-left: 4px solid #2196F3;
            padding: 15px;
            margin: 20px 0;
            border-radius: 5px;
        }}
        .metric {{
            font-family: 'Courier New', monospace;
            font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏆 Strategy Rankings - Ninja Style</h1>
            <p style="color: #666; margin-top: 10px;">
                Рейтинг стратегий на основе медианных значений бэктестов
            </p>
            <div class="stats-bar">
                <div class="stat-badge">
                    📊 Всего стратегий: {len(rankings)}
                </div>
                <div class="stat-badge">
                    ⏰ Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M')}
                </div>
            </div>
        </div>

        <div class="info-box">
            <strong>ℹ️ Критерии ранжирования:</strong>
            <ul style="margin: 10px 0 0 20px;">
                <li>Только стратегии с leverage = 1x</li>
                <li>Без lookahead bias</li>
                <li>Без tight trailing stops</li>
                <li>Минимум 3 бэктеста и 10 сделок</li>
                <li>Сортировка по Ninja Score (взвешенная оценка)</li>
            </ul>
        </div>

        <div class="ranking-table">
            <table>
                <thead>
                    <tr>
                        <th class="rank">#</th>
                        <th>Стратегия</th>
                        <th>Бэктестов</th>
                        <th>Сделок</th>
                        <th>Win Rate</th>
                        <th>Profit %</th>
                        <th>Profit Factor</th>
                        <th>Sharpe</th>
                        <th>Drawdown</th>
                        <th class="score">Ninja Score</th>
                        <th>Статус</th>
                    </tr>
                </thead>
                <tbody>
"""
    
    for idx, strategy in enumerate(rankings, 1):
        rank_class = "rank-1" if idx == 1 else "rank-2" if idx == 2 else "rank-3" if idx == 3 else "rank-other"
        
        ninja_score = float(strategy.get("ninja_score", 0))
        score_class = "score-high" if ninja_score > 500 else "score-medium" if ninja_score > 0 else "score-low"
        
        win_rate = float(strategy.get("median_win_rate", 0))
        profit_pct = float(strategy.get("median_total_profit_pct", 0))
        profit_factor = float(strategy.get("median_profit_factor", 0))
        sharpe = float(strategy.get("median_sharpe_ratio", 0))
        drawdown = float(strategy.get("median_max_drawdown", 0))
        
        status_badges = []
        if strategy.get("is_stalled"):
            status_badges.append('<span class="badge badge-stalled">Stalled</span>')
        elif strategy.get("has_lookahead_bias"):
            status_badges.append('<span class="badge badge-bias">Bias</span>')
        else:
            status_badges.append('<span class="badge badge-active">Active</span>')
        
        html += f"""
                    <tr>
                        <td>
                            <span class="rank-badge {rank_class}">{idx}</span>
                        </td>
                        <td><strong>{strategy['strategy_name']}</strong></td>
                        <td>{strategy.get('total_backtests', 0)}</td>
                        <td>{strategy.get('median_total_trades', 0)}</td>
                        <td class="{'positive' if win_rate >= 50 else 'negative'}">{win_rate:.2f}%</td>
                        <td class="{'positive' if profit_pct >= 0 else 'negative'}">{profit_pct:+.2f}%</td>
                        <td class="{'positive' if profit_factor >= 1 else 'negative'}">{profit_factor:.2f}</td>
                        <td class="metric">{sharpe:.2f}</td>
                        <td class="negative">{drawdown:.2f}%</td>
                        <td class="score-cell {score_class}">{ninja_score:.0f}</td>
                        <td>{' '.join(status_badges)}</td>
                    </tr>
"""
    
    html += """
                </tbody>
            </table>
        </div>

        <div class="footer">
            <p>📊 Ninja Score рассчитывается по формуле с весами:<br>
            buys(9), avgprof(26), totprofp(26), winp(24), ddp(-25), stoploss(7), sharpe(7), sortino(7), calmar(7), expectancy(8), profit_factor(9), cagr(10), rejected_signals(-25), backtest_win_percentage(10)</p>
            <p style="margin-top: 10px;">🔄 Обновление: запустите <code>python3 strategy_rating_system_standalone.py</code></p>
        </div>
    </div>
</body>
</html>
"""
    
    html_file = WEB_DIR / "strategy_rankings.html"
    html_file.write_text(html, encoding='utf-8')
    
    print(f"✅ HTML страница создана: {html_file}")
    return html_file


def main():
    """Main entry point"""
    print("🌐 Генерация веб-интерфейса рейтинга...")
    
    rankings = get_rankings_from_json()
    
    if not rankings:
        print("⚠️  Нет данных для отображения")
        print("💡 Запустите: python3 strategy_rating_system_standalone.py")
        return
    
    html_file = create_ranking_html(rankings)
    
    print(f"\n✅ Веб-интерфейс создан!")
    print(f"🌐 Откройте: file://{html_file.absolute()}")


if __name__ == "__main__":
    main()

