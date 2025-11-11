#!/usr/bin/env python3
"""
Strategy Rating System - Ninja-style ranking for Freqtrade strategies
Parses backtest results and calculates Ninja Score with PostgreSQL storage
"""

import json
import zipfile
import hashlib
import re
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
import statistics
import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
import os

# Configuration
FREQTRADE_DIR = Path(__file__).parent
RESULTS_DIR = FREQTRADE_DIR / "user_data" / "backtest_results"
STRATEGIES_DIR = FREQTRADE_DIR / "user_data" / "strategies"

# Database connection (from environment)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/cryptotrader"
)

# Ninja Score weights (exact from ninja.trade)
NINJA_WEIGHTS = {
    "buys": 9,
    "avgprof": 26,
    "totprofp": 26,
    "winp": 24,
    "ddp": -25,  # Negative weight (lower is better)
    "stoploss": 7,
    "sharpe": 7,
    "sortino": 7,
    "calmar": 7,
    "expectancy": 8,
    "profit_factor": 9,
    "cagr": 10,
    "rejected_signals": -25,  # Negative weight
    "backtest_win_percentage": 10
}


class StrategyRatingSystem:
    """Main class for strategy rating and ranking"""
    
    def __init__(self, database_url: str = DATABASE_URL):
        self.database_url = database_url
        self.pool = None
        self._connect()
    
    def _connect(self):
        """Create database connection pool"""
        try:
            self.pool = ThreadedConnectionPool(1, 5, self.database_url)
            print("✅ Подключение к PostgreSQL установлено")
        except Exception as e:
            print(f"❌ Ошибка подключения к БД: {e}")
            raise
    
    def get_connection(self):
        """Get connection from pool"""
        return self.pool.getconn()
    
    def return_connection(self, conn):
        """Return connection to pool"""
        self.pool.putconn(conn)
    
    def calculate_strategy_hash(self, strategy_name: str) -> Optional[str]:
        """Calculate SHA256 hash of strategy file"""
        strategy_file = STRATEGIES_DIR / f"{strategy_name}.py"
        if not strategy_file.exists():
            return None
        
        with open(strategy_file, 'rb') as f:
            content = f.read()
            return hashlib.sha256(content).hexdigest()
    
    def check_lookahead_bias(self, strategy_name: str) -> Tuple[bool, List[str]]:
        """Check strategy for lookahead bias patterns"""
        strategy_file = STRATEGIES_DIR / f"{strategy_name}.py"
        if not strategy_file.exists():
            return False, []
        
        with open(strategy_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        issues = []
        
        # 1. Check for .iat[-1]
        if re.search(r'\.iat\s*\[\s*-\s*1\s*\]', content):
            issues.append("IAT")
        
        # 2. Check for .shift(-1) (future shift)
        if re.search(r'\.shift\s*\(\s*-\s*1\s*\)', content):
            issues.append("FUTURE_SHIFT")
        
        # 3. Check for whole dataframe operations without rolling
        # This is harder to detect, but we can check for common patterns
        if re.search(r'\.min\(\)|\.max\(\)|\.mean\(\)', content):
            # Check if it's used with rolling window
            if not re.search(r'\.rolling|\.ewm', content):
                issues.append("WHOLE_DATAFRAME")
        
        # 4. Check for TA period = 1
        if re.search(r'period\s*=\s*1[,\s\)]', content):
            issues.append("TA_PERIOD_1")
        
        # 5. Manual blacklist patterns (can be extended)
        blacklist_patterns = [
            r'dataframe\[.*\]\s*=\s*dataframe\[.*\]\.shift\(-1\)',
            r'dataframe\.iloc\[-1\]',
        ]
        
        for pattern in blacklist_patterns:
            if re.search(pattern, content):
                issues.append("BLACKLIST_PATTERN")
        
        return len(issues) > 0, issues
    
    def check_tight_trailing_stop(self, backtest_data: Dict) -> bool:
        """Check if strategy has tight trailing stop"""
        strategy_config = backtest_data.get("strategy", {})
        if isinstance(strategy_config, dict):
            # Check for trailing stop parameters
            trailing_stop_positive_offset = strategy_config.get(
                "trailing_stop_positive_offset", 999
            )
            trailing_stop_positive = strategy_config.get(
                "trailing_stop_positive", 999
            )
            
            # Tight trailing: offset <= 0.05 AND positive <= 0.0025
            if (trailing_stop_positive_offset <= 0.05 and 
                trailing_stop_positive <= 0.0025):
                return True
            
            # Or just positive <= 0.0025 (as of 03/16/2024)
            if trailing_stop_positive <= 0.0025:
                return True
        
        return False
    
    def extract_backtest_metrics(self, zip_file: Path) -> Optional[Dict]:
        """Extract metrics from Freqtrade backtest ZIP file"""
        try:
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                # Find JSON file with results
                json_files = [f for f in zip_ref.namelist() if f.endswith('.json')]
                
                if not json_files:
                    return None
                
                # Read first JSON file (usually contains backtest results)
                json_content = zip_ref.read(json_files[0])
                data = json.loads(json_content)
                
                # Extract strategy name (first key)
                strategy_name = list(data.keys())[0] if data else None
                if not strategy_name:
                    return None
                
                strategy_data = data.get(strategy_name, {})
                results = strategy_data.get("results", {})
                
                if not results:
                    return None
                
                # Extract metrics
                metrics = {
                    "strategy_name": strategy_name,
                    "total_trades": results.get("total_trades", 0),
                    "winning_trades": results.get("wins", 0),
                    "losing_trades": results.get("losses", 0),
                    "win_rate": results.get("winrate", 0.0) * 100,  # Convert to percentage
                    "total_profit_pct": results.get("profit_total_pct", 0.0),
                    "roi": results.get("profit_total_pct", 0.0),  # Use total profit as ROI
                    "max_drawdown": abs(results.get("max_drawdown", 0.0)),
                    "profit_factor": results.get("profit_factor", 0.0),
                    "sharpe_ratio": results.get("sharpe_ratio", 0.0),
                    "sortino_ratio": results.get("sortino_ratio", 0.0),
                    "calmar_ratio": results.get("calmar_ratio", 0.0),
                    "expectancy": results.get("expectancy", 0.0),
                    "cagr": results.get("cagr", 0.0),
                    "avg_profit": results.get("profit_total_pct", 0.0) / max(results.get("total_trades", 1), 1),
                    "buys": results.get("total_trades", 0),  # Total trades = buys
                    "rejected_signals": results.get("rejected_signals", 0),
                    "leverage": strategy_data.get("config", {}).get("leverage", 1),
                }
                
                return metrics
                
        except Exception as e:
            print(f"⚠️  Ошибка при извлечении метрик из {zip_file.name}: {e}")
            return None
    
    def calculate_ninja_score(self, metrics: Dict, backtest_count: int) -> Decimal:
        """Calculate Ninja Score using weighted metrics"""
        score = Decimal(0)
        
        # Normalize metrics to 0-100 scale (approximate)
        def normalize(value: float, min_val: float = 0, max_val: float = 100) -> float:
            if max_val == min_val:
                return 0
            return min(100, max(0, ((value - min_val) / (max_val - min_val)) * 100))
        
        # buys (9) - normalize by number of trades
        buys_score = normalize(metrics.get("buys", 0), 0, 1000)
        score += Decimal(buys_score) * Decimal(NINJA_WEIGHTS["buys"])
        
        # avgprof (26) - average profit per trade
        avgprof_score = normalize(metrics.get("avg_profit", 0), -5, 5)
        score += Decimal(avgprof_score) * Decimal(NINJA_WEIGHTS["avgprof"])
        
        # totprofp (26) - total profit percentage
        totprofp_score = normalize(metrics.get("total_profit_pct", 0), -50, 50)
        score += Decimal(totprofp_score) * Decimal(NINJA_WEIGHTS["totprofp"])
        
        # winp (24) - win rate
        winp_score = normalize(metrics.get("win_rate", 0), 0, 100)
        score += Decimal(winp_score) * Decimal(NINJA_WEIGHTS["winp"])
        
        # ddp (-25) - max drawdown (negative, lower is better)
        ddp_score = normalize(metrics.get("max_drawdown", 0), 0, 50)
        score += Decimal(100 - ddp_score) * Decimal(NINJA_WEIGHTS["ddp"])  # Invert
        
        # sharpe (7)
        sharpe_score = normalize(metrics.get("sharpe_ratio", 0), -2, 5)
        score += Decimal(sharpe_score) * Decimal(NINJA_WEIGHTS["sharpe"])
        
        # sortino (7)
        sortino_score = normalize(metrics.get("sortino_ratio", 0), -2, 5)
        score += Decimal(sortino_score) * Decimal(NINJA_WEIGHTS["sortino"])
        
        # calmar (7)
        calmar_score = normalize(metrics.get("calmar_ratio", 0), -2, 5)
        score += Decimal(calmar_score) * Decimal(NINJA_WEIGHTS["calmar"])
        
        # expectancy (8)
        expectancy_score = normalize(metrics.get("expectancy", 0), -1, 1)
        score += Decimal(expectancy_score) * Decimal(NINJA_WEIGHTS["expectancy"])
        
        # profit_factor (9)
        pf_score = normalize(metrics.get("profit_factor", 0), 0, 5)
        score += Decimal(pf_score) * Decimal(NINJA_WEIGHTS["profit_factor"])
        
        # cagr (10)
        cagr_score = normalize(metrics.get("cagr", 0), -50, 100)
        score += Decimal(cagr_score) * Decimal(NINJA_WEIGHTS["cagr"])
        
        # rejected_signals (-25) - negative weight
        rejected_score = normalize(metrics.get("rejected_signals", 0), 0, 100)
        score += Decimal(100 - rejected_score) * Decimal(NINJA_WEIGHTS["rejected_signals"])
        
        # backtest_win_percentage (10)
        backtest_win_pct = (backtest_count / max(backtest_count, 1)) * 100 if backtest_count > 0 else 0
        score += Decimal(backtest_win_pct) * Decimal(NINJA_WEIGHTS["backtest_win_percentage"])
        
        return score
    
    def process_all_backtests(self) -> Dict[str, List[Dict]]:
        """Process all backtest results and group by strategy"""
        strategies_metrics = {}
        
        print(f"📊 Обработка результатов бэктестов из {RESULTS_DIR}")
        
        # Find all ZIP files
        zip_files = list(RESULTS_DIR.glob("*.zip"))
        print(f"   Найдено ZIP файлов: {len(zip_files)}")
        
        for zip_file in zip_files:
            metrics = self.extract_backtest_metrics(zip_file)
            if not metrics:
                continue
            
            strategy_name = metrics["strategy_name"]
            
            if strategy_name not in strategies_metrics:
                strategies_metrics[strategy_name] = []
            
            strategies_metrics[strategy_name].append(metrics)
        
        print(f"✅ Обработано стратегий: {len(strategies_metrics)}")
        for strategy, metrics_list in strategies_metrics.items():
            print(f"   - {strategy}: {len(metrics_list)} бэктестов")
        
        return strategies_metrics
    
    def calculate_median_metrics(self, metrics_list: List[Dict]) -> Dict:
        """Calculate median values from list of metrics"""
        if not metrics_list:
            return {}
        
        # Get all numeric values
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
        
        return median_metrics
    
    def save_to_database(self, strategy_name: str, metrics_list: List[Dict]):
        """Save strategy rating to PostgreSQL"""
        if not metrics_list:
            return
        
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Calculate median metrics
                median_metrics = self.calculate_median_metrics(metrics_list)
                
                # Check for biases
                has_lookahead, lookahead_issues = self.check_lookahead_bias(strategy_name)
                strategy_hash = self.calculate_strategy_hash(strategy_name)
                
                # Check for tight trailing stop (check first backtest)
                # Note: This requires full backtest data, simplified for now
                has_tight_trailing = False
                
                # Calculate backtest win percentage
                profitable_backtests = sum(
                    1 for m in metrics_list if m.get("total_profit_pct", 0) > 0
                )
                backtest_win_pct = (profitable_backtests / len(metrics_list)) * 100
                
                # Calculate Ninja Score
                # Use median metrics for score calculation
                combined_metrics = {
                    **median_metrics,
                    "backtest_win_percentage": backtest_win_pct,
                }
                ninja_score = self.calculate_ninja_score(combined_metrics, len(metrics_list))
                
                # Get leverage (should be 1 for ranking)
                leverage = metrics_list[0].get("leverage", 1) if metrics_list else 1
                
                # Check if strategy should be stalled
                is_stalled = False
                stall_reason = None
                
                # Check: negative average profit + total profit negative over 6 months
                avg_profit = statistics.mean([m.get("total_profit_pct", 0) for m in metrics_list])
                if avg_profit < -0.30 and all(m.get("total_profit_pct", 0) < 0 for m in metrics_list):
                    is_stalled = True
                    stall_reason = "negative"
                
                # Check: >=90% negative backtests
                negative_count = sum(1 for m in metrics_list if m.get("total_profit_pct", 0) < 0)
                if len(metrics_list) >= 12 and (negative_count / len(metrics_list)) >= 0.90:
                    is_stalled = True
                    stall_reason = "90_percent_negative"
                
                # Check: lookahead bias
                if has_lookahead:
                    is_stalled = True
                    stall_reason = "biased"
                
                # Check: no trades
                if all(m.get("total_trades", 0) == 0 for m in metrics_list):
                    is_stalled = True
                    stall_reason = "no_trades"
                
                # Insert or update strategy_ratings
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
                        strategy_hash, is_stalled, stall_reason, is_active
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
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
                        has_lookahead_bias = EXCLUDED.has_lookahead_bias,
                        has_tight_trailing_stop = EXCLUDED.has_tight_trailing_stop,
                        leverage = EXCLUDED.leverage,
                        strategy_hash = EXCLUDED.strategy_hash,
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
                    has_lookahead,
                    has_tight_trailing,
                    leverage,
                    strategy_hash,
                    is_stalled,
                    stall_reason,
                    not is_stalled
                ))
                
                rating_id = cur.fetchone()["id"]
                conn.commit()
                
                print(f"✅ Сохранен рейтинг для {strategy_name} (ID: {rating_id}, Score: {ninja_score:.2f})")
                
                return rating_id
                
        except Exception as e:
            conn.rollback()
            print(f"❌ Ошибка при сохранении в БД: {e}")
            raise
        finally:
            self.return_connection(conn)
    
    def run(self):
        """Main execution method"""
        print("=" * 70)
        print("🎯 Strategy Rating System - Ninja-style Ranking")
        print("=" * 70)
        print()
        
        # Process all backtests
        strategies_metrics = self.process_all_backtests()
        
        if not strategies_metrics:
            print("❌ Нет результатов для обработки")
            return
        
        # Save to database
        print()
        print("💾 Сохранение в PostgreSQL...")
        for strategy_name, metrics_list in strategies_metrics.items():
            try:
                self.save_to_database(strategy_name, metrics_list)
            except Exception as e:
                print(f"❌ Ошибка для {strategy_name}: {e}")
        
        print()
        print("=" * 70)
        print("✅ Рейтинг стратегий обновлен!")
        print("=" * 70)


def main():
    """Main entry point"""
    system = StrategyRatingSystem()
    system.run()


if __name__ == "__main__":
    main()

