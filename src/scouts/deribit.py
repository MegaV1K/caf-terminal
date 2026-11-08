"""
Deribit Public API Scout for CAF-Terminal.

Connects to Deribit v2 Public REST API (no authentication required) to gather:
- Live options book summary (Open Interest, Volume, Bid/Ask, Mark IV).
- Index prices (ETH/USD, BTC/USD).
- Historical volatility.
- Institutional Open Interest (OI) Pinning Clusters and Break-Even Zones.
"""

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

from config import CACHE_DIR, DERIBIT_BASE_URL, DERIBIT_CACHE_TTL
from src.risk.derivatives_risk import DerivativesRiskEngine


class DeribitScout:
    """Scout for gathering options, open interest, and volatility from Deribit Public API."""

    def __init__(self, cache_ttl: int = DERIBIT_CACHE_TTL):
        self.cache_ttl = cache_ttl
        self.cache_dir = CACHE_DIR
        self.base_url = DERIBIT_BASE_URL
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "CAF-Terminal/1.0",
        }

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

    def get_index_price(self, currency: str = "ETH") -> float:
        """Fetches live underlying index price in USD (e.g. eth_usd, btc_usd)."""
        idx_name = f"{currency.lower()}_usd"
        url = f"{self.base_url}/public/get_index_price"
        try:
            res = requests.get(url, headers=self.headers, params={"index_name": idx_name}, timeout=10)
            res.raise_for_status()
            data = res.json()
            return float(data.get("result", {}).get("index_price", 0.0))
        except Exception as e:
            print(f"[Warning] Failed to fetch Deribit index price for {idx_name}: {e}")
            return 0.0

    def get_historical_volatility(self, currency: str = "ETH") -> float:
        """Fetches current annualized historical volatility percentage."""
        url = f"{self.base_url}/public/get_historical_volatility"
        try:
            res = requests.get(url, headers=self.headers, params={"currency": currency.upper()}, timeout=10)
            res.raise_for_status()
            data = res.json().get("result", [])
            if data and isinstance(data, list) and len(data[-1]) >= 2:
                return round(float(data[-1][1]), 2)
            return 0.0
        except Exception as e:
            print(f"[Warning] Failed to fetch Deribit historical volatility for {currency}: {e}")
            return 0.0

    def fetch_book_summary(
        self,
        currency: str = "ETH",
        kind: str = "option",
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Fetches full options market summary by currency.
        Contains open_interest, mark_price, mark_iv, volume, bid_price, ask_price.
        """
        currency_upper = currency.upper()
        cache_file = self.cache_dir / f"deribit_{currency_upper.lower()}_{kind}_summary.json"
        if not force_refresh:
            cached = self._get_cached(cache_file)
            if cached:
                return cached

        url = f"{self.base_url}/public/get_book_summary_by_currency"
        params = {"currency": currency_upper, "kind": kind}
        try:
            res = requests.get(url, headers=self.headers, params=params, timeout=15)
            res.raise_for_status()
            data = res.json().get("result", [])
            if isinstance(data, list) and data:
                self._save_cache(cache_file, data)
                return data
            return []
        except Exception as e:
            print(f"[Warning] Failed to fetch Deribit book summary for {currency_upper}: {e}")
            cached = self._get_cached(cache_file)
            return cached or []

    def get_top_oi_clusters(
        self,
        currency: str = "ETH",
        min_oi: float = 500.0,
        top_n: int = 15,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Parses live book summary to locate the largest Open Interest clusters,
        computes break-even pinning boundaries, and determines market-maker delta-hedging flows.
        """
        currency_upper = currency.upper()
        summary = self.fetch_book_summary(currency=currency_upper, kind="option", force_refresh=force_refresh)
        if not summary:
            return []

        index_price = self.get_index_price(currency=currency_upper) or (
            summary[0].get("underlying_price") or 0.0
        )

        parsed_clusters = []
        # Pattern e.g.: ETH-27DEC24-2600-C or BTC-25OCT24-65000-P
        pattern = re.compile(rf"^{currency_upper}-([A-Z0-9]+)-(\d+)-([CP])$")

        for item in summary:
            inst = item.get("instrument_name", "")
            match = pattern.match(inst)
            if not match:
                continue

            expiry, strike_str, opt_type_code = match.groups()
            strike = float(strike_str)
            opt_type = "CALL" if opt_type_code == "C" else "PUT"
            oi = float(item.get("open_interest") or 0.0)

            if oi < min_oi:
                continue

            # Mark price on Deribit is in base currency (e.g. 0.05 ETH). Convert to USD.
            mark_price_base = float(item.get("mark_price") or 0.0)
            premium_usd = mark_price_base * index_price if index_price > 0 else 0.0

            bid = float(item.get("bid_price") or 0.0) * index_price if index_price > 0 else 0.0
            ask = float(item.get("ask_price") or 0.0) * index_price if index_price > 0 else 0.0
            vol_usd = float(item.get("volume_usd") or (float(item.get("volume") or 0.0) * index_price))

            parsed_clusters.append({
                "instrument": inst,
                "asset": currency_upper,
                "expiry": expiry,
                "strike": strike,
                "type": opt_type,
                "open_interest": oi,
                "premium": round(premium_usd, 2),
                "premium_base": mark_price_base,
                "mark_iv": float(item.get("mark_iv") or 0.0),
                "volume_usd": round(vol_usd, 2),
                "bid_usd": round(bid, 2),
                "ask_usd": round(ask, 2),
                "underlying_price": round(index_price, 2),
            })

        # Sort by Open Interest descending
        parsed_clusters.sort(key=lambda x: x["open_interest"], reverse=True)
        top_clusters = parsed_clusters[:top_n]

        # Calculate pinning and forced delta hedging flows via DerivativesRiskEngine
        zones = DerivativesRiskEngine.calculate_oi_pinning_zones(top_clusters)

        # Merge zone analytics back into cluster data
        for c, z in zip(top_clusters, zones):
            c["break_even_pinning_level"] = z["break_even_pinning_level"]
            c["forced_market_maker_flow"] = z["forced_market_maker_flow"]
            c["expected_market_reaction"] = z["expected_market_reaction"]
            c["is_institutional_wall"] = z["is_institutional_wall"]

        return top_clusters

    def analyze_options_market(
        self,
        currency: str = "ETH",
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Produces a high-level options market intelligence summary for a currency."""
        currency_upper = currency.upper()
        summary = self.fetch_book_summary(currency=currency_upper, kind="option", force_refresh=force_refresh)
        index_price = self.get_index_price(currency=currency_upper)
        hist_vol = self.get_historical_volatility(currency=currency_upper)

        if not summary:
            return {"empty": True, "currency": currency_upper}

        total_oi_base = sum(float(x.get("open_interest") or 0.0) for x in summary)
        total_vol_usd = sum(float(x.get("volume_usd") or 0.0) for x in summary)

        call_oi = sum(float(x.get("open_interest") or 0.0) for x in summary if x.get("instrument_name", "").endswith("-C"))
        put_oi = sum(float(x.get("open_interest") or 0.0) for x in summary if x.get("instrument_name", "").endswith("-P"))
        pc_ratio = round(put_oi / call_oi, 2) if call_oi > 0 else 1.0

        top_clusters = self.get_top_oi_clusters(
            currency=currency_upper,
            min_oi=100.0,
            top_n=8,
            force_refresh=force_refresh,
        )

        iv_values = [float(x.get("mark_iv") or 0.0) for x in summary if float(x.get("mark_iv") or 0.0) > 0]
        avg_iv = round(sum(iv_values) / len(iv_values), 1) if iv_values else 0.0

        return {
            "empty": False,
            "currency": currency_upper,
            "index_price": round(index_price, 2),
            "historical_volatility_pct": hist_vol,
            "average_mark_iv_pct": avg_iv,
            "total_open_interest_coins": round(total_oi_base, 1),
            "total_open_interest_usd": round(total_oi_base * index_price, 2),
            "total_24h_volume_usd": round(total_vol_usd, 2),
            "call_open_interest": round(call_oi, 1),
            "put_open_interest": round(put_oi, 1),
            "put_call_ratio": pc_ratio,
            "sentiment": (
                "BULLISH_SKEW (Low Put/Call Ratio)"
                if pc_ratio < 0.65
                else ("BEARISH_HEDGE_HEAVY (High Put/Call Ratio)" if pc_ratio > 1.0 else "BALANCED / NEUTRAL")
            ),
            "top_pinning_clusters": top_clusters,
        }
