import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from config import CACHE_DIR, CACHE_TTL, COINGECKO_BASE_URL, COINGECKO_API_KEY


class CoinGeckoScout:
    """Scout for gathering token market metrics, FDV, volume, and rank from CoinGecko."""

    def __init__(self, cache_ttl: int = CACHE_TTL):
        self.cache_ttl = cache_ttl
        self.cache_dir = CACHE_DIR
        self.api_key = COINGECKO_API_KEY
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "CAF-Terminal/1.0",
        }
        if self.api_key:
            self.headers["x-cg-demo-api-key"] = self.api_key

    def _get_cached(self, cache_file: Path) -> Optional[Any]:
        if cache_file.exists():
            mtime = cache_file.stat().st_mtime
            if time.time() - mtime < self.cache_ttl:
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
        return None

    def _save_cache(self, cache_file: Path, data: Any) -> None:
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            print(f"[Warning] Failed to save cache {cache_file}: {e}")

    def fetch_markets(
        self,
        pages: int = 3,
        per_page: int = 100,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Fetch top coins (default 3 pages = Top 300).
        Includes market_cap, fully_diluted_valuation, total_volume, price_change_percentage_24h, 7d, etc.
        """
        cache_file = self.cache_dir / f"coingecko_markets_top_{pages * per_page}.json"
        if not force_refresh:
            cached = self._get_cached(cache_file)
            if cached:
                return cached

        print(f"[Scout] Fetching {pages * per_page} tokens from CoinGecko...")
        all_coins = []

        for page in range(1, pages + 1):
            url = f"{COINGECKO_BASE_URL}/coins/markets"
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": per_page,
                "page": page,
                "sparkline": "false",
                "price_change_percentage": "24h,7d,30d",
            }
            try:
                res = requests.get(url, headers=self.headers, params=params, timeout=15)
                if res.status_code == 429:
                    print("[Warning] CoinGecko rate limit hit. Waiting 10 seconds...")
                    time.sleep(10)
                    res = requests.get(url, headers=self.headers, params=params, timeout=15)
                res.raise_for_status()
                coins = res.json()
                if isinstance(coins, list):
                    all_coins.extend(coins)
                time.sleep(1.2)  # Respect free rate limits
            except Exception as e:
                print(f"[Error] Failed to fetch CoinGecko page {page}: {e}")
                break

        if all_coins:
            self._save_cache(cache_file, all_coins)
            return all_coins

        # Fallback to cache if request failed
        cached = self._get_cached(cache_file)
        if cached:
            return cached
        return []

    def get_token_metrics(self, markets: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Map tokens by symbol and id for easy scoring lookup."""
        result = {}
        for coin in markets:
            symbol = coin.get("symbol", "").upper()
            coin_id = coin.get("id", "").lower()
            mcap = coin.get("market_cap") or 0
            fdv = coin.get("fully_diluted_valuation") or 0
            vol = coin.get("total_volume") or 0

            # Dilution risk ratio: FDV / Market Cap
            fdv_mcap_ratio = round(fdv / mcap, 2) if mcap > 0 and fdv > 0 else 1.0

            # Liquidity / turnover ratio: Volume / Market Cap
            vol_mcap_ratio = round(vol / mcap, 3) if mcap > 0 else 0.0

            item = {
                "id": coin_id,
                "symbol": symbol,
                "name": coin.get("name"),
                "rank": coin.get("market_cap_rank"),
                "price": coin.get("current_price"),
                "mcap": mcap,
                "fdv": fdv,
                "fdv_mcap_ratio": fdv_mcap_ratio,
                "volume_24h": vol,
                "vol_mcap_ratio": vol_mcap_ratio,
                "change_24h": coin.get("price_change_percentage_24h_in_currency"),
                "change_7d": coin.get("price_change_percentage_7d_in_currency"),
                "change_30d": coin.get("price_change_percentage_30d_in_currency"),
            }
            result[symbol] = item
            result[coin_id] = item
        return result

    def fetch_trending(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetches trending coins from CoinGecko /search/trending.
        Identifies early narrative shifts, new listings, and sudden attention.
        """
        cache_file = self.cache_dir / "coingecko_trending.json"
        if not force_refresh:
            cached = self._get_cached(cache_file)
            if cached:
                return cached

        print("[CoinGecko] Получение трендовых монет (/search/trending)...")
        try:
            url = f"{COINGECKO_BASE_URL}/search/trending"
            res = requests.get(url, headers=self.headers, timeout=15)
            res.raise_for_status()
            data = res.json()
            coins_raw = data.get("coins", [])
            trending = []
            for entry in coins_raw:
                item = entry.get("item", {})
                trending.append({
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "symbol": (item.get("symbol") or "").upper(),
                    "rank": item.get("market_cap_rank"),
                    "score": item.get("score"),  # 0 is top trending
                })
            self._save_cache(cache_file, trending)
            return trending
        except Exception as e:
            print(f"[Error] Ошибка получения трендов CoinGecko: {e}")
            cached = self._get_cached(cache_file)
            if cached:
                return cached
            return []

    def get_volume_anomalies(
        self,
        markets: Optional[List[Dict[str, Any]]] = None,
        min_vol_mcap_ratio: float = 0.30,  # 30%+ turnover
        max_mcap: float = 300_000_000,
        min_vol: float = 1_000_000,
    ) -> List[Dict[str, Any]]:
        """
        Finds tokens with abnormal trading volume momentum outside giant caps.
        Sign: Smart money accumulation or sudden narrative awakening.
        """
        if markets is None:
            markets = self.fetch_markets()

        anomalies = []
        for coin in markets:
            mcap = coin.get("market_cap") or 0
            vol = coin.get("total_volume") or 0
            change_7d = coin.get("price_change_percentage_7d_in_currency") or 0

            if vol < min_vol:
                continue
            if mcap > max_mcap or mcap == 0:
                continue

            ratio = vol / mcap
            if ratio >= min_vol_mcap_ratio:
                anomalies.append({
                    "id": coin.get("id"),
                    "name": coin.get("name"),
                    "symbol": (coin.get("symbol") or "").upper(),
                    "rank": coin.get("market_cap_rank"),
                    "mcap": mcap,
                    "volume_24h": vol,
                    "vol_mcap_ratio": round(ratio, 2),
                    "change_7d": round(change_7d, 2),
                    "fdv_mcap_ratio": round((coin.get("fully_diluted_valuation") or mcap) / mcap, 2),
                })

        anomalies.sort(key=lambda x: x["vol_mcap_ratio"], reverse=True)
        return anomalies
