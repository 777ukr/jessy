"""
Ninja Score Calculator for Jesse
Adapted from FreqTrade strategy_rating_system_standalone.py

Calculates weighted strategy rating based on 13 metrics
Categories: Excellent (≥500), Good (≥200), Satisfactory (≥0), Poor (<0)
"""

from typing import Dict
import math

# Ninja Score weights (exact from ninja.trade)
NINJA_WEIGHTS = {
    "total_trades": 9,           # buys
    "avg_profit_pct": 26,        # avgprof
    "total_profit_pct": 26,      # totprofp
    "win_rate": 24,              # winp
    "max_drawdown_pct": -25,     # ddp (negative weight)
    "sharpe_ratio": 7,           # sharpe
    "sortino_ratio": 7,          # sortino
    "calmar_ratio": 7,           # calmar
    "expectancy": 8,             # expectancy
    "profit_factor": 9,          # profit_factor
    "cagr": 10,                 # cagr
    "max_consecutive_losses": -25,  # rejected_signals (negative weight)
    "backtest_win_percentage": 10  # backtest_win_percentage
}


def calculate_ninja_score(metrics: Dict) -> Dict:
    """
    Calculate Ninja Score for a strategy based on metrics
    
    Args:
        metrics: Dictionary with strategy metrics from backtest session
        
    Returns:
        Dictionary with:
            - ninja_score: Calculated score
            - category: "Excellent", "Good", "Satisfactory", or "Poor"
            - breakdown: Individual metric contributions
    """
    if not metrics:
        return {
            "ninja_score": 0,
            "category": "Poor",
            "breakdown": {}
        }
    
    # Extract metrics with defaults
    total_trades = metrics.get("total_trades", 0)
    total_profit_pct = metrics.get("total_net_profit_percentage", 0.0)
    win_rate = metrics.get("win_rate", 0.0)
    max_drawdown_pct = abs(metrics.get("max_drawdown_percentage", 0.0))
    sharpe_ratio = metrics.get("sharpe_ratio", 0.0)
    sortino_ratio = metrics.get("sortino_ratio", 0.0)
    calmar_ratio = metrics.get("calmar_ratio", 0.0)
    expectancy = metrics.get("expectancy", 0.0)
    profit_factor = metrics.get("profit_factor", 0.0)
    cagr = metrics.get("cagr", 0.0)
    
    # Calculate average profit per trade
    avg_profit_pct = total_profit_pct / max(total_trades, 1)
    
    # Max consecutive losses (approximate from win rate and total trades)
    max_consecutive_losses = 0
    if total_trades > 0 and win_rate < 100:
        losing_trades = total_trades * (1 - win_rate / 100)
        if losing_trades > 0:
            # Estimate max consecutive losses
            max_consecutive_losses = int(math.log(total_trades) * (1 - win_rate / 100) * 2)
    
    # Backtest win percentage (same as win_rate for Jesse)
    backtest_win_percentage = win_rate
    
    # Calculate individual contributions
    breakdown = {}
    score = 0.0
    
    # Total trades contribution
    trades_score = min(total_trades / 10.0, 1.0) * NINJA_WEIGHTS["total_trades"]
    breakdown["total_trades"] = trades_score
    score += trades_score
    
    # Average profit contribution
    avg_prof_score = min(avg_profit_pct / 5.0, 1.0) * NINJA_WEIGHTS["avg_profit_pct"]
    breakdown["avg_profit_pct"] = avg_prof_score
    score += avg_prof_score
    
    # Total profit contribution
    tot_prof_score = min(total_profit_pct / 50.0, 1.0) * NINJA_WEIGHTS["total_profit_pct"]
    breakdown["total_profit_pct"] = tot_prof_score
    score += tot_prof_score
    
    # Win rate contribution
    win_rate_score = (win_rate / 100.0) * NINJA_WEIGHTS["win_rate"]
    breakdown["win_rate"] = win_rate_score
    score += win_rate_score
    
    # Max drawdown contribution (negative)
    dd_score = -min(max_drawdown_pct / 50.0, 1.0) * abs(NINJA_WEIGHTS["max_drawdown_pct"])
    breakdown["max_drawdown_pct"] = dd_score
    score += dd_score
    
    # Sharpe ratio contribution
    sharpe_score = min(sharpe_ratio / 3.0, 1.0) * NINJA_WEIGHTS["sharpe_ratio"]
    breakdown["sharpe_ratio"] = sharpe_score
    score += sharpe_score
    
    # Sortino ratio contribution
    sortino_score = min(sortino_ratio / 3.0, 1.0) * NINJA_WEIGHTS["sortino_ratio"]
    breakdown["sortino_ratio"] = sortino_score
    score += sortino_score
    
    # Calmar ratio contribution
    calmar_score = min(calmar_ratio / 3.0, 1.0) * NINJA_WEIGHTS["calmar_ratio"]
    breakdown["calmar_ratio"] = calmar_score
    score += calmar_score
    
    # Expectancy contribution
    expectancy_score = min(expectancy / 0.1, 1.0) * NINJA_WEIGHTS["expectancy"]
    breakdown["expectancy"] = expectancy_score
    score += expectancy_score
    
    # Profit factor contribution
    pf_score = min(profit_factor / 2.0, 1.0) * NINJA_WEIGHTS["profit_factor"]
    breakdown["profit_factor"] = pf_score
    score += pf_score
    
    # CAGR contribution
    cagr_score = min(cagr / 100.0, 1.0) * NINJA_WEIGHTS["cagr"]
    breakdown["cagr"] = cagr_score
    score += cagr_score
    
    # Max consecutive losses contribution (negative)
    losses_score = -min(max_consecutive_losses / 10.0, 1.0) * abs(NINJA_WEIGHTS["max_consecutive_losses"])
    breakdown["max_consecutive_losses"] = losses_score
    score += losses_score
    
    # Backtest win percentage contribution
    bwp_score = (backtest_win_percentage / 100.0) * NINJA_WEIGHTS["backtest_win_percentage"]
    breakdown["backtest_win_percentage"] = bwp_score
    score += bwp_score
    
    # Determine category
    if score >= 500:
        category = "Excellent"
    elif score >= 200:
        category = "Good"
    elif score >= 0:
        category = "Satisfactory"
    else:
        category = "Poor"
    
    return {
        "ninja_score": round(score, 2),
        "category": category,
        "breakdown": breakdown
    }


def get_ninja_score_color(score: float) -> str:
    """
    Get color for Ninja Score visualization
    
    Args:
        score: Ninja Score value
        
    Returns:
        Color hex code
    """
    if score >= 500:
        return "#10b981"  # Green (Excellent)
    elif score >= 200:
        return "#3b82f6"  # Blue (Good)
    elif score >= 0:
        return "#f59e0b"  # Gold (Satisfactory)
    else:
        return "#ef4444"  # Red (Poor)

