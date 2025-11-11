#!/usr/bin/env python3
"""
Premium Data Provider - Kaiko and CoinAPI integration
Fetches high-quality historical data for accurate backtesting
"""

import os
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import json
import time

# API Keys
KAIKO_API_KEY = os.getenv("KAIKO_API_KEY", "ec47c618-04bb-4eff-a962-dad3fab8ca45")
COINAPI_API_KEY = os.getenv("COINAPI_API_KEY", "")

# Data directories
FREQTRADE_DIR = Path(__file__).parent
DATA_DIR = FREQTRADE_DIR / "user_data" / "data"

class PremiumDataProvider:
    """Fetch historical data from premium sources (Kaiko, CoinAPI)"""
    
    def __init__(self, kaiko_key: str = KAIKO_API_KEY, coinapi_key: str = COINAPI_API_KEY):
        self.kaiko_key = kaiko_key
        self.coinapi_key = coinapi_key
        self.kaiko_base_url = "https://us.market-api.kaiko.io/v2/data"
        self.coinapi_base_url = "https://rest.coinapi.io/v1"
        
    def download_from_kaiko(self, pair: str, timeframe: str, start_date: datetime, 
                            end_date: datetime) -> Optional[pd.DataFrame]:
        """Download OHLCV data from Kaiko"""
        try:
            # Convert pair to Kaiko format (BTC-USDT)
            kaiko_pair = pair.replace("/", "-")
            
            # Convert timeframe to Kaiko interval
            interval_map = {
                "30s": "1s",  # Kaiko supports 1s, we'll aggregate
                "1m": "1m",
                "5m": "5m",
                "15m": "15m",
                "1h": "1h",
                "4h": "4h",
                "1d": "1d"
            }
            interval = interval_map.get(timeframe, "1m")
            
            # Kaiko API endpoint
            url = f"{self.kaiko_base_url}/trades.v1/spot_direct_exchange_rate"
            
            params = {
                "pair": kaiko_pair,
                "start_time": start_date.isoformat(),
                "end_time": end_date.isoformat(),
                "interval": interval,
                "page_size": 10000
            }
            
            headers = {
                "X-Api-Key": self.kaiko_key,
                "Accept": "application/json"
            }
            
            print(f"📥 Загрузка данных с Kaiko для {pair} ({timeframe})...")
            response = requests.get(url, params=params, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if "data" in data and len(data["data"]) > 0:
                    df = pd.DataFrame(data["data"])
                    # Convert to OHLCV format
                    df = self._convert_kaiko_to_ohlcv(df, timeframe)
                    print(f"✅ Загружено {len(df)} свечей с Kaiko")
                    return df
                else:
                    print(f"⚠️  Kaiko вернул пустые данные")
                    return None
            else:
                print(f"❌ Ошибка Kaiko API: {response.status_code} - {response.text[:200]}")
                return None
                
        except Exception as e:
            print(f"❌ Ошибка при загрузке с Kaiko: {e}")
            return None
    
    def download_from_coinapi(self, pair: str, timeframe: str, start_date: datetime,
                              end_date: datetime) -> Optional[pd.DataFrame]:
        """Download OHLCV data from CoinAPI"""
        if not self.coinapi_key:
            return None
            
        try:
            # Convert pair to CoinAPI format (BINANCE_SPOT_BTC_USDT)
            exchange = "BINANCE"
            base_asset = pair.split("/")[0]
            quote_asset = pair.split("/")[1]
            symbol_id = f"{exchange}_SPOT_{base_asset}_{quote_asset}"
            
            # Convert timeframe
            period_map = {
                "30s": "30SEC",
                "1m": "1MIN",
                "5m": "5MIN",
                "15m": "15MIN",
                "1h": "1HRS",
                "4h": "4HRS",
                "1d": "1DAY"
            }
            period = period_map.get(timeframe, "1MIN")
            
            url = f"{self.coinapi_base_url}/ohlcv/{symbol_id}/history"
            
            params = {
                "period_id": period,
                "time_start": start_date.isoformat(),
                "time_end": end_date.isoformat(),
                "limit": 100000
            }
            
            headers = {
                "X-CoinAPI-Key": self.coinapi_key,
                "Accept": "application/json"
            }
            
            print(f"📥 Загрузка данных с CoinAPI для {pair} ({timeframe})...")
            response = requests.get(url, params=params, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if len(data) > 0:
                    df = pd.DataFrame(data)
                    df = self._convert_coinapi_to_ohlcv(df)
                    print(f"✅ Загружено {len(df)} свечей с CoinAPI")
                    return df
                else:
                    print(f"⚠️  CoinAPI вернул пустые данные")
                    return None
            else:
                print(f"❌ Ошибка CoinAPI: {response.status_code} - {response.text[:200]}")
                return None
                
        except Exception as e:
            print(f"❌ Ошибка при загрузке с CoinAPI: {e}")
            return None
    
    def _convert_kaiko_to_ohlcv(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """Convert Kaiko data to OHLCV format"""
        # Kaiko returns trade data, need to aggregate to OHLCV
        if "timestamp" in df.columns:
            df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = df.set_index("date")
        
        # Aggregate to OHLCV
        ohlcv = df.resample(timeframe).agg({
            "price": ["first", "max", "min", "last"],
            "size": "sum"
        })
        
        ohlcv.columns = ["open", "high", "low", "close", "volume"]
        ohlcv = ohlcv.dropna()
        
        return ohlcv.reset_index()
    
    def _convert_coinapi_to_ohlcv(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert CoinAPI data to OHLCV format"""
        if "time_period_start" in df.columns:
            df["date"] = pd.to_datetime(df["time_period_start"])
            df = df.set_index("date")
        
        # CoinAPI already has OHLCV format
        ohlcv = df[["price_open", "price_high", "price_low", "price_close", "volume_traded"]].copy()
        ohlcv.columns = ["open", "high", "low", "close", "volume"]
        ohlcv = ohlcv.dropna()
        
        return ohlcv.reset_index()
    
    def download_and_save(self, pair: str, timeframe: str, days: int = 30,
                          exchange: str = "kaiko") -> tuple[str, Optional[Path]]:
        """
        Download data from premium source and save in Freqtrade format
        
        Priority: Kaiko > CoinAPI > Binance (fallback)
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        df = None
        source_used = None
        
        # Try Kaiko first
        if exchange == "kaiko" or exchange == "premium":
            df = self.download_from_kaiko(pair, timeframe, start_date, end_date)
            if df is not None:
                source_used = "kaiko"
        
        # Try CoinAPI if Kaiko failed
        if df is None and self.coinapi_key:
            df = self.download_from_coinapi(pair, timeframe, start_date, end_date)
            if df is not None:
                source_used = "coinapi"
        
        if df is None:
            print(f"⚠️  Premium источники недоступны, используем fallback")
            return "fallback", None
        
        # Save to Freqtrade format
        file_pair = pair.replace("/", "_")
        data_dir = DATA_DIR / source_used
        data_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = data_dir / f"{file_pair}-{timeframe}.json"
        
        # Convert to Freqtrade JSON format
        freqtrade_data = []
        for _, row in df.iterrows():
            timestamp = int(row["date"].timestamp() * 1000) if "date" in row else int(time.time() * 1000)
            freqtrade_data.append([
                timestamp / 1000,  # timestamp
                row["open"],
                row["high"],
                row["low"],
                row["close"],
                row["volume"]
            ])
        
        with open(output_file, 'w') as f:
            json.dump(freqtrade_data, f, indent=2)
        
        print(f"✅ Данные сохранены: {output_file}")
        return source_used, output_file

if __name__ == "__main__":
    # Test
    provider = PremiumDataProvider()
    source, file = provider.download_and_save("BTC/USDT", "1m", days=7, exchange="kaiko")
    print(f"Source: {source}, File: {file}")




