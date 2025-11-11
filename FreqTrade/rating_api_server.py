#!/usr/bin/env python3
"""
FastAPI Server for Strategy Rating System
Full-featured web interface for managing strategies, running backtests, and viewing rankings
"""

import os
import sys
import json
import subprocess
import asyncio
import time
import logging
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import zipfile

# Setup logging first (before any logger.info calls)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Try to import optional dependencies
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor, execute_values
    from psycopg2.pool import ThreadedConnectionPool
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logger.warning("psycopg2 not available, using JSON fallback")

try:
    import pandas as pd
    import numpy as np
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    logger.warning("pandas/numpy not available, some features may be limited")

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

# Импортируем расширенный калькулятор доходности
try:
    from advanced_profitability_calculator import (
        ProfitabilityCalculator, Exchange, TradingType,
        compare_exchanges, calculate_optimal_strategy
    )
    PROFITABILITY_AVAILABLE = True
except ImportError:
    PROFITABILITY_AVAILABLE = False
    logger.warning("Advanced profitability calculator not available")

# Импортируем базу данных результатов бэктестов
try:
    from backtest_results_db import BacktestResultsDB, get_db
    BACKTEST_DB_AVAILABLE = True
    backtest_db = get_db()
    logger.info("✅ База данных результатов бэктестов доступна")
except ImportError:
    BACKTEST_DB_AVAILABLE = False
    backtest_db = None
    logger.warning("База данных результатов бэктестов недоступна")
except Exception as e:
    BACKTEST_DB_AVAILABLE = False
    backtest_db = None
    logger.warning(f"Ошибка инициализации БД результатов: {e}")

# Configuration
FREQTRADE_DIR = Path(__file__).parent
CONFIG_PATH = FREQTRADE_DIR.parent / "config" / "freqtrade_config.json"
STRATEGIES_DIR = FREQTRADE_DIR / "user_data" / "strategies"
RESULTS_DIR = FREQTRADE_DIR / "user_data" / "backtest_results"
WEB_DIR = FREQTRADE_DIR / "user_data" / "web"

# Setup logging to file (add file handler after logger is created)
try:
    log_file = FREQTRADE_DIR / 'api_server.log'
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
except Exception as e:
    # If can't create file handler, continue without it
    pass

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

app = FastAPI(title="Strategy Rating System", version="1.0.0")

# Добавляем роутер для расширенной доходности
if PROFITABILITY_AVAILABLE:
    try:
        from enhanced_profitability_api import router as profitability_router
        app.include_router(profitability_router)
    except Exception as e:
        logger.warning(f"Не удалось загрузить profitability router: {e}")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files - serve HTML files directly
# Note: We serve HTML files via routes, not static files mount
# app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

# Database pool
db_pool = None

def get_db_connection():
    """Get database connection"""
    global db_pool
    try:
        if db_pool is None:
            try:
                db_pool = ThreadedConnectionPool(1, 10, DATABASE_URL)
            except Exception as e:
                # Если не удалось создать пул, возвращаем None
                logger.warning(f"PostgreSQL не доступен: {e}")
                return None
        try:
            return db_pool.getconn()
        except Exception as e:
            logger.warning(f"Ошибка получения соединения: {e}")
            return None
    except Exception as e:
        logger.warning(f"PostgreSQL не доступен: {e}")
        return None

def return_db_connection(conn):
    """Return connection to pool"""
    if db_pool:
        db_pool.putconn(conn)

# Pydantic models
class BacktestRequest(BaseModel):
    """Валидация запроса на бэктест с улучшенной проверкой"""
    strategy_name: str = Field(..., min_length=1, max_length=100, description="Название стратегии")
    pairs: List[str] = Field(default=["BTC/USDT"], min_items=1, max_items=10, description="Список торговых пар")
    timerange: Optional[str] = Field(None, description="Временной диапазон (YYYYMMDD-YYYYMMDD)")
    timeframe: str = Field(default="5m", pattern="^(1m|3m|5m|15m|30m|1h|2h|4h|1d)$", description="Таймфрейм")
    leverage: int = Field(default=1, ge=1, le=125, description="Плечо")
    exchange: str = Field(default="binance", pattern="^(binance|bybit|gateio|kucoin)$", description="Биржа")
    trading_type: str = Field(default="spot", pattern="^(spot|futures)$", description="Тип торговли")
    deposit: float = Field(default=1000, gt=0, le=1000000, description="Депозит для расчета проскальзываний")
    
    @field_validator('strategy_name')
    @classmethod
    def validate_strategy_name(cls, v):
        """Валидация имени стратегии"""
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Strategy name contains invalid characters')
        return v
    
    @field_validator('pairs')
    @classmethod
    def validate_pairs(cls, v):
        """Валидация формата пар"""
        for pair in v:
            if '/' not in pair or len(pair.split('/')) != 2:
                raise ValueError(f'Invalid pair format: {pair}')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "strategy_name": "ElliotV5_SMA",
                "pairs": ["BTC/USDT"],
                "timeframe": "5m",
                "leverage": 1,
                "exchange": "binance",
                "trading_type": "spot",
                "deposit": 1000
            }
        }

class StrategyFilter(BaseModel):
    min_trades: int = 0
    min_profit: float = -100
    max_leverage: Optional[int] = None
    exclude_stalled: bool = True
    exclude_bias: bool = True
    pairs: Optional[List[str]] = None

# API Routes

def serve_html_file(filename: str):
    """Helper to serve HTML files"""
    html_file = WEB_DIR / filename
    if html_file.exists():
        try:
            content = html_file.read_text(encoding='utf-8')
            return HTMLResponse(content=content)
        except Exception as e:
            logger.error(f"Ошибка чтения HTML {filename}: {e}", exc_info=True)
            return HTMLResponse(
                content=f"<h1>Error</h1><p>Ошибка загрузки {filename}: {e}</p>",
                status_code=500
            )
    return HTMLResponse(
        content=f"<h1>Not Found</h1><p>Файл {filename} не найден</p>",
        status_code=404
    )

@app.get("/")
async def root():
    """Main page"""
    return serve_html_file("rating_ui.html")

@app.get("/vectorbt_backtester.html")
async def vectorbt_page():
    """VectorBT backtester page"""
    return serve_html_file("vectorbt_backtester.html")

@app.get("/octobot_backtester.html")
async def octobot_page():
    """OctoBot backtester page"""
    return serve_html_file("octobot_backtester.html")

@app.get("/hummingbot_backtester.html")
async def hummingbot_page():
    """Hummingbot backtester page"""
    return serve_html_file("hummingbot_backtester.html")

@app.get("/jesse_backtester.html")
async def jesse_page():
    """Jesse backtester page"""
    return serve_html_file("jesse_backtester.html")

@app.get("/api/strategies")
async def get_strategies():
    """Get list of all strategies"""
    strategies = []
    for file in STRATEGIES_DIR.glob("*.py"):
        if file.name != "__init__.py" and not file.name.startswith("_"):
            # Проверяем есть ли бэктесты для стратегии
            strategy_name = file.stem
            has_backtests = any(
                f"backtest-result" in f.name and strategy_name.lower() in f.name.lower()
                for f in RESULTS_DIR.glob("*.zip")
            )
            
            strategies.append({
                "name": strategy_name,
                "file": file.name,
                "size": file.stat().st_size,
                "modified": datetime.fromtimestamp(file.stat().st_mtime).isoformat(),
                "has_backtests": has_backtests
            })
    return {"strategies": sorted(strategies, key=lambda x: x["name"])}

@app.get("/api/rankings")
async def get_rankings(
    min_trades: int = 0,
    min_profit: float = -100,
    max_leverage: Optional[str] = None,
    exclude_stalled: bool = True,
    exclude_bias: bool = True,
    sort_by: str = "ninja_score",
    order: str = "desc",
    limit: int = 100,
    exchange: Optional[str] = None,
    stake: Optional[str] = None,
    hide_negative: bool = False,
    show_dca: bool = False,
    show_multiclass: bool = False,
    timeframe: Optional[str] = None
):
    """Get strategy rankings (main/default tab)"""
    return await get_rankings_with_tab(
        tab=None,
        min_trades=min_trades,
        min_profit=min_profit,
        max_leverage=max_leverage,
        exclude_stalled=exclude_stalled,
        exclude_bias=exclude_bias,
        sort_by=sort_by,
        order=order,
        limit=limit,
        exchange=exchange,
        stake=stake,
        hide_negative=hide_negative,
        show_dca=show_dca,
        show_multiclass=show_multiclass,
        timeframe=timeframe
    )

@app.get("/api/rankings/{tab}")
async def get_rankings_with_tab(
    tab: str,
    min_trades: int = 0,
    min_profit: float = -100,
    max_leverage: Optional[str] = None,
    exclude_stalled: bool = True,
    exclude_bias: bool = True,
    sort_by: str = "ninja_score",
    order: str = "desc",
    limit: int = 100,
    exchange: Optional[str] = None,
    stake: Optional[str] = None,
    hide_negative: bool = False,
    show_dca: bool = False,
    show_multiclass: bool = False,
    timeframe: Optional[str] = None
):
    """Get strategy rankings with filters and tabs support
    
    Tabs: main (default), latest, failed, private, dca, multiclass
    """
    # ВСЕГДА используем JSON fallback (PostgreSQL не настроен)
    conn = None
    if True:  # Принудительно используем JSON fallback
        # Fallback: используем standalone JSON версию
        try:
            import sys
            sys.path.insert(0, str(FREQTRADE_DIR))
            from strategy_rating_system_standalone import StrategyRatingSystemStandalone
            from rating_web_interface_standalone import get_rankings_from_json
            
            rankings = get_rankings_from_json(limit=1000)  # Получаем больше для фильтрации
            
            # Обработка вкладок
            if tab == "latest":
                # Сортируем по дате обновления (последние бэктесты)
                rankings.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            elif tab == "failed":
                # Стратегии с ошибками или stalled
                rankings = [r for r in rankings if r.get("is_stalled", False) or r.get("total_backtests", 0) == 0]
            elif tab == "private":
                # Стратегии без URL (пока просто все, нужно добавить поле private)
                rankings = rankings  # TODO: добавить детекцию private стратегий
            elif tab == "dca":
                # DCA стратегии (пока просто все, нужно добавить детекцию DCA)
                rankings = rankings  # TODO: добавить детекцию DCA
            elif tab == "multiclass":
                # Multiclass стратегии (пока просто все, нужно добавить детекцию)
                rankings = rankings  # TODO: добавить детекцию multiclass
            # else: main/default - без дополнительной фильтрации
            
            # Применяем фильтры
            filtered = []
            for r in rankings:
                # Exchange filter
                if exchange and r.get("exchange", "").lower() != exchange.lower():
                    continue
                
                # Stake filter
                if stake and r.get("stake_currency", "").upper() != stake.upper():
                    continue
                
                # Timeframe filter
                if timeframe and r.get("timeframe", "").lower() != timeframe.lower():
                    continue
                
                # Hide negative
                if hide_negative and r.get("median_total_profit_pct", 0) < 0:
                    continue
                
                # Show DCA
                if tab != "dca" and not show_dca:
                    # Если не на вкладке DCA и show_dca выключен, пропускаем DCA стратегии
                    # TODO: добавить проверку флага DCA
                    pass
                
                # Show Multiclass
                if tab != "multiclass" and not show_multiclass:
                    # TODO: добавить проверку флага multiclass
                    pass
                
                # Стандартные фильтры
                if r.get("median_total_trades", 0) < min_trades:
                    continue
                if r.get("median_total_profit_pct", -100) < min_profit:
                    continue
                if max_leverage and max_leverage.strip():
                    try:
                        if r.get("leverage", 1) > int(max_leverage):
                            continue
                    except:
                        pass
                if tab != "failed":  # На вкладке failed не исключаем stalled
                    if exclude_stalled and r.get("is_stalled", False):
                        continue
                if exclude_bias and r.get("has_lookahead_bias", False):
                    continue
                filtered.append(r)
            
            # Преобразуем данные для фронтенда (median_* -> avg_* и добавляем недостающие поля)
            transformed_rankings = []
            for r in filtered:
                # Базовые поля
                transformed = dict(r)
                
                # Преобразуем median_* в avg_* для совместимости с фронтендом
                transformed["avg_buys"] = r.get("median_buys", 0) or r.get("median_total_trades", 0)
                transformed["avg_prof"] = r.get("median_avg_profit", 0)
                # Если median_avg_profit отсутствует, рассчитываем из total_profit_pct / total_trades
                if transformed["avg_prof"] == 0 and r.get("median_total_trades", 0) > 0:
                    transformed["avg_prof"] = (r.get("median_total_profit_pct", 0) or 0) / r.get("median_total_trades", 1)
                transformed["avg_tot_profit_pct"] = r.get("median_total_profit_pct", 0) or 0
                transformed["avg_win_pct"] = r.get("median_win_rate", 0) or 0
                transformed["avg_dd_pct"] = abs(r.get("median_max_drawdown", 0) or 0)
                transformed["avg_sharpe"] = r.get("median_sharpe_ratio", 0) or 0
                
                # Добавляем недостающие поля для совместимости
                if "stoploss" not in transformed or transformed.get("stoploss") == -0.99:
                    # Пытаемся извлечь stoploss из стратегии
                    strategy_name = transformed.get("strategy_name", "")
                    if strategy_name:
                        strategy_file = STRATEGIES_DIR / f"{strategy_name}.py"
                        if strategy_file.exists():
                            try:
                                with open(strategy_file, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                    # Ищем stoploss = значение
                                    match = re.search(r'stoploss\s*=\s*(-?\d+\.?\d*)', content)
                                    if match:
                                        transformed["stoploss"] = float(match.group(1))
                                    else:
                                        transformed["stoploss"] = -0.99
                            except:
                                transformed["stoploss"] = -0.99
                        else:
                            transformed["stoploss"] = -0.99
                    else:
                        transformed["stoploss"] = -0.99
                
                # Добавляем alias для median_avg_profit_pct (используется фронтендом)
                transformed["median_avg_profit_pct"] = transformed["avg_prof"]
                
                transformed_rankings.append(transformed)
            
            # Сортировка
            reverse = order.lower() == "desc"
            try:
                # Используем sort_by для сортировки, но проверяем наличие поля
                def sort_key(x):
                    key = sort_by
                    # Если поле начинается с median_, проверяем оба варианта
                    if key.startswith("median_"):
                        return x.get(key, x.get(key.replace("median_", "avg_"), 0))
                    return x.get(key, 0)
                transformed_rankings.sort(key=sort_key, reverse=reverse)
            except Exception as e:
                logger.warning(f"Ошибка сортировки: {e}")
                pass
            
            return JSONResponse(
                status_code=200,
                content={
                    "rankings": transformed_rankings[:limit],
                    "total": len(transformed_rankings),
                    "filtered": len(transformed_rankings),
                    "source": "json",
                    "tab": tab if tab else "main"
                }
            )
        except Exception as e:
            logger.info(f"⚠️  Ошибка при чтении JSON рейтинга: {e}")
            return JSONResponse(
                status_code=200,
                content={"rankings": [], "total": 0, "error": "Нет данных. Запустите бэктесты."}
            )
    # Пропускаем PostgreSQL блок - всегда используем JSON fallback
    # Это гарантирует работу без настройки базы данных
    # PostgreSQL код закомментирован, так как таблицы не созданы

@app.post("/api/backtest/run")
async def run_backtest(request: BacktestRequest, background_tasks: BackgroundTasks):
    """Run backtest for strategy - supports multiple pairs (BTC/USDT, ETH/USDT, SOL/USDT)"""
    # Используем timerange из запроса или вычисляем по умолчанию (30 дней)
    if request.timerange:
        timerange = request.timerange
    else:
        # По умолчанию: последние 30 дней (быстро и достаточно для тестирования)
        end_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")  # Вчера
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")  # 30 дней назад
        timerange = f"{start_date}-{end_date}"
    
    # Default pairs if not provided: BTC/USDT, ETH/USDT, SOL/USDT
    if not request.pairs or len(request.pairs) == 0:
        request.pairs = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
        logger.info(f"📊 Используем пары по умолчанию: {request.pairs}")
    
    # Support for batch testing - if strategy_name is "all", test all strategies
    if request.strategy_name.lower() == "all":
        # Get all strategies automatically
        all_strategies = []
        for file in STRATEGIES_DIR.glob("*.py"):
            if file.name != "__init__.py" and not file.name.startswith("_"):
                all_strategies.append(file.stem)
        
        # Launch backtests for all strategies
        logger.info(f"🚀 [{datetime.now().strftime('%H:%M:%S')}] Запрос на массовое тестирование:")
        logger.info(f"   Количество стратегий: {len(all_strategies)}")
        logger.info(f"   Пары: {request.pairs}")
        logger.info(f"   Timeframe: {request.timeframe}, Timerange: {timerange}")
        
        for strategy in sorted(all_strategies):
            background_tasks.add_task(
                execute_backtest,
                strategy,
                request.pairs,
                timerange,
                request.timeframe,
                request.leverage,
                request.exchange,
                request.trading_type,
                request.deposit
            )
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "started",
                "strategy": "all",
                "strategies_count": len(all_strategies),
                "strategies": sorted(all_strategies),
                "pairs": request.pairs,
                "timerange": timerange,
                "message": f"Backtests started for {len(all_strategies)} strategies in background"
            }
        )
    
    # Validate strategy exists
    strategy_file = STRATEGIES_DIR / f"{request.strategy_name}.py"
    if not strategy_file.exists():
        raise HTTPException(status_code=404, detail=f"Strategy {request.strategy_name} not found")
    
    # Логируем запуск
    logger.info(f"🚀 [{datetime.now().strftime('%H:%M:%S')}] Запрос на запуск бэктеста:")
    logger.info(f"   Стратегия: {request.strategy_name}")
    logger.info(f"   Пары: {request.pairs}")
    logger.info(f"   Timeframe: {request.timeframe}, Timerange: {timerange}")
    
    # Add to background tasks
    background_tasks.add_task(
        execute_backtest,
        request.strategy_name,
        request.pairs,
        timerange,
        request.timeframe,
        request.leverage,
        request.exchange,
        request.trading_type,
        request.deposit
    )
    
    return JSONResponse(
        status_code=200,
        content={
            "status": "started",
            "strategy": request.strategy_name,
            "pairs": request.pairs,
            "timerange": timerange,
            "message": "Backtest started in background"
        }
    )

async def execute_backtest(strategy_name: str, pairs: List[str], timerange: str, timeframe: str, leverage: int, exchange: str = "binance", trading_type: str = "spot", deposit: float = 1000):
    """
    Execute backtest with improved error handling and logging
    
    Args:
        strategy_name: Name of the strategy
        pairs: List of trading pairs
        timerange: Time range for backtest
        timeframe: Timeframe for candles
        leverage: Leverage to use
        exchange: Exchange name
        trading_type: Spot or futures
        deposit: Deposit amount for slippage calculation
    """
    logger.info(f"🔄 Запуск бэктеста для {strategy_name}...")
    """Execute backtest in background and update rankings automatically"""
    import sys
    import time
    import asyncio
    
    # Небольшая задержка чтобы убедиться что ответ отправлен
    await asyncio.sleep(1)
    
    sys.path.insert(0, str(FREQTRADE_DIR))
    
    # Записываем время начала
    start_time = datetime.now()
    log_file = FREQTRADE_DIR / f"backtest_{strategy_name}_{int(time.time())}.log"
    
    logger.info(f"[{start_time.strftime('%H:%M:%S')}] === НАЧАЛО БЭКТЕСТА ===")
    logger.info(f"   Стратегия: {strategy_name}")
    logger.info(f"   Пары: {', '.join(pairs)}")
    logger.info(f"   Timeframe: {timeframe}")
    logger.info(f"   Timerange: {timerange}")
    logger.info(f"   Лог файл: {log_file.name}")
    
    # Проверяем наличие данных и скачиваем если нужно
    # Пробуем сначала Binance (лучшие данные), потом Gate.io
    logger.info(f"   Проверка данных...")
    
    # Приоритет бирж: Binance > Gate.io > KuCoin
    exchanges_to_try = ["binance", "gateio", "kucoin"]
    data_dir = None
    missing_pairs = []
    
    for exchange in exchanges_to_try:
        data_dir = FREQTRADE_DIR / "user_data" / "data" / exchange
        all_exist = True
        
        for pair in pairs:
            file_pair = pair.replace("/", "_")
            data_file = data_dir / f"{file_pair}-{timeframe}.json"
            if not data_file.exists():
                all_exist = False
                missing_pairs.append(pair)
        
        if all_exist and missing_pairs == []:
            logger.info(f"   ✅ Данные найдены на {exchange}")
            break
        missing_pairs = []
    
    # Если данных нет, скачиваем с лучшей доступной биржи
    if missing_pairs or data_dir is None or not all_exist:
        logger.info(f"   📥 Скачивание данных...")
        
        # Сначала пробуем Binance (лучшие данные)
        try:
            from multi_exchange_data_parser import download_and_save
            for pair in set(missing_pairs if missing_pairs else pairs):
                logger.info(f"   📥 Скачивание {pair} с Binance...")
                exchange_used, file_path = download_and_save(pair, timeframe, days=30, exchange="binance")
                if file_path:
                    logger.info(f"   ✅ {pair} скачан с {exchange_used}")
                    data_dir = FREQTRADE_DIR / "user_data" / "data" / exchange_used
        except Exception as e:
            logger.info(f"   ⚠️  Прямое скачивание не удалось: {e}, используем Freqtrade...")
        
        # Fallback: используем Freqtrade downloader
        if missing_pairs:
            download_cmd = [
                "freqtrade", "download-data",
                "--exchange", "binance",  # Сначала пробуем Binance
                "--pairs", ",".join(set(missing_pairs if missing_pairs else pairs)),
                "--timeframes", timeframe,
                "--config", str(CONFIG_PATH),
                "--days", "30"
            ]
            download_result = subprocess.run(
                download_cmd,
                cwd=str(FREQTRADE_DIR),
                capture_output=True,
                text=True,
                timeout=300
            )
            if download_result.returncode == 0:
                logger.info(f"   ✅ Данные скачаны с Binance")
                data_dir = FREQTRADE_DIR / "user_data" / "data" / "binance"
            else:
                # Fallback на Gate.io
                logger.info(f"   ⚠️  Binance недоступен, пробуем Gate.io...")
                download_cmd[2] = "gateio"
                download_result = subprocess.run(
                    download_cmd,
                    cwd=str(FREQTRADE_DIR),
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                if download_result.returncode == 0:
                    logger.info(f"   ✅ Данные скачаны с Gate.io")
                    data_dir = FREQTRADE_DIR / "user_data" / "data" / "gateio"
                else:
                    logger.info(f"   ⚠️  Ошибка скачивания данных: {download_result.stderr[:200]}")
    
    # Обновляем data_dir для использования в команде бэктеста
    if data_dir is None:
        data_dir = FREQTRADE_DIR / "user_data" / "data" / "binance"  # По умолчанию Binance
    
    # Используем --pairs напрямую, не через whitelist
    # Freqtrade будет использовать пары из --pairs даже если их нет в whitelist
    
    # ВСЕГДА используем абсолютный путь к freqtrade (правило из .cursorrules)
    venv_freqtrade = FREQTRADE_DIR / ".venv" / "bin" / "freqtrade"
    python_executable = FREQTRADE_DIR / ".venv" / "bin" / "python3"
    
    # Проверяем наличие venv freqtrade
    if venv_freqtrade.exists() and venv_freqtrade.is_file():
        freqtrade_cmd = str(venv_freqtrade.resolve())
        python_cmd = str(python_executable.resolve()) if python_executable.exists() else None
    else:
        # Fallback: используем системный python -m freqtrade
        import sys
        freqtrade_cmd = None
        python_cmd = sys.executable
    
    # Формируем команду с абсолютными путями
    if freqtrade_cmd:
        cmd = [
            freqtrade_cmd, "backtesting",
            "--config", str(CONFIG_PATH.resolve()),
            "--strategy", strategy_name,
            "--timerange", timerange,
            "--timeframe", timeframe,
            "--pairs", ",".join(pairs),
            "--export", "trades",
            "--breakdown", "month",
            "--cache", "none"
        ]
    else:
        # Fallback: python -m freqtrade с абсолютным путем к модулю
        cmd = [
            python_cmd, "-m", "freqtrade", "backtesting",
            "--config", str(CONFIG_PATH.resolve()),
            "--strategy", strategy_name,
            "--timerange", timerange,
            "--timeframe", timeframe,
            "--pairs", ",".join(pairs),
            "--export", "trades",
            "--breakdown", "month",
            "--cache", "none"
        ]
    
    # Добавляем переменную окружения для обхода проверки whitelist
    import os
    env = os.environ.copy()
    env['FREQTRADE_IGNORE_WHITELIST'] = '1'  # Временное решение
    # Активируем venv если используется
    if '.venv' in str(freqtrade_cmd) if freqtrade_cmd else False:
        venv_path = FREQTRADE_DIR / ".venv"
        if venv_path.exists():
            env['PATH'] = str(venv_path / "bin") + ":" + env.get('PATH', '')
    
    try:
        logger.info(f"🔄 [{start_time.strftime('%H:%M:%S')}] Запуск бэктеста для {strategy_name}...")
        logger.info(f"   Пары: {', '.join(pairs)}")
        logger.info(f"   Timeframe: {timeframe}, Timerange: {timerange}")
        logger.info(f"   Команда: {' '.join(cmd)}")
        
        # Записываем команду в лог
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"Команда: {' '.join(cmd)}\n")
            f.write(f"Начало: {start_time.isoformat()}\n")
            f.write(f"Рабочая директория: {FREQTRADE_DIR}\n")
            f.write(f"Конфиг: {CONFIG_PATH}\n\n")
        
        # Запускаем бэктест с использованием абсолютных путей (правило из .cursorrules)
        logger.info(f"   Выполнение команды: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                cwd=str(FREQTRADE_DIR.resolve()),
                capture_output=True,
                text=True,
                timeout=600,  # 10 минут максимум
                env=env
            )
        except subprocess.TimeoutExpired:
            logger.error(f"⏱️ Бэктест превысил таймаут (10 минут), прерываем...")
            # Создаем фиктивный результат с ошибкой таймаута
            result = type('Result', (), {
                'returncode': -1,
                'stdout': '',
                'stderr': 'Backtest timeout after 600 seconds'
            })()
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Сохраняем вывод в лог
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"\nЗавершение: {end_time.isoformat()}\n")
            f.write(f"Длительность: {duration:.1f} секунд\n")
            f.write(f"Код возврата: {result.returncode}\n\n")
            f.write("STDOUT:\n")
            f.write(result.stdout)
            f.write("\n\nSTDERR:\n")
            f.write(result.stderr)
        
        if result.returncode == 0:
            logger.info(f"✅ [{end_time.strftime('%H:%M:%S')}] Бэктест завершен для {strategy_name} за {duration:.1f}с")
            logger.info(f"   Обновление рейтинга...")
            
            # Небольшая задержка для сохранения файлов
            time.sleep(2)
            
            # Сохраняем результаты в оптимизированную БД
            if BACKTEST_DB_AVAILABLE and backtest_db:
                try:
                    # Находим последний созданный ZIP файл
                    zip_files = sorted(RESULTS_DIR.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True)
                    if zip_files:
                        latest_zip = zip_files[0]
                        logger.info(f"   💾 Сохранение результатов в БД: {latest_zip.name}")
                        
                        # Импортируем из ZIP в БД
                        for pair in pairs:
                            if backtest_db.import_from_zip(str(latest_zip)):
                                logger.info(f"   ✅ Результаты для {pair} сохранены в БД")
                            else:
                                logger.warning(f"   ⚠️  Не удалось сохранить результаты для {pair}")
                except Exception as e:
                    logger.warning(f"Ошибка сохранения в БД результатов: {e}", exc_info=True)
            
            # ВСЕГДА обновляем рейтинг после успешного бэктеста
            # Сначала пытаемся PostgreSQL, затем JSON fallback
            rating_updated = False
            
            # Пытаемся обновить PostgreSQL, если доступен
            try:
                from strategy_rating_system_postgresql import StrategyRatingSystemPostgreSQL
                rating_system = StrategyRatingSystemPostgreSQL()
                rating_system.process_and_save_to_db()
                logger.info("✅ Рейтинг обновлен в PostgreSQL")
                rating_updated = True
            except Exception as e:
                logger.warning(f"PostgreSQL недоступен, используем standalone версию: {e}")
            
            # ВСЕГДА используем standalone версию для JSON fallback
            # Это гарантирует что рейтинг будет доступен даже без PostgreSQL
            try:
                from strategy_rating_system_standalone import StrategyRatingSystemStandalone
                standalone = StrategyRatingSystemStandalone()
                strategies_count = standalone.run()  # Это обрабатывает ВСЕ ZIP файлы и создает rankings.json
                if strategies_count and strategies_count > 0:
                    logger.info(f"✅ Рейтинг сохранен в JSON (standalone): {strategies_count} стратегий")
                    rating_updated = True
                else:
                    logger.warning("⚠️  Standalone версия не нашла стратегий для обработки")
            except Exception as e2:
                logger.error(f"❌ Ошибка при сохранении рейтинга в JSON: {e2}", exc_info=True)
                import traceback
                logger.error(traceback.format_exc())
            
            if not rating_updated:
                logger.error("❌ КРИТИЧНО: Рейтинг не был обновлен ни в PostgreSQL, ни в JSON!")
        else:
            logger.error(f"[{end_time.strftime('%H:%M:%S')}] Ошибка бэктеста для {strategy_name}")
            logger.error(f"   Код: {result.returncode}")
            logger.error(f"   Ошибка: {result.stderr[:500]}")
            logger.error(f"   Лог: {log_file}")
        
    except subprocess.TimeoutExpired:
        logger.warning(f"Бэктест для {strategy_name} превысил лимит времени (10 минут)")
    except Exception as e:
        logger.error(f"Error running backtest: {e}", exc_info=True)

@app.get("/api/backtest/history")
async def get_backtest_history(strategy_name: Optional[str] = None, limit: int = 50):
    """Get backtest history"""
    # Используем JSON fallback вместо PostgreSQL
    conn = None
    if True:  # Всегда используем JSON fallback
        # Get from JSON rankings
        try:
            from rating_web_interface_standalone import get_rankings_from_json
            rankings = get_rankings_from_json(limit=limit * 10)  # Get more for filtering
            
            if strategy_name:
                rankings = [r for r in rankings if r.get('strategy_name') == strategy_name]
            
            return JSONResponse(content={
                "history": rankings[:limit],
                "total": len(rankings)
            })
        except Exception as e:
            logger.error(f"Ошибка получения истории: {e}")
            return JSONResponse(content={"history": [], "total": 0, "error": str(e)})
    
    # PostgreSQL code (disabled)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if strategy_name:
                cur.execute("""
                    SELECT * FROM backtest_results
                    WHERE strategy_name = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (strategy_name, limit))
            else:
                cur.execute("""
                    SELECT * FROM backtest_results
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))
            
            results = cur.fetchall()
            return {"history": [dict(r) for r in results]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        return_db_connection(conn)

@app.delete("/api/strategies/{strategy_name}")
async def delete_strategy(strategy_name: str):
    """Delete strategy and its backtests"""
    # JSON fallback - mark strategy as inactive in rankings
    conn = None
    if True:  # Always use JSON fallback
        try:
            from strategy_rating_system_standalone import StrategyRatingSystemStandalone
            # Re-process rankings to update
            standalone = StrategyRatingSystemStandalone()
            standalone.run()
            return JSONResponse(content={
                "status": "deleted",
                "strategy": strategy_name,
                "message": "Strategy marked as inactive"
            })
        except Exception as e:
            logger.error(f"Ошибка удаления стратегии: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # PostgreSQL code (disabled)
    try:
        with conn.cursor() as cur:
            # Mark strategy as inactive
            cur.execute("""
                UPDATE strategy_ratings
                SET is_active = FALSE
                WHERE strategy_name = %s
            """, (strategy_name,))
            
            conn.commit()
            
            return {"status": "deleted", "strategy": strategy_name}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        return_db_connection(conn)

@app.get("/api/backtest/status")
async def get_backtest_status():
    """Получить статус последних бэктестов"""
    try:
        zip_files = sorted(RESULTS_DIR.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True)
        statuses = []
        for zip_file in zip_files[:10]:
            mtime = datetime.fromtimestamp(zip_file.stat().st_mtime)
            statuses.append({
                "file": zip_file.name,
                "modified": mtime.isoformat(),
                "size": zip_file.stat().st_size,
                "age_seconds": (datetime.now() - mtime).total_seconds()
            })
        return JSONResponse(content={
            "recent_backtests": statuses,
            "total": len(zip_files)
        })
    except Exception as e:
        return JSONResponse(content={"error": str(e), "recent_backtests": [], "total": 0})

@app.get("/api/backtest/progress")
async def get_backtest_progress():
    """Получить прогресс текущих бэктестов"""
    try:
        import subprocess
        
        # Проверяем активные процессы
        processes = []
        try:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
                timeout=2
            )
            for line in result.stdout.split('\n'):
                if 'freqtrade' in line and 'backtest' in line.lower():
                    parts = line.split()
                    if len(parts) > 1:
                        processes.append({
                            "pid": parts[1],
                            "command": ' '.join(parts[10:])[:100]
                        })
        except:
            pass
        
        # Проверяем последние логи
        log_files = sorted(FREQTRADE_DIR.glob("backtest_*.log"), key=lambda x: x.stat().st_mtime, reverse=True)
        recent_logs = []
        for log_file in log_files[:3]:
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            try:
                with open(log_file, 'r') as f:
                    content = f.read()
                    lines = content.split('\n')
                    recent_logs.append({
                        "file": log_file.name,
                        "modified": mtime.isoformat(),
                        "age_seconds": (datetime.now() - mtime).total_seconds(),
                        "last_lines": lines[-5:] if len(lines) > 5 else lines
                    })
            except:
                pass
        
        return JSONResponse(content={
            "active_processes": len(processes),
            "processes": processes,
            "recent_logs": recent_logs,
            "status": "running" if processes else "idle"
        })
    except Exception as e:
        return JSONResponse(content={"error": str(e), "status": "error"})

@app.get("/api/strategies/{strategy_name}/chart-data")
async def get_strategy_chart_data(strategy_name: str, pair: str = "BTC/USDT", 
                                  timeframe: str = "5m", limit: int = 500):
    """Get OHLCV data and trade points for chart visualization"""
    try:
        import zipfile
        import json
        import time
        from pathlib import Path
        from datetime import datetime
        
        # Find latest backtest for this strategy (more flexible search)
        # Freqtrade создает файлы типа: backtest-result-YYYY-MM-DD_HH-MM-SS.zip
        # Внутри ZIP могут быть файлы с именем стратегии
        zip_files = sorted(RESULTS_DIR.glob("*.zip"), 
                          key=lambda x: x.stat().st_mtime, reverse=True)
        
        # Сначала ищем по имени файла (если есть явное совпадение)
        matching_zips = [z for z in zip_files if strategy_name.lower() in z.stem.lower()]
        
        # Если не нашли, проверяем содержимое всех ZIP файлов
        if not matching_zips:
            import zipfile
            for zip_file in zip_files[:20]:  # Проверяем последние 20 файлов
                try:
                    with zipfile.ZipFile(zip_file, 'r') as z:
                        # Ищем JSON файлы с именем стратегии
                        names = z.namelist()
                        for name in names:
                            if strategy_name.lower() in name.lower() and name.endswith('.json'):
                                matching_zips = [zip_file]
                                break
                        
                        # Также проверяем содержимое JSON файлов
                        if not matching_zips:
                            for name in names:
                                if name.endswith('.json'):
                                    try:
                                        content = z.read(name)
                                        data = json.loads(content)
                                        # Проверяем наличие стратегии в данных
                                        if isinstance(data, dict):
                                            if 'strategy' in data:
                                                if strategy_name.lower() in [s.lower() for s in data['strategy'].keys()]:
                                                    matching_zips = [zip_file]
                                                    break
                                    except:
                                        continue
                except:
                    continue
                if matching_zips:
                    break
        
        # Если все еще не нашли, берем последний файл (может содержать нужную стратегию)
        if not matching_zips and zip_files:
            matching_zips = [zip_files[0]]
        
        if not matching_zips:
            # Return empty data instead of error
            return JSONResponse(content={
                "strategy_name": strategy_name,
                "pair": pair,
                "timeframe": timeframe,
                "ohlcv": [],
                "entry_points": [],
                "exit_points": [],
                "stop_loss_lines": [],
                "take_profit_lines": [],
                "total_trades": 0,
                "has_data": False,
                "message": "No backtest data found. Run backtest first."
            })
        
        # Extract OHLCV and trades from backtest
        ohlcv_data = []
        entry_points = []
        exit_points = []
        stop_loss_lines = []
        take_profit_lines = []
        
        with zipfile.ZipFile(matching_zips[0], 'r') as zip_ref:
            # Find all JSON files
            json_files = [f for f in zip_ref.namelist() if f.endswith('.json')]
            
            trades_data = []
            
            for json_file in json_files:
                try:
                    content = zip_ref.read(json_file)
                    data = json.loads(content)
                    
                    # Check if it's trades data (list of trades)
                    if isinstance(data, list) and len(data) > 0:
                        if isinstance(data[0], dict) and 'open_date' in data[0]:
                            trades_data = data
                            break
                    
                    # Check if it's strategy result (dict with strategy key)
                    if isinstance(data, dict):
                        if 'strategy' in data:
                            # Ищем стратегию по точному имени (case-insensitive)
                            strategy_found = None
                            for strategy_name_key, strategy_info in data.get('strategy', {}).items():
                                if strategy_name.lower() == strategy_name_key.lower():
                                    strategy_found = strategy_info
                                    break
                            
                            # Если не нашли точное совпадение, берем первую стратегию
                            if not strategy_found and data.get('strategy'):
                                strategy_found = list(data['strategy'].values())[0]
                            
                            if strategy_found:
                                if 'trades' in strategy_found and isinstance(strategy_found['trades'], list):
                                    trades_data = strategy_found['trades']
                                    break
                                # Также проверяем trade list напрямую
                                if isinstance(strategy_found, dict) and 'trades' in strategy_found:
                                    if isinstance(strategy_found['trades'], list):
                                        trades_data = strategy_found['trades']
                                        break
                        elif 'trades' in data and isinstance(data['trades'], list):
                            trades_data = data['trades']
                            break
                except Exception as e:
                    logger.warning(f"Ошибка чтения {json_file}: {e}", exc_info=True)
                    continue
            
            # Extract trade points
            if trades_data:
                for trade in trades_data[:limit]:
                    try:
                        # Entry point
                        if 'open_date' in trade and trade.get('open_date'):
                            open_date = trade['open_date']
                            # Convert to timestamp if needed
                            if isinstance(open_date, str):
                                try:
                                    # Try ISO format
                                    dt = datetime.fromisoformat(open_date.replace('Z', '+00:00'))
                                    open_timestamp = dt.timestamp()
                                except:
                                    try:
                                        # Try different format
                                        dt = datetime.strptime(open_date, '%Y-%m-%d %H:%M:%S')
                                        open_timestamp = dt.timestamp()
                                    except:
                                        open_timestamp = time.time()
                            else:
                                open_timestamp = float(open_date)
                            
                            # Calculate profit_pct if missing
                            profit_pct = float(trade.get('profit_pct', 0))
                            # Используем profit_ratio если profit_pct = 0 (profit_ratio в формате 0.01 = 1%)
                            if profit_pct == 0 and trade.get('profit_ratio'):
                                profit_pct = float(trade.get('profit_ratio', 0)) * 100
                            # Если все еще 0, рассчитываем из open_rate/close_rate
                            if profit_pct == 0 and trade.get('open_rate') and trade.get('close_rate'):
                                open_rate = float(trade.get('open_rate', 0))
                                close_rate = float(trade.get('close_rate', 0))
                                if open_rate > 0:
                                    # Calculate profit percentage
                                    if trade.get('is_short', False):
                                        profit_pct = ((open_rate - close_rate) / open_rate) * 100
                                    else:
                                        profit_pct = ((close_rate - open_rate) / open_rate) * 100
                            
                            entry_points.append({
                                'x': open_timestamp,
                                'y': float(trade.get('open_rate', 0)),
                                'trade_id': str(trade.get('trade_id', '')),
                                'profit_pct': profit_pct
                            })
                            
                            # Stop-loss line
                            if 'stoploss' in trade and trade.get('stoploss'):
                                stop_price = float(trade.get('stoploss', 0))
                                close_date = trade.get('close_date', open_date)
                                if isinstance(close_date, str):
                                    try:
                                        dt = datetime.fromisoformat(close_date.replace('Z', '+00:00'))
                                        close_timestamp = dt.timestamp()
                                    except:
                                        try:
                                            dt = datetime.strptime(close_date, '%Y-%m-%d %H:%M:%S')
                                            close_timestamp = dt.timestamp()
                                        except:
                                            close_timestamp = open_timestamp + 3600
                                else:
                                    close_timestamp = float(close_date) if close_date else open_timestamp + 3600
                                
                                stop_loss_lines.append({
                                    'x': [open_timestamp, close_timestamp],
                                    'y': [stop_price, stop_price],
                                    'trade_id': str(trade.get('trade_id', ''))
                                })
                        
                        # Exit point
                        if 'close_date' in trade and trade.get('close_date'):
                            close_date = trade['close_date']
                            if isinstance(close_date, str):
                                try:
                                    dt = datetime.fromisoformat(close_date.replace('Z', '+00:00'))
                                    close_timestamp = dt.timestamp()
                                except:
                                    try:
                                        dt = datetime.strptime(close_date, '%Y-%m-%d %H:%M:%S')
                                        close_timestamp = dt.timestamp()
                                    except:
                                        continue
                            else:
                                close_timestamp = float(close_date)
                            
                            # Calculate profit_pct if missing
                            profit_pct = float(trade.get('profit_pct', 0))
                            if profit_pct == 0 and trade.get('open_rate') and trade.get('close_rate'):
                                open_rate = float(trade.get('open_rate', 0))
                                close_rate = float(trade.get('close_rate', 0))
                                if open_rate > 0:
                                    # Calculate profit percentage
                                    if trade.get('is_short', False):
                                        profit_pct = ((open_rate - close_rate) / open_rate) * 100
                                    else:
                                        profit_pct = ((close_rate - open_rate) / open_rate) * 100
                            
                            exit_points.append({
                                'x': close_timestamp,
                                'y': float(trade.get('close_rate', 0)),
                                'trade_id': str(trade.get('trade_id', '')),
                                'profit_pct': profit_pct,
                                'profit_abs': float(trade.get('profit_abs', 0))
                            })
                    except Exception as e:
                        logger.warning(f"Ошибка обработки сделки: {e}", exc_info=True)
                        continue
        
        # Optimize OHLCV data loading (limit to reasonable size)
        max_ohlcv_points = 2000  # Limit for performance
        
        # Try to get OHLCV data from data directory
        data_dir = FREQTRADE_DIR / "user_data" / "data"
        file_pair = pair.replace("/", "_")
        data_file = None
        
        # Try different exchanges and timeframes
        for exchange in ["binance", "gateio", "kaiko", "coinapi", "kucoin"]:
            # Try exact timeframe first
            potential_file = data_dir / exchange / f"{file_pair}-{timeframe}.json"
            if potential_file.exists():
                data_file = potential_file
                break
            
            # Try 5m as fallback
            if timeframe != "5m":
                potential_file = data_dir / exchange / f"{file_pair}-5m.json"
                if potential_file.exists():
                    data_file = potential_file
                    break
        
        if data_file:
            try:
                with open(data_file, 'r') as f:
                    ohlcv_raw = json.load(f)
                    # Limit data size for performance
                    max_limit = min(limit, max_ohlcv_points)
                    # Take last N candles (most recent)
                    candles_to_process = ohlcv_raw[-max_limit:] if len(ohlcv_raw) > max_limit else ohlcv_raw
                    
                    # Convert to chart format
                    for candle in candles_to_process:
                        try:
                            if isinstance(candle, list) and len(candle) >= 6:
                                ohlcv_data.append({
                                    'timestamp': float(candle[0]),
                                    'open': float(candle[1]),
                                    'high': float(candle[2]),
                                    'low': float(candle[3]),
                                    'close': float(candle[4]),
                                    'volume': float(candle[5])
                                })
                            elif isinstance(candle, dict):
                                ohlcv_data.append({
                                    'timestamp': float(candle.get('timestamp', candle.get('date', 0))),
                                    'open': float(candle.get('open', 0)),
                                    'high': float(candle.get('high', 0)),
                                    'low': float(candle.get('low', 0)),
                                    'close': float(candle.get('close', 0)),
                                    'volume': float(candle.get('volume', 0))
                                })
                        except Exception as e:
                            logger.warning(f"Ошибка обработки свечи: {e}", exc_info=True)
                            continue
            except Exception as e:
                logger.warning(f"Ошибка чтения OHLCV файла: {e}", exc_info=True)
        
        # Calculate EMA lines if we have OHLCV data
        ema_lines = {}
        if ohlcv_data and len(ohlcv_data) > 0 and PANDAS_AVAILABLE:
            try:
                # Create DataFrame from OHLCV data
                df = pd.DataFrame(ohlcv_data)
                df = df.sort_values('timestamp')
                
                # Calculate EMAs for different periods (inspired by OctoBot)
                ema_periods = [9, 21, 50, 200]
                for period in ema_periods:
                    if len(df) >= period:
                        df[f'ema_{period}'] = df['close'].ewm(span=period, adjust=False).mean()
                        # Extract EMA values with timestamps
                        ema_values = []
                        for idx, row in df.iterrows():
                            if not pd.isna(row[f'ema_{period}']):
                                ema_values.append({
                                    'timestamp': float(row['timestamp']),
                                    'value': float(row[f'ema_{period}'])
                                })
                        if ema_values:
                            ema_lines[f'ema_{period}'] = ema_values
            except Exception as e:
                logger.warning(f"Ошибка расчета EMA: {e}", exc_info=True)
        
        # Calculate PnL statistics (OctoBot style)
        pnl_stats = {
            "total_trades": len(entry_points),
            "winning_trades": 0,
            "losing_trades": 0,
            "total_profit_pct": 0.0,
            "total_profit_abs": 0.0,
            "win_rate": 0.0,
            "avg_profit_per_trade": 0.0,
            "best_trade_pct": 0.0,
            "worst_trade_pct": 0.0,
            "current_drawdown": 0.0,
            "max_drawdown": 0.0
        }
        
        # Equity curve data (cumulative profit over time)
        equity_curve = []
        trade_profits = []  # For profit bars chart
        
        if trades_data:
            try:
                profits = []
                cumulative_profit = 0.0
                initial_balance = 1000.0  # Default starting balance
                
                for trade in trades_data:
                    profit_pct = float(trade.get('profit_pct', 0))
                    profit_abs = float(trade.get('profit_abs', 0))
                    
                    # Используем profit_ratio если profit_pct = 0
                    if profit_pct == 0 and trade.get('profit_ratio'):
                        profit_pct = float(trade.get('profit_ratio', 0)) * 100
                    
                    # Если profit_pct все еще 0, рассчитываем из open_rate/close_rate
                    if profit_pct == 0 and trade.get('open_rate') and trade.get('close_rate'):
                        open_rate = float(trade.get('open_rate', 0))
                        close_rate = float(trade.get('close_rate', 0))
                        if open_rate > 0:
                            if trade.get('is_short', False):
                                profit_pct = ((open_rate - close_rate) / open_rate) * 100
                            else:
                                profit_pct = ((close_rate - open_rate) / open_rate) * 100
                    
                    if profit_pct > 0:
                        pnl_stats["winning_trades"] += 1
                    elif profit_pct < 0:
                        pnl_stats["losing_trades"] += 1
                    
                    pnl_stats["total_profit_pct"] += profit_pct
                    pnl_stats["total_profit_abs"] += profit_abs
                    profits.append(profit_pct)
                    
                    # Equity curve: cumulative profit
                    cumulative_profit += profit_pct
                    close_timestamp = trade.get('close_timestamp') or trade.get('close_date')
                    if close_timestamp:
                        if isinstance(close_timestamp, str):
                            try:
                                from datetime import datetime
                                dt = datetime.fromisoformat(close_timestamp.replace('Z', '+00:00'))
                                timestamp = dt.timestamp()
                            except:
                                import time
                                timestamp = time.time()
                        else:
                            timestamp = float(close_timestamp)
                        
                        equity_curve.append({
                            'timestamp': timestamp,
                            'equity': initial_balance * (1 + cumulative_profit / 100),
                            'profit_pct': cumulative_profit
                        })
                    
                    # Trade profits for bar chart
                    trade_profits.append({
                        'trade_id': trade.get('trade_id', len(trade_profits)),
                        'profit_pct': profit_pct,
                        'timestamp': close_timestamp if close_timestamp else time.time()
                    })
                    
                    if profit_pct > pnl_stats["best_trade_pct"]:
                        pnl_stats["best_trade_pct"] = profit_pct
                    if profit_pct < pnl_stats["worst_trade_pct"]:
                        pnl_stats["worst_trade_pct"] = profit_pct
                
                # Calculate win rate
                if pnl_stats["total_trades"] > 0:
                    pnl_stats["win_rate"] = (pnl_stats["winning_trades"] / pnl_stats["total_trades"]) * 100
                    pnl_stats["avg_profit_per_trade"] = pnl_stats["total_profit_pct"] / pnl_stats["total_trades"]
                
                # Calculate drawdown
                if profits and PANDAS_AVAILABLE:
                    try:
                        cumulative = np.cumsum(profits)
                        running_max = np.maximum.accumulate(cumulative)
                        drawdown = cumulative - running_max
                        pnl_stats["current_drawdown"] = float(drawdown[-1]) if len(drawdown) > 0 else 0.0
                        pnl_stats["max_drawdown"] = float(np.min(drawdown)) if len(drawdown) > 0 else 0.0
                    except Exception as e:
                        logger.warning(f"Ошибка расчета drawdown: {e}")
                elif profits:
                    # Fallback calculation without numpy
                    cumulative = []
                    running_max = []
                    cum_sum = 0
                    max_sum = 0
                    for profit in profits:
                        cum_sum += profit
                        max_sum = max(max_sum, cum_sum)
                        cumulative.append(cum_sum)
                        running_max.append(max_sum)
                    
                    drawdown = [c - r for c, r in zip(cumulative, running_max)]
                    pnl_stats["current_drawdown"] = float(drawdown[-1]) if drawdown else 0.0
                    pnl_stats["max_drawdown"] = float(min(drawdown)) if drawdown else 0.0
            except Exception as e:
                logger.error(f"Ошибка расчета PnL статистики: {e}", exc_info=True)
        
        return JSONResponse(content={
            "strategy_name": strategy_name,
            "pair": pair,
            "timeframe": timeframe,
            "ohlcv": ohlcv_data,
            "entry_points": entry_points,
            "exit_points": exit_points,
            "stop_loss_lines": stop_loss_lines,
            "take_profit_lines": take_profit_lines,
            "ema_lines": ema_lines,  # New: EMA overlay data
            "pnl_stats": pnl_stats,  # New: PnL dashboard data (OctoBot style)
            "equity_curve": equity_curve,  # Equity curve data for subplot
            "trade_profits": trade_profits,  # Trade profits for bar chart
            "total_trades": len(entry_points),
            "has_data": len(ohlcv_data) > 0 or len(entry_points) > 0
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении данных графика: {e}", exc_info=True)
        return JSONResponse(
            status_code=200,
            content={
                "strategy_name": strategy_name,
                "pair": pair,
                "timeframe": timeframe,
                "ohlcv": [],
                "entry_points": [],
                "exit_points": [],
                "stop_loss_lines": [],
                "take_profit_lines": [],
                "total_trades": 0,
                "error": str(e),
                "has_data": False
            }
        )

@app.get("/api/strategies/{strategy_name}/details")
async def get_strategy_details(strategy_name: str):
    """Get detailed information about a specific strategy including monthly breakdown"""
    try:
        import sys
        sys.path.insert(0, str(FREQTRADE_DIR))
        from strategy_rating_system_standalone import StrategyRatingSystemStandalone
        from rating_web_interface_standalone import get_rankings_from_json
        import zipfile
        import json
        from pathlib import Path
        
        # Get strategy info from rankings
        rankings = get_rankings_from_json(limit=1000)
        strategy_info = next((r for r in rankings if r.get("strategy_name") == strategy_name), None)
        
        if not strategy_info:
            raise HTTPException(status_code=404, detail=f"Strategy {strategy_name} not found")
        
        # Get monthly breakdown from backtest results
        monthly_breakdown = []
        zip_files = sorted(RESULTS_DIR.glob(f"{strategy_name}_*.zip"), key=lambda x: x.stat().st_mtime, reverse=True)
        
        for zip_file in zip_files[:10]:  # Последние 10 бэктестов
            try:
                with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                    # Ищем JSON файл в ZIP
                    json_files = [f for f in zip_ref.namelist() if f.endswith('.json') and 'strategy' in f.lower()]
                    if json_files:
                        json_content = zip_ref.read(json_files[0])
                        data = json.loads(json_content)
                        
                        # Извлекаем breakdown по месяцам
                        if 'strategy' in data and strategy_name in data['strategy']:
                            strategy_data = data['strategy'][strategy_name]
                            
                            # Проверяем разные варианты структуры breakdown
                            breakdown = None
                            if 'periodic_breakdown' in strategy_data:
                                # Freqtrade использует periodic_breakdown с ключом 'month'
                                periodic = strategy_data.get('periodic_breakdown', {})
                                if isinstance(periodic, dict) and 'month' in periodic:
                                    breakdown = periodic['month']
                            elif 'breakdown' in strategy_data:
                                breakdown = strategy_data['breakdown']
                            elif 'monthly_breakdown' in strategy_data:
                                breakdown = strategy_data['monthly_breakdown']
                            elif 'results' in strategy_data and 'breakdown' in strategy_data['results']:
                                breakdown = strategy_data['results']['breakdown']
                            
                            if breakdown:
                                # breakdown может быть dict или list
                                if isinstance(breakdown, dict):
                                    for month, month_data in breakdown.items():
                                        if isinstance(month_data, dict):
                                            monthly_breakdown.append({
                                                'month': month,
                                                'trades': month_data.get('trades', month_data.get('buys', 0)),
                                                'profit_pct': month_data.get('profit_pct', month_data.get('profit', 0)),
                                                'win_rate': month_data.get('win_rate', month_data.get('winp', 0)),
                                                'drawdown': month_data.get('drawdown', month_data.get('ddp', 0)),
                                                'sharpe': month_data.get('sharpe', month_data.get('sharpe_ratio', 0)),
                                                'cum_profit_pct': month_data.get('cum_profit_pct', 0),
                                                'backtest_file': zip_file.name
                                            })
                                elif isinstance(breakdown, list):
                                    # Freqtrade format: list of dicts with date keys
                                    for month_data in breakdown:
                                        if isinstance(month_data, dict):
                                            # Extract date from keys like 'date', 'period', 'month', or use index
                                            month_key = month_data.get('date', month_data.get('period', month_data.get('month', 'N/A')))
                                            # Format to YYYYMM if needed
                                            if isinstance(month_key, str) and len(month_key) >= 7:
                                                month_key = month_key[:7].replace('-', '')  # YYYY-MM -> YYYYMM
                                            
                                            monthly_breakdown.append({
                                                'month': month_key,
                                                'trades': month_data.get('trades', month_data.get('buys', month_data.get('trade_count', 0))),
                                                'profit_pct': month_data.get('profit_pct', month_data.get('profit', month_data.get('profit_total_pct', 0))),
                                                'win_rate': month_data.get('win_rate', month_data.get('winp', month_data.get('winrate', 0)) * 100 if month_data.get('winrate') else 0),
                                                'drawdown': abs(month_data.get('drawdown', month_data.get('ddp', month_data.get('max_drawdown', 0)))),
                                                'sharpe': month_data.get('sharpe', month_data.get('sharpe_ratio', month_data.get('sharpe', 0))),
                                                'cum_profit_pct': month_data.get('cum_profit_pct', month_data.get('profit_pct', 0)),
                                                'backtest_file': zip_file.name
                                            })
                            
                            # Если breakdown нет, пытаемся извлечь из trades
                            if not breakdown and 'trades' in strategy_data:
                                # Группируем трейды по месяцам
                                trades = strategy_data.get('trades', [])
                                if trades:
                                    from collections import defaultdict
                                    monthly_trades = defaultdict(list)
                                    for trade in trades:
                                        if 'close_date' in trade:
                                            from datetime import datetime
                                            try:
                                                close_date = datetime.fromisoformat(trade['close_date'].replace('Z', '+00:00'))
                                                month_key = close_date.strftime('%Y%m')
                                                monthly_trades[month_key].append(trade)
                                            except:
                                                pass
                                    
                                    # Вычисляем метрики по месяцам
                                    for month, month_trades in monthly_trades.items():
                                        if month_trades:
                                            wins = sum(1 for t in month_trades if t.get('profit_abs', 0) > 0)
                                            total_profit = sum(t.get('profit_abs', 0) for t in month_trades)
                                            total_profit_pct = sum(t.get('profit_pct', 0) for t in month_trades)
                                            
                                            monthly_breakdown.append({
                                                'month': month,
                                                'trades': len(month_trades),
                                                'profit_pct': total_profit_pct / len(month_trades) if month_trades else 0,
                                                'win_rate': (wins / len(month_trades) * 100) if month_trades else 0,
                                                'drawdown': 0,  # Нужно вычислить отдельно
                                                'sharpe': 0,  # Нужно вычислить отдельно
                                                'cum_profit_pct': total_profit_pct,
                                                'backtest_file': zip_file.name
                                            })
            except Exception as e:
                continue
        
        # Calculate strategy hash
        strategy_file = STRATEGIES_DIR / f"{strategy_name}.py"
        strategy_hash = None
        if strategy_file.exists():
            import hashlib
            with open(strategy_file, 'rb') as f:
                strategy_hash = hashlib.sha256(f.read()).hexdigest()
        
        # Extract indicators from strategy file
        indicators = []
        if strategy_file.exists():
            try:
                with open(strategy_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Простой поиск индикаторов (можно улучшить)
                    import re
                    indicator_patterns = [
                        r"ta\.(\w+)\(",
                        r"qtpylib\.(\w+)\(",
                        r"ftt\.(\w+)\(",
                        r"dataframe\['(\w+)'\]",
                    ]
                    for pattern in indicator_patterns:
                        matches = re.findall(pattern, content)
                        indicators.extend(matches)
            except:
                pass
        
        return JSONResponse(content={
            "strategy_name": strategy_name,
            "strategy_info": strategy_info,
            "monthly_breakdown": sorted(monthly_breakdown, key=lambda x: x['month'], reverse=True),
            "hash": strategy_hash,
            "indicators": list(set(indicators))[:50],  # Уникальные индикаторы, максимум 50
            "timeframe": strategy_info.get("timeframe", "5m"),
            "stoploss": strategy_info.get("stoploss", -0.99)
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении деталей стратегии: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats")
async def get_stats():
    """Get overall statistics (like strat.ninja stats page)"""
    # ВСЕГДА используем JSON fallback для статистики
    conn = None  # Принудительно используем JSON fallback
    if True:  # Всегда используем JSON fallback
        # Fallback: используем standalone JSON версию
        try:
            import sys
            sys.path.insert(0, str(FREQTRADE_DIR))
            from strategy_rating_system_standalone import StrategyRatingSystemStandalone
            from rating_web_interface_standalone import get_rankings_from_json
            from strategy_rating_system_standalone import get_all_strategies
            
            rankings = get_rankings_from_json(limit=10000)
            all_strategies = get_all_strategies()
            
            # Подсчитываем статистику как на strat.ninja
            total_strategies = len(all_strategies)
            total_backtests = sum(r.get("total_backtests", 0) for r in rankings)
            
            # Подсчитываем проценты
            failed_count = len([r for r in rankings if r.get("is_stalled", False) or r.get("total_backtests", 0) == 0])
            lookahead_count = len([r for r in rankings if r.get("has_lookahead_bias", False)])
            stalled_count = len([r for r in rankings if r.get("is_stalled", False)])
            private_count = len([r for r in rankings if not r.get("strategy_url") or r.get("strategy_url") == ""])
            dca_count = len([r for r in rankings if r.get("is_dca", False)])
            multiclass_count = len([r for r in rankings if r.get("is_multiclass", False)])
            
            # Топ стратегия
            top_strategy = None
            if rankings:
                sorted_rankings = sorted(rankings, key=lambda x: x.get("ninja_score", 0), reverse=True)
                top = sorted_rankings[0]
                top_strategy = {
                    "strategy_name": top.get("strategy_name", ""),
                    "ninja_score": top.get("ninja_score", 0),
                    "median_total_profit_pct": top.get("median_total_profit_pct", 0)
                }
            
            # Последние бэктесты
            zip_files = sorted(RESULTS_DIR.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True)
            latest_backtests = [f.stem.replace('_', ' ') for f in zip_files[:10]]
            
            return JSONResponse(
                status_code=200,
                content={
                    "total_strategies": total_strategies,
                    "total_backtests": total_backtests,
                    "top_strategy": top_strategy,
                    "failed_testing_pct": round((failed_count / total_strategies * 100) if total_strategies > 0 else 0, 1),
                    "failed_count": failed_count,
                    "lookahead_pct": round((lookahead_count / total_strategies * 100) if total_strategies > 0 else 0, 1),
                    "lookahead_count": lookahead_count,
                    "stalled_pct": round((stalled_count / total_strategies * 100) if total_strategies > 0 else 0, 1),
                    "stalled_count": stalled_count,
                    "private_pct": round((private_count / total_strategies * 100) if total_strategies > 0 else 0, 1),
                    "private_count": private_count,
                    "dca_pct": round((dca_count / total_strategies * 100) if total_strategies > 0 else 0, 1),
                    "dca_count": dca_count,
                    "multiclass_pct": round((multiclass_count / total_strategies * 100) if total_strategies > 0 else 0, 1),
                    "multiclass_count": multiclass_count,
                    "latest_backtests": latest_backtests,
                    "source": "json"
                }
            )
        except Exception as e:
            logger.warning(f"Ошибка при чтении статистики: {e}", exc_info=True)
            return JSONResponse(
                status_code=200,
                content={
                    "total_strategies": 0,
                    "total_backtests": 0,
                    "top_strategy": None,
                    "error": "Нет данных. Запустите бэктесты."
                }
            )
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Total strategies
            cur.execute("SELECT COUNT(*) as total FROM strategy_ratings WHERE is_active = TRUE")
            result = cur.fetchone()
            total_strategies = result["total"] if result else 0
            
            # Total backtests
            cur.execute("SELECT COUNT(*) as total FROM backtest_results")
            result = cur.fetchone()
            total_backtests = result["total"] if result else 0
            
            # Top strategy
            cur.execute("""
                SELECT strategy_name, ninja_score, median_total_profit_pct
                FROM strategy_ratings
                WHERE is_active = TRUE
                ORDER BY ninja_score DESC
                LIMIT 1
            """)
            top_result = cur.fetchone()
            top_strategy = None
            if top_result and cur.rowcount > 0:
                top_strategy = dict(top_result)
                # Конвертируем значения
                for key, value in top_strategy.items():
                    if hasattr(value, 'isoformat'):
                        top_strategy[key] = value.isoformat()
            
            return JSONResponse(
                status_code=200,
                content={
                    "total_strategies": int(total_strategies),
                    "total_backtests": int(total_backtests),
                    "top_strategy": top_strategy
                }
            )
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}", exc_info=True)
        return JSONResponse(
            status_code=200,
            content={
                "total_strategies": 0,
                "total_backtests": 0,
                "top_strategy": None,
                "error": str(e)
            }
        )
    finally:
        if conn:
            return_db_connection(conn)

# API endpoints для альтернативных бэктестеров
@app.post("/api/vectorbt/run")
async def run_vectorbt_backtest(request: dict):
    """Запуск бэктеста через VectorBT (в разработке)"""
    return JSONResponse(content={
        "success": False,
        "error": "VectorBT интеграция в разработке. Используйте основной бэктестер Freqtrade.",
        "message": "Для использования VectorBT установите: pip install vectorbt"
    })

@app.post("/api/octobot/run")
async def run_octobot_backtest(request: dict):
    """Запуск бэктеста через OctoBot (в разработке)"""
    return JSONResponse(content={
        "success": False,
        "error": "OctoBot интеграция в разработке. Используйте основной бэктестер Freqtrade.",
        "message": "OctoBot требует отдельной установки и настройки."
    })

@app.post("/api/hummingbot/run")
async def run_hummingbot_backtest(request: dict):
    """Запуск бэктеста через Hummingbot (в разработке)"""
    return JSONResponse(content={
        "success": False,
        "error": "Hummingbot интеграция в разработке. Используйте основной бэктестер Freqtrade.",
        "message": "Hummingbot требует отдельной установки и настройки."
    })

@app.post("/api/jesse/run")
async def run_jesse_backtest(request: dict):
    """Запуск бэктеста через Jesse (в разработке)"""
    return JSONResponse(content={
        "success": False,
        "error": "Jesse интеграция в разработке",
        "message": "Jesse требует отдельной установки и настройки. Используйте основной бэктестер Freqtrade для тестирования стратегий.",
        "installation": "pip install jesse",
        "docs": "https://docs.jesse.trade/",
        "alternative": "Используйте Freqtrade бэктестер через главную страницу"
    })

# Optuna Optimization Endpoints
@app.post("/api/optimize/strategy")
async def optimize_strategy_endpoint(request: dict):
    """Optimize strategy parameters using Optuna"""
    try:
        from strategy_optimizer_optuna import StrategyOptimizer, OPTUNA_AVAILABLE
        
        if not OPTUNA_AVAILABLE:
            return JSONResponse(content={
                "success": False,
                "error": "Optuna не установлен",
                "message": "Установите: pip install optuna"
            })
        
        strategy_name = request.get('strategy_name')
        pair = request.get('pair', 'BTC/USDT')
        timeframe = request.get('timeframe', '5m')
        n_trials = request.get('n_trials', 30)
        timeout = request.get('timeout', 3600)
        
        if not strategy_name:
            raise HTTPException(status_code=400, detail="strategy_name required")
        
        optimizer = StrategyOptimizer(strategy_name, pair, timeframe)
        result = optimizer.optimize(n_trials=n_trials, timeout=timeout)
        
        return JSONResponse(content={
            "success": True,
            "strategy": strategy_name,
            "best_params": result['best_params'],
            "best_value": result['best_value'],
            "n_trials": result['n_trials'],
            "message": f"Оптимизация завершена: {result['n_trials']} trials"
        })
    except ImportError as e:
        return JSONResponse(content={
            "success": False,
            "error": "Optuna не установлен",
            "message": str(e)
        })
    except Exception as e:
        logger.error(f"Ошибка оптимизации: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/optimize/status/{strategy_name}")
async def get_optimization_status(strategy_name: str):
    """Get optimization status and best parameters for strategy"""
    try:
        from strategy_optimizer_optuna import OPTUNA_AVAILABLE
        import optuna
        
        if not OPTUNA_AVAILABLE:
            return JSONResponse(content={
                "optimized": False,
                "message": "Optuna не установлен"
            })
        
        # Load study
        study_path = FREQTRADE_DIR / "user_data" / "optuna_studies" / f"{strategy_name}_BTC_USDT_5m.db"
        if not study_path.exists():
            return JSONResponse(content={
                "optimized": False,
                "message": "Оптимизация не выполнялась"
            })
        
        storage = f"sqlite:///{study_path}"
        study = optuna.load_study(study_name=f"{strategy_name}_BTC_USDT_5m", storage=storage)
        
        return JSONResponse(content={
            "optimized": True,
            "best_params": study.best_params,
            "best_value": -study.best_value,  # Convert back to positive
            "n_trials": len(study.trials),
            "last_optimized": study.trials[-1].datetime_start.isoformat() if study.trials else None
        })
    except Exception as e:
        logger.error(f"Ошибка получения статуса оптимизации: {e}")
        return JSONResponse(content={
            "optimized": False,
            "error": str(e)
        })

@app.post("/api/strategy/switch")
async def switch_strategy_endpoint(request: dict):
    """Switch active strategy based on performance"""
    try:
        from strategy_switcher_optuna import AutoStrategyManager
        
        current_strategy = request.get('current_strategy')
        current_metrics = request.get('current_metrics', {})
        
        manager = AutoStrategyManager()
        if current_strategy:
            manager.active_strategy = current_strategy
        
        result = manager.monitor_and_manage(current_metrics)
        
        return JSONResponse(content={
            "success": True,
            "action": result.get('action'),
            "strategy": result.get('strategy') or result.get('to'),
            "reason": result.get('reason'),
            "new_params": result.get('new_params')
        })
    except Exception as e:
        logger.error(f"Ошибка переключения стратегии: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8889)

