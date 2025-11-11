#!/usr/bin/env python3
"""
Mass backtest runner for all strategies
Runs backtests for all strategies on specified timeframes
"""
import sys
import os
import time
import requests
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jesse-master'))

BASE_URL = "http://localhost:9001"
PASSWORD = "test_password_123"

def get_auth_token():
    """Get authentication token"""
    response = requests.post(
        f"{BASE_URL}/auth",
        json={"password": PASSWORD},
        headers={"Content-Type": "application/json"},
        timeout=10
    )
    if response.status_code == 200:
        return response.json().get("auth_token")
    else:
        print(f"❌ Auth error: {response.status_code}")
        return None

def get_all_strategies():
    """Get all available strategies (exclude test strategies)"""
    strategies_dir = "jesse-master/strategies"
    strategies = []
    exclude_prefixes = ["Test", "test_"]
    
    if os.path.exists(strategies_dir):
        for item in os.listdir(strategies_dir):
            # Skip test strategies
            if any(item.startswith(prefix) for prefix in exclude_prefixes):
                continue
                
            strategy_path = os.path.join(strategies_dir, item, "__init__.py")
            if os.path.exists(strategy_path):
                strategies.append(item)
    
    return sorted(strategies)

def run_backtest(token, strategy_name, start_date, finish_date, timeframe="5m", exchange="Gate USDT Perpetual"):
    """Run a single backtest"""
    import uuid
    
    session_id = str(uuid.uuid4())
    
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
    
    try:
        response = requests.post(
            f"{BASE_URL}/backtest",
            json=backtest_request,
            headers={
                "Content-Type": "application/json",
                "Authorization": token
            },
            timeout=10
        )
        
        if response.status_code == 202:
            return session_id
        else:
            print(f"   ❌ Error {response.status_code}: {response.text[:100]}")
            return None
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        return None

def check_backtest_status(token, session_id):
    """Check if backtest is finished"""
    try:
        response = requests.get(
            f"{BASE_URL}/backtest-sessions/{session_id}",
            headers={"Authorization": token},
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("status", "unknown")
    except:
        pass
    return "unknown"

def main():
    print("🚀 Mass Backtest Runner")
    print("=" * 60)
    
    # Get token
    print("🔐 Authenticating...")
    token = get_auth_token()
    if not token:
        print("❌ Failed to authenticate")
        sys.exit(1)
    print("✅ Authenticated")
    print()
    
    # Get all strategies
    print("📋 Finding strategies...")
    strategies = get_all_strategies()
    if not strategies:
        print("❌ No strategies found")
        sys.exit(1)
    
    print(f"✅ Found {len(strategies)} strategies:")
    for s in strategies:
        print(f"   - {s}")
    print()
    
    # Configuration
    start_date = "2025-01-01"
    finish_date = "2025-11-01"
    timeframes = ["5m", "1m"]
    exchange = "Gate USDT Perpetual"
    
    print(f"📊 Configuration:")
    print(f"   Period: {start_date} to {finish_date}")
    print(f"   Exchange: {exchange}")
    print(f"   Symbol: BTC-USDT")
    print(f"   Timeframes: {', '.join(timeframes)}")
    print()
    
    # Run backtests
    total = len(strategies) * len(timeframes)
    current = 0
    running_sessions = []
    
    print(f"🔄 Starting {total} backtests...")
    print()
    
    for strategy in strategies:
        for timeframe in timeframes:
            current += 1
            print(f"[{current}/{total}] {strategy} @ {timeframe}...", end=" ", flush=True)
            
            session_id = run_backtest(token, strategy, start_date, finish_date, timeframe, exchange)
            
            if session_id:
                running_sessions.append((strategy, timeframe, session_id))
                print(f"✅ Started (ID: {session_id[:8]}...)")
            else:
                print("❌ Failed")
            
            # Small delay to avoid overwhelming the server
            time.sleep(0.5)
    
    print()
    print(f"✅ Started {len(running_sessions)} backtests")
    print()
    print("💡 Monitor progress at: http://localhost:9001")
    print("💡 View rating at: http://localhost:9001/rating")
    print()
    print("⏳ Backtests are running in background...")

if __name__ == "__main__":
    main()

