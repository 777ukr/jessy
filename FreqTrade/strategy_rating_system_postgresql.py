#!/usr/bin/env python3
"""
Strategy Rating System - PostgreSQL Version
Полная интеграция с PostgreSQL для хранения всех данных
"""

import json
import zipfile
import hashlib
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import statistics
import os
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from psycopg2.pool import ThreadedConnectionPool

# Configuration
FREQTRADE_DIR = Path(__file__).parent
RESULTS_DIR = FREQTRADE_DIR / "user_data" / "backtest_results"
STRATEGIES_DIR = FREQTRADE_DIR / "user_data" / "strategies"

# Пытаемся получить DATABASE_URL из .env или используем дефолт
ENV_FILE = FREQTRADE_DIR.parent / ".env"
if ENV_FILE.exists():
    with open(ENV_FILE, 'r') as f:
        for line in f:
            if line.startswith('DATABASE_URL='):
                DATABASE_URL = line.split('=', 1)[1].strip().strip('"').strip("'")
                break
        else:
            DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cryptotrader")
else:
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cryptotrader")

# Ninja Score weights
NINJA_WEIGHTS = {
    "buys": 9,
    "avgprof": 26,
    "totprofp": 26,
    "winp": 24,
    "ddp": -25,
    "stoploss": 7,
    "sharpe": 7,
    "sortino": 7,
    "calmar": 7,
    "expectancy": 8,
    "profit_factor": 9,
    "cagr": 10,
    "rejected_signals": -25,
    "backtest_win_percentage": 10
}


class StrategyRatingSystemPostgreSQL:
    """Система рейтинга с полной интеграцией PostgreSQL"""
    
    def __init__(self, database_url: str = DATABASE_URL):
        self.database_url = database_url
        self.pool = None
        self._connect()
    
    def _connect(self):
        """Создать пул соединений"""
        try:
            self.pool = ThreadedConnectionPool(1, 10, self.database_url)
            print("✅ Подключение к PostgreSQL установлено")
        except Exception as e:
            print(f"❌ Ошибка подключения к БД: {e}")
            raise
    
    def get_connection(self):
        """Получить соединение из пула"""
        return self.pool.getconn()
    
    def return_connection(self, conn):
        """Вернуть соединение в пул"""
        self.pool.putconn(conn)
    
    def extract_backtest_metrics(self, zip_file: Path) -> Optional[Dict]:
        """Извлечь метрики из ZIP файла бэктеста"""
        try:
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                json_files = [f for f in zip_ref.namelist() if f.endswith('.json')]
                
                if json_files:
                    json_content = zip_ref.read(json_files[0])
                    data = json.loads(json_content)
                    
                    if "strategy" in data and data["strategy"]:
                        strategy_name = list(data["strategy"].keys())[0]
                        strategy_data = data["strategy"][strategy_name]
                        
                        total_trades = strategy_data.get("total_trades", 0)
                        wins = strategy_data.get("wins", 0)
                        losses = strategy_data.get("losses", 0)
                        profit_total_pct = strategy_data.get("profit_total_pct", 0.0)
                        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
                        
                        return {
                            "strategy_name": strategy_name,
                            "total_trades": total_trades,
                            "winning_trades": wins,
                            "losing_trades": losses,
                            "win_rate": win_rate,
                            "total_profit_pct": profit_total_pct,
                            "roi": profit_total_pct,
                            "max_drawdown": abs(strategy_data.get("max_drawdown", 0.0)),
                            "profit_factor": strategy_data.get("profit_factor", 0.0),
                            "sharpe_ratio": strategy_data.get("sharpe", 0.0),
                            "sortino_ratio": strategy_data.get("sortino", 0.0),
                            "calmar_ratio": strategy_data.get("calmar", 0.0),
                            "expectancy": strategy_data.get("expectancy", 0.0),
                            "cagr": strategy_data.get("cagr", 0.0),
                            "avg_profit": profit_total_pct / max(total_trades, 1),
                            "buys": total_trades,
                            "rejected_signals": strategy_data.get("rejected_signals", 0),
                            "leverage": 1,  # Можно извлечь из конфига
                        }
        except Exception as e:
            print(f"⚠️  Ошибка при извлечении метрик: {e}")
            return None
    
    def calculate_ninja_score(self, metrics: Dict, backtest_count: int) -> float:
        """Рассчитать Ninja Score"""
        score = 0.0
        
        def normalize(value: float, min_val: float = 0, max_val: float = 100) -> float:
            if max_val == min_val:
                return 0
            return min(100, max(0, ((value - min_val) / (max_val - min_val)) * 100))
        
        score += normalize(metrics.get("buys", 0), 0, 1000) * NINJA_WEIGHTS["buys"]
        score += normalize(metrics.get("avg_profit", 0), -5, 5) * NINJA_WEIGHTS["avgprof"]
        score += normalize(metrics.get("total_profit_pct", 0), -50, 50) * NINJA_WEIGHTS["totprofp"]
        score += normalize(metrics.get("win_rate", 0), 0, 100) * NINJA_WEIGHTS["winp"]
        score += (100 - normalize(metrics.get("max_drawdown", 0), 0, 50)) * NINJA_WEIGHTS["ddp"]
        score += normalize(metrics.get("sharpe_ratio", 0), -2, 5) * NINJA_WEIGHTS["sharpe"]
        score += normalize(metrics.get("sortino_ratio", 0), -2, 5) * NINJA_WEIGHTS["sortino"]
        score += normalize(metrics.get("calmar_ratio", 0), -2, 5) * NINJA_WEIGHTS["calmar"]
        score += normalize(metrics.get("expectancy", 0), -1, 1) * NINJA_WEIGHTS["expectancy"]
        score += normalize(metrics.get("profit_factor", 0), 0, 5) * NINJA_WEIGHTS["profit_factor"]
        score += normalize(metrics.get("cagr", 0), -50, 100) * NINJA_WEIGHTS["cagr"]
        score += (100 - normalize(metrics.get("rejected_signals", 0), 0, 100)) * NINJA_WEIGHTS["rejected_signals"]
        
        backtest_win_pct = (backtest_count / max(backtest_count, 1)) * 100 if backtest_count > 0 else 0
        score += backtest_win_pct * NINJA_WEIGHTS["backtest_win_percentage"]
        
        return score
    
    def process_and_save_to_db(self):
        """Обработать все бэктесты и сохранить в PostgreSQL"""
        print("=" * 70)
        print("🎯 Strategy Rating System - PostgreSQL")
        print("=" * 70)
        print()
        
        # Собираем метрики по стратегиям
        strategies_metrics = {}
        
        zip_files = list(RESULTS_DIR.glob("*.zip"))
        print(f"📊 Найдено ZIP файлов: {len(zip_files)}")
        
        for zip_file in zip_files:
            metrics = self.extract_backtest_metrics(zip_file)
            if not metrics:
                continue
            
            strategy_name = metrics["strategy_name"]
            if strategy_name not in strategies_metrics:
                strategies_metrics[strategy_name] = []
            
            strategies_metrics[strategy_name].append(metrics)
        
        print(f"✅ Обработано стратегий: {len(strategies_metrics)}")
        
        # Сохраняем в БД
        conn = self.get_connection()
        try:
            for strategy_name, metrics_list in strategies_metrics.items():
                self._save_strategy_rating_to_db(conn, strategy_name, metrics_list)
            conn.commit()
            print("\n✅ Все данные сохранены в PostgreSQL")
        except Exception as e:
            conn.rollback()
            print(f"❌ Ошибка при сохранении: {e}")
            raise
        finally:
            self.return_connection(conn)
    
    def _save_strategy_rating_to_db(self, conn, strategy_name: str, metrics_list: List[Dict]):
        """Сохранить рейтинг стратегии в БД"""
        if not metrics_list:
            return
        
        # Рассчитываем медианные значения
        numeric_fields = [
            "total_trades", "winning_trades", "losing_trades", "win_rate",
            "total_profit_pct", "roi", "max_drawdown", "profit_factor",
            "sharpe_ratio", "sortino_ratio", "calmar_ratio", "expectancy",
            "cagr", "avg_profit", "buys", "rejected_signals"
        ]
        
        median_metrics = {}
        for field in numeric_fields:
            values = [m.get(field, 0) for m in metrics_list if field in m]
            if values:
                median_metrics[f"median_{field}"] = statistics.median(values)
        
        # Процент прибыльных бэктестов
        profitable_backtests = sum(1 for m in metrics_list if m.get("total_profit_pct", 0) > 0)
        backtest_win_pct = (profitable_backtests / len(metrics_list)) * 100
        
        # Ninja Score
        combined_metrics = {
            **{k.replace("median_", ""): v for k, v in median_metrics.items()},
            "backtest_win_percentage": backtest_win_pct,
        }
        ninja_score = self.calculate_ninja_score(combined_metrics, len(metrics_list))
        
        # Проверка на stalled
        avg_profit = statistics.mean([m.get("total_profit_pct", 0) for m in metrics_list])
        is_stalled = False
        stall_reason = None
        
        if avg_profit < -0.30 and all(m.get("total_profit_pct", 0) < 0 for m in metrics_list):
            is_stalled = True
            stall_reason = "negative"
        
        negative_count = sum(1 for m in metrics_list if m.get("total_profit_pct", 0) < 0)
        if len(metrics_list) >= 12 and (negative_count / len(metrics_list)) >= 0.90:
            is_stalled = True
            stall_reason = "90_percent_negative"
        
        if all(m.get("total_trades", 0) == 0 for m in metrics_list):
            is_stalled = True
            stall_reason = "no_trades"
        
        leverage = metrics_list[0].get("leverage", 1) if metrics_list else 1
        
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO strategy_ratings (
                    strategy_name, exchange, stake_currency,
                    total_backtests,
                    median_buys, median_total_trades, median_winning_trades,
                    median_losing_trades, median_win_rate,
                    median_avg_profit, median_total_profit_pct, median_roi,
                    median_max_drawdown, median_sharpe_ratio, median_sortino_ratio,
                    median_calmar_ratio, median_profit_factor, median_expectancy,
                    median_cagr, median_rejected_signals,
                    backtest_win_percentage, ninja_score,
                    has_lookahead_bias, has_tight_trailing_stop, leverage,
                    is_stalled, stall_reason, is_active
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (strategy_name, exchange, stake_currency)
                DO UPDATE SET
                    updated_at = NOW(),
                    total_backtests = EXCLUDED.total_backtests,
                    median_buys = EXCLUDED.median_buys,
                    median_total_trades = EXCLUDED.median_total_trades,
                    median_winning_trades = EXCLUDED.median_winning_trades,
                    median_losing_trades = EXCLUDED.median_losing_trades,
                    median_win_rate = EXCLUDED.median_win_rate,
                    median_avg_profit = EXCLUDED.median_avg_profit,
                    median_total_profit_pct = EXCLUDED.median_total_profit_pct,
                    median_roi = EXCLUDED.median_roi,
                    median_max_drawdown = EXCLUDED.median_max_drawdown,
                    median_sharpe_ratio = EXCLUDED.median_sharpe_ratio,
                    median_sortino_ratio = EXCLUDED.median_sortino_ratio,
                    median_calmar_ratio = EXCLUDED.median_calmar_ratio,
                    median_profit_factor = EXCLUDED.median_profit_factor,
                    median_expectancy = EXCLUDED.median_expectancy,
                    median_cagr = EXCLUDED.median_cagr,
                    median_rejected_signals = EXCLUDED.median_rejected_signals,
                    backtest_win_percentage = EXCLUDED.backtest_win_percentage,
                    ninja_score = EXCLUDED.ninja_score,
                    leverage = EXCLUDED.leverage,
                    is_stalled = EXCLUDED.is_stalled,
                    stall_reason = EXCLUDED.stall_reason,
                    last_backtest_date = NOW()
                RETURNING id
            """, (
                strategy_name, "gateio", "USDT",
                len(metrics_list),
                median_metrics.get("median_buys"),
                median_metrics.get("median_total_trades"),
                median_metrics.get("median_winning_trades"),
                median_metrics.get("median_losing_trades"),
                median_metrics.get("median_win_rate"),
                median_metrics.get("median_avg_profit"),
                median_metrics.get("median_total_profit_pct"),
                median_metrics.get("median_roi"),
                median_metrics.get("median_max_drawdown"),
                median_metrics.get("median_sharpe_ratio"),
                median_metrics.get("median_sortino_ratio"),
                median_metrics.get("median_calmar_ratio"),
                median_metrics.get("median_profit_factor"),
                median_metrics.get("median_expectancy"),
                median_metrics.get("median_cagr"),
                median_metrics.get("median_rejected_signals"),
                backtest_win_pct,
                float(ninja_score),
                False,  # has_lookahead_bias
                False,  # has_tight_trailing_stop
                leverage,
                is_stalled,
                stall_reason,
                not is_stalled
            ))
            
            rating_id = cur.fetchone()[0]
            print(f"✅ Сохранен рейтинг для {strategy_name} (ID: {rating_id}, Score: {ninja_score:.2f})")


def main():
    """Main entry point"""
    system = StrategyRatingSystemPostgreSQL()
    system.process_and_save_to_db()


if __name__ == "__main__":
    main()



