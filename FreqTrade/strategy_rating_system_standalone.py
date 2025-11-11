#!/usr/bin/env python3
"""
Strategy Rating System - Standalone version (works without PostgreSQL)
Saves results to JSON, can be imported to PostgreSQL later
"""

import json
import zipfile
import hashlib
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
import statistics

# Configuration
FREQTRADE_DIR = Path(__file__).parent
RESULTS_DIR = FREQTRADE_DIR / "user_data" / "backtest_results"
STRATEGIES_DIR = FREQTRADE_DIR / "user_data" / "strategies"
RATINGS_DIR = FREQTRADE_DIR / "user_data" / "ratings"
RATINGS_DIR.mkdir(parents=True, exist_ok=True)

# Автоматическое обнаружение всех стратегий
def get_all_strategies():
    """Автоматически находит все стратегии в папке"""
    strategies = []
    for file in STRATEGIES_DIR.glob("*.py"):
        if file.name != "__init__.py" and not file.name.startswith("_"):
            strategies.append(file.stem)
    return sorted(strategies)

# Ninja Score weights (exact from ninja.trade)
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


class StrategyRatingSystemStandalone:
    """Standalone version - saves to JSON instead of PostgreSQL"""
    
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
        if re.search(r'\.min\(\)|\.max\(\)|\.mean\(\)', content):
            if not re.search(r'\.rolling|\.ewm', content):
                issues.append("WHOLE_DATAFRAME")
        
        # 4. Check for TA period = 1
        if re.search(r'period\s*=\s*1[,\s\)]', content):
            issues.append("TA_PERIOD_1")
        
        return len(issues) > 0, issues
    
    def extract_backtest_metrics(self, zip_file: Path) -> Optional[Dict]:
        """Extract metrics from Freqtrade backtest ZIP file"""
        try:
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                # Try to find JSON file or read from meta.json
                json_files = [f for f in zip_ref.namelist() if f.endswith('.json')]
                
                # Also check for .meta.json file outside ZIP
                meta_file = zip_file.with_suffix('.meta.json')
                if meta_file.exists():
                    try:
                        meta_data = json.loads(meta_file.read_text())
                        strategy_name = list(meta_data.keys())[0] if meta_data else None
                        if strategy_name:
                            strategy_meta = meta_data.get(strategy_name, {})
                            results = strategy_meta.get("results", {})
                            
                            if results:
                                # Extract timeframe and timerange
                                timeframe = strategy_meta.get("config", {}).get("timeframe", "5m")
                                timerange = strategy_meta.get("config", {}).get("timerange", "")
                                
                                # Calculate days from timerange
                                days_tested = None
                                if timerange and len(timerange) == 17:
                                    try:
                                        start_date = datetime.strptime(timerange[:8], "%Y%m%d")
                                        end_date = datetime.strptime(timerange[9:], "%Y%m%d")
                                        days_tested = (end_date - start_date).days
                                    except:
                                        pass
                                
                                metrics = {
                                    "strategy_name": strategy_name,
                                    "total_trades": results.get("total_trades", 0),
                                    "winning_trades": results.get("wins", 0),
                                    "losing_trades": results.get("losses", 0),
                                    "win_rate": results.get("winrate", 0.0) * 100,
                                    "total_profit_pct": results.get("profit_total_pct", 0.0),
                                    "roi": results.get("profit_total_pct", 0.0),
                                    "max_drawdown": abs(results.get("max_drawdown", 0.0)),
                                    "profit_factor": results.get("profit_factor", 0.0),
                                    "sharpe_ratio": results.get("sharpe_ratio", 0.0),
                                    "sortino_ratio": results.get("sortino_ratio", 0.0),
                                    "calmar_ratio": results.get("calmar_ratio", 0.0),
                                    "expectancy": results.get("expectancy", 0.0),
                                    "cagr": results.get("cagr", 0.0),
                                    "avg_profit": results.get("profit_total_pct", 0.0) / max(results.get("total_trades", 1), 1),
                                    "buys": results.get("total_trades", 0),
                                    "rejected_signals": results.get("rejected_signals", 0),
                                    "leverage": strategy_meta.get("config", {}).get("leverage", 1),
                                    "timeframe": timeframe,
                                    "timerange": timerange,
                                    "days_tested": days_tested,
                                }
                                return metrics
                    except Exception:
                        pass
                
                # Try to read from ZIP JSON
                if json_files:
                    json_content = zip_ref.read(json_files[0])
                    data = json.loads(json_content)
                    
                    # Freqtrade structure: {"strategy": {"StrategyName": {...}}, "strategy_comparison": [...]}
                    if "strategy" in data and data["strategy"]:
                        strategy_name = list(data["strategy"].keys())[0]
                        strategy_data = data["strategy"][strategy_name]
                        
                        # Try to get total_trades from multiple sources
                        total_trades = strategy_data.get("total_trades", 0)
                        
                        # If total_trades is 0, check trades array
                        if total_trades == 0:
                            trades_array = strategy_data.get("trades", [])
                            if trades_array:
                                total_trades = len(trades_array)
                        
                        # Also check results_per_pair for aggregated trades
                        if total_trades == 0:
                            results_per_pair = strategy_data.get("results_per_pair", {})
                            if results_per_pair:
                                # results_per_pair может быть dict или list
                                if isinstance(results_per_pair, dict):
                                    total_trades = sum(
                                        pair_data.get("trades", 0) 
                                        for pair_data in results_per_pair.values()
                                    )
                                elif isinstance(results_per_pair, list):
                                    total_trades = sum(
                                        pair_data.get("trades", 0) 
                                        for pair_data in results_per_pair
                                    )
                        
                        # Calculate wins/losses from trades or use summary
                        wins = strategy_data.get("wins", 0)
                        losses = strategy_data.get("losses", 0)
                        
                        # If wins/losses are 0, calculate from trades array
                        if wins == 0 and losses == 0 and total_trades > 0:
                            trades_array = strategy_data.get("trades", [])
                            if trades_array:
                                wins = sum(1 for t in trades_array if t.get("profit_ratio", 0) > 0)
                                losses = sum(1 for t in trades_array if t.get("profit_ratio", 0) <= 0)
                        
                        # Get profit metrics - try multiple sources
                        profit_total = strategy_data.get("profit_total", 0.0)
                        profit_total_pct = strategy_data.get("profit_total_pct", 0.0)
                        
                        # ВСЕГДА пересчитываем profit из trades array для точности
                        # (profit_total_pct в JSON может быть неточным или 0)
                        if total_trades > 0:
                            trades_array = strategy_data.get("trades", [])
                            if trades_array:
                                # profit_ratio уже в формате 0.01 = 1%, умножаем на 100
                                profit_total_pct = sum(t.get("profit_ratio", 0) * 100 for t in trades_array)
                                # Также проверяем profit_abs если profit_ratio = 0
                                if profit_total_pct == 0.0:
                                    total_profit_abs = sum(t.get("profit_abs", 0) for t in trades_array)
                                    if total_profit_abs != 0 and trades_array[0].get("open_rate"):
                                        # Рассчитываем процент от начальной ставки
                                        initial_stake = trades_array[0].get("stake_amount", 1000)
                                        if initial_stake > 0:
                                            profit_total_pct = (total_profit_abs / initial_stake) * 100
                        
                        # Also check results_per_pair
                        if profit_total_pct == 0.0:
                            results_per_pair = strategy_data.get("results_per_pair", {})
                            if results_per_pair:
                                # results_per_pair может быть dict или list
                                if isinstance(results_per_pair, dict):
                                    profit_total_pct = sum(
                                        pair_data.get("profit_total_pct", 0.0) 
                                        for pair_data in results_per_pair.values()
                                    )
                                elif isinstance(results_per_pair, list):
                                    profit_total_pct = sum(
                                        pair_data.get("profit_total_pct", 0.0) 
                                        for pair_data in results_per_pair
                                    )
                        
                        # Calculate win rate
                        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
                        
                        # Extract timeframe and timerange from strategy_data or config
                        timeframe = strategy_data.get("timeframe", "5m")
                        timerange = strategy_data.get("timerange", "")
                        
                        # Try to extract from backtest_start/backtest_end if timerange not found
                        if not timerange:
                            backtest_start = strategy_data.get("backtest_start")
                            backtest_end = strategy_data.get("backtest_end")
                            if backtest_start and backtest_end:
                                try:
                                    # Parse ISO format: "2025-10-08 00:00:00"
                                    start_dt = datetime.strptime(backtest_start.split()[0], "%Y-%m-%d")
                                    end_dt = datetime.strptime(backtest_end.split()[0], "%Y-%m-%d")
                                    timerange = f"{start_dt.strftime('%Y%m%d')}-{end_dt.strftime('%Y%m%d')}"
                                except:
                                    pass
                        
                        # Also try to extract from config file in ZIP
                        if not timerange:
                            try:
                                with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                                    config_files = [f for f in zip_ref.namelist() if 'config' in f and f.endswith('.json')]
                                    if config_files:
                                        config_data = json.loads(zip_ref.read(config_files[0]))
                                        if 'timerange' in config_data:
                                            timerange = config_data['timerange']
                            except:
                                pass
                        
                        # Calculate days from timerange (format: YYYYMMDD-YYYYMMDD)
                        days_tested = None
                        if timerange and len(timerange) == 17:
                            try:
                                start_date = datetime.strptime(timerange[:8], "%Y%m%d")
                                end_date = datetime.strptime(timerange[9:], "%Y%m%d")
                                days_tested = (end_date - start_date).days
                            except:
                                pass
                        
                        # Fallback: use backtest_days if available
                        if days_tested is None:
                            backtest_days = strategy_data.get("backtest_days")
                            if backtest_days:
                                days_tested = backtest_days
                        
                        metrics = {
                            "strategy_name": strategy_name,
                            "total_trades": total_trades,
                            "winning_trades": wins,
                            "losing_trades": losses,
                            "win_rate": win_rate,
                            "total_profit_pct": profit_total_pct,
                            "roi": profit_total_pct,
                            "max_drawdown": abs(strategy_data.get("max_drawdown", 0.0)),
                            "profit_factor": strategy_data.get("profit_factor", 0.0),
                            "sharpe_ratio": strategy_data.get("sharpe_ratio", 0.0),
                            "sortino_ratio": strategy_data.get("sortino_ratio", 0.0),
                            "calmar_ratio": strategy_data.get("calmar_ratio", 0.0),
                            "expectancy": strategy_data.get("expectancy", 0.0),
                            "cagr": strategy_data.get("cagr", 0.0),
                            "avg_profit": profit_total_pct / max(total_trades, 1),
                            "buys": total_trades,
                            "rejected_signals": strategy_data.get("rejected_signals", 0),
                            "leverage": 1,  # Default, can be extracted from config if needed
                            "timeframe": timeframe,
                            "timerange": timerange,
                            "days_tested": days_tested,
                        }
                        
                        return metrics
                    else:
                        # Fallback: try direct key (old format)
                        strategy_name = list(data.keys())[0] if data else None
                        if not strategy_name:
                            return None
                        strategy_data = data.get(strategy_name, {})
                        results = strategy_data.get("results", {})
                        
                        if not results:
                            return None
                        
                        metrics = {
                            "strategy_name": strategy_name,
                            "total_trades": results.get("total_trades", 0),
                            "winning_trades": results.get("wins", 0),
                            "losing_trades": results.get("losses", 0),
                            "win_rate": results.get("winrate", 0.0) * 100,
                            "total_profit_pct": results.get("profit_total_pct", 0.0),
                            "roi": results.get("profit_total_pct", 0.0),
                            "max_drawdown": abs(results.get("max_drawdown", 0.0)),
                            "profit_factor": results.get("profit_factor", 0.0),
                            "sharpe_ratio": results.get("sharpe_ratio", 0.0),
                            "sortino_ratio": results.get("sortino_ratio", 0.0),
                            "calmar_ratio": results.get("calmar_ratio", 0.0),
                            "expectancy": results.get("expectancy", 0.0),
                            "cagr": results.get("cagr", 0.0),
                            "avg_profit": results.get("profit_total_pct", 0.0) / max(results.get("total_trades", 1), 1),
                            "buys": results.get("total_trades", 0),
                            "rejected_signals": results.get("rejected_signals", 0),
                            "leverage": strategy_data.get("config", {}).get("leverage", 1),
                            "timeframe": "5m",  # Default
                            "timerange": "",
                            "days_tested": None,
                        }
                    
                    return metrics
                
        except Exception as e:
            print(f"⚠️  Ошибка при извлечении метрик из {zip_file.name}: {e}")
            import traceback
            traceback.print_exc()
            return None
        
        # Если ничего не найдено, возвращаем None
        return None
    
    def calculate_ninja_score(self, metrics: Dict, backtest_count: int) -> float:
        """Calculate Ninja Score using weighted metrics"""
        score = 0.0
        
        def normalize(value: float, min_val: float = 0, max_val: float = 100) -> float:
            if max_val == min_val:
                return 0
            return min(100, max(0, ((value - min_val) / (max_val - min_val)) * 100))
        
        # Calculate all components
        buys_score = normalize(metrics.get("buys", 0), 0, 1000)
        score += buys_score * NINJA_WEIGHTS["buys"]
        
        avgprof_score = normalize(metrics.get("avg_profit", 0), -5, 5)
        score += avgprof_score * NINJA_WEIGHTS["avgprof"]
        
        totprofp_score = normalize(metrics.get("total_profit_pct", 0), -50, 50)
        score += totprofp_score * NINJA_WEIGHTS["totprofp"]
        
        winp_score = normalize(metrics.get("win_rate", 0), 0, 100)
        score += winp_score * NINJA_WEIGHTS["winp"]
        
        ddp_score = normalize(metrics.get("max_drawdown", 0), 0, 50)
        score += (100 - ddp_score) * NINJA_WEIGHTS["ddp"]
        
        sharpe_score = normalize(metrics.get("sharpe_ratio", 0), -2, 5)
        score += sharpe_score * NINJA_WEIGHTS["sharpe"]
        
        sortino_score = normalize(metrics.get("sortino_ratio", 0), -2, 5)
        score += sortino_score * NINJA_WEIGHTS["sortino"]
        
        calmar_score = normalize(metrics.get("calmar_ratio", 0), -2, 5)
        score += calmar_score * NINJA_WEIGHTS["calmar"]
        
        expectancy_score = normalize(metrics.get("expectancy", 0), -1, 1)
        score += expectancy_score * NINJA_WEIGHTS["expectancy"]
        
        pf_score = normalize(metrics.get("profit_factor", 0), 0, 5)
        score += pf_score * NINJA_WEIGHTS["profit_factor"]
        
        cagr_score = normalize(metrics.get("cagr", 0), -50, 100)
        score += cagr_score * NINJA_WEIGHTS["cagr"]
        
        rejected_score = normalize(metrics.get("rejected_signals", 0), 0, 100)
        score += (100 - rejected_score) * NINJA_WEIGHTS["rejected_signals"]
        
        backtest_win_pct = (backtest_count / max(backtest_count, 1)) * 100 if backtest_count > 0 else 0
        score += backtest_win_pct * NINJA_WEIGHTS["backtest_win_percentage"]
        
        return score
    
    def process_all_backtests(self) -> Dict[str, List[Dict]]:
        """Process all backtest results and group by strategy"""
        strategies_metrics = {}
        
        print(f"📊 Обработка результатов бэктестов из {RESULTS_DIR}")
        
        zip_files = list(RESULTS_DIR.glob("*.zip"))
        print(f"   Найдено ZIP файлов: {len(zip_files)}")
        
        for zip_file in zip_files:
            metrics = self.extract_backtest_metrics(zip_file)
            if not metrics:
                print(f"   ⚠️  Не удалось извлечь метрики из {zip_file.name}")
                continue
            
            strategy_name = metrics["strategy_name"]
            timeframe = metrics.get("timeframe", "5m")
            timerange = metrics.get("timerange", "")
            
            # Создаем уникальный ключ для комбинации стратегия+таймфрейм+период
            # Это позволяет разделять стратегии по разным периодам тестирования
            if timerange:
                strategy_key = f"{strategy_name}_{timeframe}_{timerange}"
            else:
                strategy_key = f"{strategy_name}_{timeframe}"
            
            if strategy_key not in strategies_metrics:
                strategies_metrics[strategy_key] = []
            
            strategies_metrics[strategy_key].append(metrics)
        
        # Обрабатываем все стратегии с результатами (автообнаружение)
        # Фильтруем только стратегии с хотя бы одной сделкой
        filtered_metrics = {}
        all_strategies = get_all_strategies()
        
        for strategy, metrics_list in strategies_metrics.items():
            # Извлекаем имя стратегии из метрик (полное имя, не базовое)
            strategy_name_from_metrics = metrics_list[0].get("strategy_name", "") if metrics_list else ""
            
            # Проверяем, что стратегия существует в файловой системе
            # Проверяем как полное имя, так и базовое (на случай если стратегия называется по-другому)
            base_strategy = strategy.split("_")[0] if "_" in strategy else strategy
            
            # Улучшенная проверка существования стратегии
            strategy_exists = (
                strategy_name_from_metrics in all_strategies or
                base_strategy in all_strategies or
                (strategy_name_from_metrics.split("_")[0] in all_strategies if "_" in strategy_name_from_metrics else False) or
                any(s.startswith(base_strategy + "_") or s == base_strategy for s in all_strategies)  # Дополнительная проверка
            )
            
            if strategy_exists:
                # ВСЕГДА включаем стратегию если она существует в файловой системе
                # (даже с 0 сделок - это валидная информация для пользователя)
                filtered_metrics[strategy] = metrics_list
            else:
                # Логируем почему стратегия отфильтрована (с деталями для отладки)
                print(f"   ⚠️  Отфильтровано: {strategy}")
                print(f"      strategy_name_from_metrics: '{strategy_name_from_metrics}'")
                print(f"      base_strategy: '{base_strategy}'")
                print(f"      strategy_name_from_metrics in all_strategies: {strategy_name_from_metrics in all_strategies}")
                print(f"      base_strategy in all_strategies: {base_strategy in all_strategies}")
        
        print(f"✅ Обработано стратегий: {len(filtered_metrics)}")
        print(f"   (Отфильтровано неработающих: {len(strategies_metrics) - len(filtered_metrics)})")
        for strategy, metrics_list in filtered_metrics.items():
            # Извлекаем информацию о периоде тестирования
            timeframe = metrics_list[0].get("timeframe", "5m") if metrics_list else "5m"
            days_tested = metrics_list[0].get("days_tested") if metrics_list else None
            timerange = metrics_list[0].get("timerange", "") if metrics_list else ""
            
            days_info = f" ({days_tested} дней)" if days_tested else ""
            tf_info = f" [{timeframe}]" if timeframe else ""
            print(f"   - {strategy}{tf_info}{days_info}: {len(metrics_list)} бэктестов")
        
        return filtered_metrics
    
    def calculate_median_metrics(self, metrics_list: List[Dict]) -> Dict:
        """Calculate median values from list of metrics"""
        if not metrics_list:
            return {}
        
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
    
    def save_to_json(self, strategy_name: str, metrics_list: List[Dict]):
        """Save strategy rating to JSON file"""
        if not metrics_list:
            return
        
        # Extract base strategy name (without timeframe/timerange suffix)
        # strategy_name может быть в формате "StrategyName_timeframe_timerange"
        base_strategy_name = strategy_name.split("_")[0] if "_" in strategy_name else strategy_name
        
        # Calculate median metrics
        median_metrics = self.calculate_median_metrics(metrics_list)
        
        # Check for biases
        has_lookahead, lookahead_issues = self.check_lookahead_bias(base_strategy_name)
        strategy_hash = self.calculate_strategy_hash(base_strategy_name)
        
        # Calculate backtest win percentage
        profitable_backtests = sum(
            1 for m in metrics_list if m.get("total_profit_pct", 0) > 0
        )
        backtest_win_pct = (profitable_backtests / len(metrics_list)) * 100
        
        # Calculate Ninja Score
        combined_metrics = {
            **{k.replace("median_", ""): v for k, v in median_metrics.items()},
            "backtest_win_percentage": backtest_win_pct,
        }
        ninja_score = self.calculate_ninja_score(combined_metrics, len(metrics_list))
        
        # Get leverage
        leverage = metrics_list[0].get("leverage", 1) if metrics_list else 1
        
        # Extract timeframe, timerange, days_tested from the first metric in the list
        timeframe = metrics_list[0].get("timeframe", "5m") if metrics_list else "5m"
        timerange = metrics_list[0].get("timerange", "") if metrics_list else ""
        days_tested = metrics_list[0].get("days_tested") if metrics_list else None
        
        # Если timerange не найден в метриках, попробуем извлечь из strategy_name
        if not timerange and "_" in strategy_name:
            # Формат: StrategyName_timeframe_YYYYMMDD-YYYYMMDD
            parts = strategy_name.split("_")
            if len(parts) >= 3:
                # Последняя часть может быть timerange
                last_part = parts[-1]
                if len(last_part) == 17 and "-" in last_part:
                    timerange = last_part
        
        # Format timerange for display
        timerange_display = ""
        if timerange and len(timerange) == 17:
            try:
                start_date = datetime.strptime(timerange[:8], "%Y%m%d")
                end_date = datetime.strptime(timerange[9:], "%Y%m%d")
                timerange_display = f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}"
            except:
                timerange_display = timerange
        
        # Check if strategy should be stalled
        is_stalled = False
        stall_reason = None
        
        avg_profit = statistics.mean([m.get("total_profit_pct", 0) for m in metrics_list])
        if avg_profit < -0.30 and all(m.get("total_profit_pct", 0) < 0 for m in metrics_list):
            is_stalled = True
            stall_reason = "negative"
        
        negative_count = sum(1 for m in metrics_list if m.get("total_profit_pct", 0) < 0)
        if len(metrics_list) >= 12 and (negative_count / len(metrics_list)) >= 0.90:
            is_stalled = True
            stall_reason = "90_percent_negative"
        
        if has_lookahead:
            is_stalled = True
            stall_reason = "biased"
        
        # Не помечаем как stalled если это просто стратегия без сделок
        # (может быть валидная стратегия, просто не нашла входов)
        if all(m.get("total_trades", 0) == 0 for m in metrics_list):
            # Проверяем, есть ли хотя бы один валидный бэктест
            has_valid_backtest = any(
                m.get("strategy_name") and 
                m.get("timeframe") and
                m.get("timerange")
                for m in metrics_list
            )
            if not has_valid_backtest:
                is_stalled = True
                stall_reason = "no_trades"
        
        # Create rating object
        rating = {
            "strategy_name": base_strategy_name,  # Используем базовое имя стратегии
            "strategy_key": strategy_name,  # Полный ключ с timeframe/timerange
            "exchange": "gateio",
            "stake_currency": "USDT",
            "timeframe": timeframe,
            "timerange": timerange,
            "timerange_display": timerange_display,
            "days_tested": days_tested,
            "total_backtests": len(metrics_list),
            "updated_at": datetime.now().isoformat(),
            **{k: float(v) for k, v in median_metrics.items()},
            "backtest_win_percentage": backtest_win_pct,
            "ninja_score": ninja_score,
            "has_lookahead_bias": has_lookahead,
            "lookahead_issues": lookahead_issues,
            "has_tight_trailing_stop": False,  # Simplified
            "leverage": leverage,
            "strategy_hash": strategy_hash,
            "is_stalled": is_stalled,
            "stall_reason": stall_reason,
            "is_active": not is_stalled,
            "all_backtests": metrics_list  # Store all individual backtests
        }
        
        # Save to JSON
        rating_file = RATINGS_DIR / f"{strategy_name}_rating.json"
        rating_file.write_text(json.dumps(rating, indent=2, ensure_ascii=False), encoding='utf-8')
        
        print(f"✅ Сохранен рейтинг для {strategy_name} (Score: {ninja_score:.2f})")
        return rating
    
    def run(self):
        """Main execution method - processes all backtests and saves to JSON"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info("=" * 70)
        logger.info("🎯 Strategy Rating System - Standalone (JSON)")
        logger.info("=" * 70)
        
        strategies_metrics = self.process_all_backtests()
        
        if not strategies_metrics:
            logger.warning("❌ Нет результатов для обработки")
            return 0
        
        # Save to JSON
        logger.info("💾 Сохранение в JSON файлы...")
        all_ratings = {}
        for strategy_name, metrics_list in strategies_metrics.items():
            try:
                rating = self.save_to_json(strategy_name, metrics_list)
                if rating:
                    all_ratings[strategy_name] = rating
                    logger.info(f"✅ Сохранен рейтинг для {strategy_name}")
            except Exception as e:
                logger.error(f"❌ Ошибка для {strategy_name}: {e}", exc_info=True)
        
        # Save combined rankings file
        rankings_file = RATINGS_DIR / "rankings.json"
        rankings_data = {
            "updated_at": datetime.now().isoformat(),
            "total_strategies": len(all_ratings),
            "rankings": sorted(
                all_ratings.values(),
                key=lambda x: x.get("ninja_score", 0),
                reverse=True
            )
        }
        
        # Ensure directory exists
        RATINGS_DIR.mkdir(parents=True, exist_ok=True)
        
        rankings_file.write_text(
            json.dumps(rankings_data, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        
        logger.info("=" * 70)
        logger.info(f"✅ Рейтинг стратегий сохранен! ({len(all_ratings)} стратегий)")
        logger.info(f"📁 Файлы в: {RATINGS_DIR}")
        logger.info(f"📊 Общий рейтинг: {rankings_file}")
        logger.info("=" * 70)
        
        return len(all_ratings)  # Return count for verification


def main():
    """Main entry point"""
    system = StrategyRatingSystemStandalone()
    system.run()


if __name__ == "__main__":
    main()

