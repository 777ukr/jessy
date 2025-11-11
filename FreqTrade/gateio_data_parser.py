#!/usr/bin/env python3
"""
Gate.io Data Parser
Автоматическая загрузка исторических данных с Gate.io для бэктестов
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import subprocess

# Configuration
FREQTRADE_DIR = Path(__file__).parent
CONFIG_FILE = FREQTRADE_DIR.parent / "config" / "freqtrade_config.json"
DATA_DIR = FREQTRADE_DIR / "user_data" / "data"
GATEIO_API_BASE = "https://api.gateio.ws/api/v4"

# Пытаемся получить ключи из переменных окружения или конфига
def get_gateio_keys():
    """Получить API ключи Gate.io из env или конфига"""
    api_key = os.getenv("GATEIO_API_KEY", "")
    secret_key = os.getenv("GATEIO_SECRET_KEY", "")
    
    # Если не в env, пытаемся из конфига Freqtrade
    if not api_key and CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                exchange_config = config.get("exchange", {})
                if exchange_config.get("name") == "gateio":
                    api_key = exchange_config.get("key", "")
                    secret_key = exchange_config.get("secret", "")
        except Exception:
            pass
    
    return api_key, secret_key

GATEIO_API_KEY, GATEIO_SECRET_KEY = get_gateio_keys()

# Gate.io комиссии (maker/taker)
GATEIO_FEES = {
    "spot": {
        "maker": 0.002,  # 0.2%
        "taker": 0.002   # 0.2%
    },
    "futures": {
        "maker": 0.0002,  # 0.02%
        "taker": 0.0005  # 0.05%
    }
}


class GateioDataParser:
    """Парсер данных с Gate.io"""
    
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        
        # Используем ключи из модуля (env или конфиг)
        self.api_key = GATEIO_API_KEY
        self.secret_key = GATEIO_SECRET_KEY
        
        if self.api_key and self.secret_key:
            print(f"✅ API ключи Gate.io найдены (из {'env' if os.getenv('GATEIO_API_KEY') else 'конфига'})")
        else:
            print("⚠️  API ключи Gate.io не найдены (работаем в публичном режиме)")
            print("💡 Для использования ключей:")
            print("   1. Установите переменные окружения:")
            print("      export GATEIO_API_KEY='your_key'")
            print("      export GATEIO_SECRET_KEY='your_secret'")
            print("   2. Или добавьте ключи в конфиг Freqtrade:")
            print(f"      {CONFIG_FILE}")
            print("      В секции exchange -> key и secret")
    
    def get_available_pairs(self) -> List[str]:
        """Получить список доступных торговых пар"""
        try:
            url = f"{GATEIO_API_BASE}/spot/currency_pairs"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            pairs = response.json()
            # Фильтруем только USDT пары
            usdt_pairs = [
                pair["id"].replace("_", "/") 
                for pair in pairs 
                if pair["id"].endswith("_USDT") and pair["trade_status"] == "tradable"
            ]
            
            print(f"✅ Найдено {len(usdt_pairs)} доступных USDT пар")
            return sorted(usdt_pairs)
            
        except Exception as e:
            print(f"❌ Ошибка при получении списка пар: {e}")
            return []
    
    def download_candles(
        self, 
        pair: str, 
        interval: str = "5m",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Скачать свечи с Gate.io
        
        Args:
            pair: Торговая пара (BTC/USDT)
            interval: Интервал (1m, 5m, 15m, 1h, 4h, 1d)
            start_time: Начало периода
            end_time: Конец периода
        """
        # Конвертируем пару в формат Gate.io (BTC/USDT -> BTC_USDT)
        gate_pair = pair.replace("/", "_")
        
        # Интервалы Gate.io
        interval_map = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "4h": "4h",
            "1d": "1d"
        }
        
        gate_interval = interval_map.get(interval, "5m")
        
        # Временные метки (исправлено: используем правильное время)
        if not start_time:
            start_time = datetime.now() - timedelta(days=30)
        if not end_time:
            end_time = datetime.now()
        
        # Gate.io API требует секунды, не миллисекунды
        start_ts = int(start_time.timestamp())
        end_ts = int(end_time.timestamp())
        
        # Проверяем что время не в будущем
        now_ts = int(datetime.now().timestamp())
        if start_ts > now_ts:
            start_ts = now_ts - (30 * 24 * 60 * 60)  # 30 дней назад
        if end_ts > now_ts:
            end_ts = now_ts
        
        url = f"{GATEIO_API_BASE}/spot/candlesticks"
        params = {
            "currency_pair": gate_pair,
            "interval": gate_interval,
            "from": start_ts,
            "to": end_ts,
            "limit": 1000  # Максимум за запрос
        }
        
        all_candles = []
        current_start = start_ts
        
        try:
            while current_start < end_ts:
                params["from"] = current_start
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                
                candles = response.json()
                if not candles:
                    break
                
                all_candles.extend(candles)
                
                # Обновляем начальное время для следующего запроса
                if candles:
                    last_ts = int(candles[-1][0])
                    if last_ts <= current_start:
                        break
                    current_start = last_ts + 1
                
                # Rate limit
                time.sleep(0.1)
            
            print(f"✅ Скачано {len(all_candles)} свечей для {pair} ({interval})")
            return all_candles
            
        except Exception as e:
            print(f"❌ Ошибка при скачивании данных для {pair}: {e}")
            return []
    
    def save_to_freqtrade_format(
        self, 
        pair: str, 
        interval: str, 
        candles: List[Dict]
    ) -> Path:
        """
        Сохранить данные в формате Freqtrade
        
        Формат: timestamp,open,high,low,close,volume
        """
        # Конвертируем пару в формат Freqtrade (BTC/USDT -> BTC_USDT)
        freq_pair = pair.replace("/", "_")
        
        # Создаем директорию для биржи
        exchange_dir = DATA_DIR / "gateio"
        exchange_dir.mkdir(parents=True, exist_ok=True)
        
        # Имя файла
        filename = f"{freq_pair}-{interval}.json"
        filepath = exchange_dir / filename
        
        # Конвертируем свечи Gate.io в формат Freqtrade
        # Gate.io формат: [timestamp, volume, close, high, low, open]
        # Freqtrade формат: [timestamp, open, high, low, close, volume]
        freq_candles = []
        for candle in candles:
            if len(candle) >= 6:
                ts = int(candle[0])
                volume = float(candle[1])
                close = float(candle[2])
                high = float(candle[3])
                low = float(candle[4])
                open_price = float(candle[5])
                
                freq_candles.append([
                    ts * 1000,  # Freqtrade использует миллисекунды
                    open_price,
                    high,
                    low,
                    close,
                    volume
                ])
        
        # Сохраняем в JSON
        with open(filepath, 'w') as f:
            json.dump(freq_candles, f)
        
        print(f"✅ Данные сохранены: {filepath}")
        return filepath
    
    def download_pair_for_backtest(
        self, 
        pair: str, 
        interval: str = "5m",
        days: int = 30
    ) -> bool:
        """Скачать данные для бэктеста"""
        print(f"📥 Скачивание данных для {pair} ({interval}, {days} дней)...")
        
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        candles = self.download_candles(pair, interval, start_time, end_time)
        
        if candles:
            self.save_to_freqtrade_format(pair, interval, candles)
            
            # Также скачиваем данные для Freqtrade через download-data
            self._download_via_freqtrade(pair, interval, days)
            return True
        
        return False
    
    def _download_via_freqtrade(
        self, 
        pair: str, 
        interval: str, 
        days: int
    ):
        """Скачать данные через Freqtrade CLI (более надежно)"""
        try:
            cmd = [
                "freqtrade", "download-data",
                "--exchange", "gateio",
                "--pairs", pair,
                "--timeframes", interval,
                "--days", str(days),
                "--data-format-ohlcv", "json"
            ]
            
            result = subprocess.run(
                cmd,
                cwd=str(FREQTRADE_DIR),
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                print(f"✅ Данные скачаны через Freqtrade CLI")
            else:
                print(f"⚠️  Freqtrade CLI вернул код {result.returncode}")
                
        except Exception as e:
            print(f"⚠️  Ошибка при скачивании через Freqtrade: {e}")
    
    def download_top_pairs(self, limit: int = 10, interval: str = "5m", days: int = 30):
        """Скачать данные для топ-пар"""
        pairs = self.get_available_pairs()
        
        # Топ-пары по умолчанию
        top_pairs = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
        
        # Добавляем другие популярные пары
        for pair in pairs:
            if pair not in top_pairs and len(top_pairs) < limit:
                top_pairs.append(pair)
        
        print(f"📊 Скачивание данных для {len(top_pairs)} пар...")
        
        for pair in top_pairs:
            self.download_pair_for_backtest(pair, interval, days)
            time.sleep(1)  # Rate limit


def calculate_gateio_fees(
    trade_amount: float,
    trade_type: str = "spot",
    is_maker: bool = True
) -> float:
    """
    Рассчитать комиссию Gate.io
    
    Args:
        trade_amount: Сумма сделки
        trade_type: spot или futures
        is_maker: True для maker, False для taker
    """
    fee_rate = GATEIO_FEES[trade_type]["maker" if is_maker else "taker"]
    return trade_amount * fee_rate


def apply_fees_to_backtest_result(
    profit_pct: float,
    total_trades: int,
    trade_type: str = "spot",
    is_maker: bool = True
) -> float:
    """
    Применить комиссии к результату бэктеста
    
    Args:
        profit_pct: Прибыль в процентах
        total_trades: Количество сделок
        trade_type: spot или futures
        is_maker: True для maker, False для taker
    """
    fee_rate = GATEIO_FEES[trade_type]["maker" if is_maker else "taker"]
    
    # Каждая сделка = вход + выход = 2 комиссии
    total_fees_pct = fee_rate * 2 * total_trades * 100
    
    # Вычитаем комиссии из прибыли
    adjusted_profit = profit_pct - total_fees_pct
    
    return adjusted_profit


def main():
    """Main entry point"""
    parser = GateioDataParser()
    
    # Скачиваем топ-пары
    parser.download_top_pairs(limit=10, interval="5m", days=30)
    
    print("\n✅ Загрузка данных завершена!")


if __name__ == "__main__":
    main()

