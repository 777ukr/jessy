#!/usr/bin/env python3
"""
Gate.io Coin Parser
Автоматическое добавление новых монет из Gate.io для бэктестов
"""

import os
import json
import requests
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

# Configuration
FREQTRADE_DIR = Path(__file__).parent
CONFIG_FILE = FREQTRADE_DIR.parent / "config" / "freqtrade_config.json"
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


class GateioCoinParser:
    """Парсер монет с Gate.io"""
    
    def __init__(self):
        self.session = requests.Session()
        
        # Проверяем наличие API ключей
        self.api_key = GATEIO_API_KEY
        self.secret_key = GATEIO_SECRET_KEY
        
        if self.api_key and self.secret_key:
            print(f"✅ API ключи Gate.io найдены (из {'env' if os.getenv('GATEIO_API_KEY') else 'конфига'})")
        else:
            print("⚠️  API ключи Gate.io не найдены (работаем в публичном режиме)")
    
    def get_all_usdt_pairs(self) -> List[Dict]:
        """Получить все USDT пары с Gate.io"""
        try:
            url = f"{GATEIO_API_BASE}/spot/currency_pairs"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            all_pairs = response.json()
            
            # Фильтруем только USDT пары с достаточной ликвидностью
            usdt_pairs = []
            for pair in all_pairs:
                if (pair["id"].endswith("_USDT") and 
                    pair["trade_status"] == "tradable" and
                    pair.get("min_quote_amount", 0) > 0):
                    
                    # Конвертируем в формат Freqtrade
                    freq_pair = pair["id"].replace("_", "/")
                    usdt_pairs.append({
                        "pair": freq_pair,
                        "gate_pair": pair["id"],
                        "base": pair["base"],
                        "quote": pair["quote"],
                        "min_quote_amount": pair.get("min_quote_amount", 0),
                        "fee": pair.get("fee", "0.2%"),
                        "trade_status": pair.get("trade_status", "tradable")
                    })
            
            print(f"✅ Найдено {len(usdt_pairs)} USDT пар")
            return sorted(usdt_pairs, key=lambda x: x["pair"])
            
        except Exception as e:
            print(f"❌ Ошибка при получении пар: {e}")
            return []
    
    def get_pair_24h_stats(self, pair: str) -> Optional[Dict]:
        """Получить 24ч статистику для пары"""
        try:
            gate_pair = pair.replace("/", "_")
            url = f"{GATEIO_API_BASE}/spot/tickers"
            params = {"currency_pair": gate_pair}
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            tickers = response.json()
            if tickers:
                ticker = tickers[0]
                return {
                    "volume_24h": float(ticker.get("base_volume", 0)),
                    "quote_volume_24h": float(ticker.get("quote_volume", 0)),
                    "high_24h": float(ticker.get("high_24h", 0)),
                    "low_24h": float(ticker.get("low_24h", 0)),
                    "last_price": float(ticker.get("last", 0)),
                    "change_24h": float(ticker.get("change_percentage", 0))
                }
            
        except Exception as e:
            print(f"⚠️  Ошибка при получении статистики для {pair}: {e}")
        
        return None
    
    def filter_by_volume(self, pairs: List[Dict], min_volume_usdt: float = 100000) -> List[Dict]:
        """Фильтровать пары по минимальному объему"""
        filtered = []
        
        print(f"🔍 Фильтрация пар по объему >= ${min_volume_usdt:,.0f}...")
        
        for pair_info in pairs:
            stats = self.get_pair_24h_stats(pair_info["pair"])
            if stats and isinstance(stats.get("quote_volume_24h"), (int, float)):
                volume = float(stats["quote_volume_24h"])
                if volume >= min_volume_usdt:
                    pair_info["stats_24h"] = stats
                    filtered.append(pair_info)
            
            # Rate limit
            import time
            time.sleep(0.1)
        
        print(f"✅ Отфильтровано {len(filtered)} пар с достаточным объемом")
        return filtered
    
    def get_top_pairs_by_volume(self, limit: int = 50) -> List[Dict]:
        """Получить топ-пары по объему"""
        all_pairs = self.get_all_usdt_pairs()
        
        # Получаем статистику для всех пар
        pairs_with_stats = []
        for pair_info in all_pairs:
            stats = self.get_pair_24h_stats(pair_info["pair"])
            if stats:
                pair_info["stats_24h"] = stats
                pairs_with_stats.append(pair_info)
            
            import time
            time.sleep(0.1)
        
        # Сортируем по объему (исправлено: проверяем тип)
        pairs_with_stats.sort(
            key=lambda x: float(x.get("stats_24h", {}).get("quote_volume_24h", 0) or 0),
            reverse=True
        )
        
        return pairs_with_stats[:limit]
    
    def save_pairs_to_config(self, pairs: List[str], config_path: Path = CONFIG_FILE):
        """Сохранить пары в конфиг Freqtrade"""
        if not config_path.exists():
            print(f"❌ Конфиг не найден: {config_path}")
            return
        
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Обновляем whitelist
            existing_pairs = set(config.get("exchange", {}).get("pair_whitelist", []))
            new_pairs = set(pairs)
            
            # Объединяем
            all_pairs = sorted(list(existing_pairs | new_pairs))
            config.setdefault("exchange", {})["pair_whitelist"] = all_pairs
            
            # Сохраняем
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            print(f"✅ Сохранено {len(all_pairs)} пар в конфиг (добавлено {len(new_pairs - existing_pairs)} новых)")
            
        except Exception as e:
            print(f"❌ Ошибка при сохранении конфига: {e}")


def main():
    """Main entry point"""
    parser = GateioCoinParser()
    
    # Получаем топ-50 пар по объему
    print("📊 Получение топ-пар по объему...")
    top_pairs = parser.get_top_pairs_by_volume(limit=50)
    
    # Выводим результаты
    print("\n🏆 Топ-10 пар по объему:")
    for i, pair_info in enumerate(top_pairs[:10], 1):
        stats = pair_info.get("stats_24h", {})
        volume = stats.get("quote_volume_24h", 0)
        change = stats.get("change_24h", 0)
        print(f"{i:2d}. {pair_info['pair']:15s} | Объем: ${volume:>12,.0f} | Изменение: {change:>6.2f}%")
    
    # Сохраняем в конфиг
    pairs_list = [p["pair"] for p in top_pairs]
    parser.save_pairs_to_config(pairs_list)
    
    print("\n✅ Парсинг завершен!")


if __name__ == "__main__":
    main()

