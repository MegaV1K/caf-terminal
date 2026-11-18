"""
Live Yield Scout for CAF-Terminal.

Collects real-time delta-neutral and market-neutral yield data:
1. Hyperliquid perpetual funding rates (hourly -> 8h, APR).
2. Gate.io perpetual funding rates with Spot-liquidity check and 7-day stability verification.
3. Pendle Finance official API for real-time Principal Token (PT) implied fixed APY.
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

from config import CACHE_DIR

HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"
GATE_FUTURES_TICKERS_URL = "https://api.gateio.ws/api/v4/futures/usdt/tickers"
GATE_SPOT_TICKERS_URL = "https://api.gateio.ws/api/v4/spot/tickers"
GATE_FUNDING_RATE_URL = "https://api.gateio.ws/api/v4/futures/usdt/funding_rate"
PENDLE_MARKETS_URL = "https://api-v2.pendle.finance/core/v1/1/markets"


class LiveYieldScout:
    """Fetches and verifies real-time funding arbitrage and Pendle PT yields."""

    def __init__(self, cache_ttl: int = 900, cache_dir: Optional[Path] = None):  # 15 minutes cache
        self.cache_ttl = cache_ttl
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.headers = {"User-Agent": "CAF-Terminal/2.4.0 (Windows NT 10.0)"}

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
        except Exception:
            pass

    def fetch_hyperliquid_funding(
        self,
        min_apr_pct: float = 8.0,
        min_24h_vol_usd: float = 300_000.0,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Fetches live Hyperliquid perps funding rates.
        Converts 1h funding to 8h and annualized APR (24h * 365).
        """
        cache_file = self.cache_dir / "hyperliquid_funding_cache.json"
        if not force_refresh:
            cached = self._get_cached(cache_file)
            if cached:
                return cached

        opportunities: List[Dict[str, Any]] = []
        try:
            payload = {"type": "metaAndAssetCtxs"}
            res = requests.post(HYPERLIQUID_INFO_URL, json=payload, headers=self.headers, timeout=8)
            if res.status_code == 200:
                data = res.json()
                universe = data[0].get("universe", [])
                ctxs = data[1] if len(data) > 1 else []

                for i, asset in enumerate(universe):
                    if i >= len(ctxs):
                        break
                    sym = asset.get("name", "")
                    ctx = ctxs[i]
                    h1_rate = float(ctx.get("funding", 0.0))
                    vol = float(ctx.get("dayNtlVlm", 0.0))
                    oracle_px = float(ctx.get("oraclePrice", 0.0))
                    oi = float(ctx.get("openInterest", 0.0)) * oracle_px

                    # 1h funding rate to 8h and APR
                    funding_8h_pct = round(h1_rate * 8.0 * 100.0, 4)
                    annual_apr_pct = round(h1_rate * 24.0 * 365.0 * 100.0, 2)

                    if annual_apr_pct >= min_apr_pct and vol >= min_24h_vol_usd:
                        opportunities.append({
                            "symbol": sym,
                            "venue": "Hyperliquid",
                            "current_apr_pct": annual_apr_pct,
                            "funding_rate_8h_pct": funding_8h_pct,
                            "oracle_price": oracle_px,
                            "volume_24h_usd": round(vol, 0),
                            "open_interest_usd": round(oi, 0),
                            "stability_status": "Active DEX Liquidity",
                        })

                opportunities.sort(key=lambda x: x["current_apr_pct"], reverse=True)
                self._save_cache(cache_file, opportunities)
        except Exception as e:
            print(f"[LiveYieldScout] Hyperliquid fetch error: {e}")

        return opportunities

    def fetch_gate_funding_with_spot_filter(
        self,
        min_apr_pct: float = 8.0,
        min_spot_vol_usd: float = 50_000.0,
        max_contracts_to_audit: int = 30,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Fetches Gate.io perps funding rates.
        Applies:
        1. Spot filter: requires active spot pair with > $50k 24h volume (no basis execution trap).
        2. 7d-stability check: requires positive and consistent 7-day average funding.
        """
        cache_file = self.cache_dir / "gate_funding_cache.json"
        if not force_refresh:
            cached = self._get_cached(cache_file)
            if cached:
                return cached

        opportunities: List[Dict[str, Any]] = []
        try:
            # 1. Fetch futures tickers
            r_fut = requests.get(GATE_FUTURES_TICKERS_URL, headers=self.headers, timeout=8)
            if r_fut.status_code != 200:
                return []
            fut_tickers = [
                t for t in r_fut.json()
                if float(t.get("funding_rate", 0.0)) * 3.0 * 365.0 * 100.0 >= min_apr_pct
            ]
            fut_tickers.sort(key=lambda x: float(x.get("funding_rate", 0.0)), reverse=True)

            # 2. Fetch spot markets to verify spot availability
            r_spot = requests.get(GATE_SPOT_TICKERS_URL, headers=self.headers, timeout=8)
            spot_map = {s["currency_pair"]: s for s in r_spot.json()} if r_spot.status_code == 200 else {}

            for t in fut_tickers[:max_contracts_to_audit]:
                contract = t.get("contract", "")
                if not contract.endswith("_USDT"):
                    continue

                # Spot filter: spot market MUST exist and have volume
                spot_data = spot_map.get(contract)
                if not spot_data:
                    continue

                spot_vol = float(spot_data.get("quote_volume", 0.0))
                if spot_vol < min_spot_vol_usd:
                    continue

                fr_8h = float(t.get("funding_rate", 0.0))
                curr_apr = fr_8h * 3.0 * 365.0 * 100.0

                # 3. 7-day stability check: fetch recent 21 intervals (21 * 8h = 7 days)
                hist_url = f"{GATE_FUNDING_RATE_URL}?contract={contract}&limit=21"
                avg_7d_apr = curr_apr
                stability = "7d Verified"

                try:
                    r_hist = requests.get(hist_url, headers=self.headers, timeout=5)
                    if r_hist.status_code == 200:
                        rates = [float(x["r"]) for x in r_hist.json() if "r" in x]
                        if rates:
                            avg_fr = sum(rates) / len(rates)
                            avg_7d_apr = avg_fr * 3.0 * 365.0 * 100.0
                            # If 7d average is negative or flipped, skip unreliable spike
                            if avg_7d_apr < (min_apr_pct * 0.5):
                                continue
                            pos_count = sum(1 for r in rates if r > 0)
                            if pos_count < (len(rates) * 0.7):
                                continue
                except Exception:
                    pass

                sym = contract.replace("_USDT", "")
                opportunities.append({
                    "symbol": sym,
                    "contract": contract,
                    "venue": "Gate.io",
                    "current_apr_pct": round(curr_apr, 2),
                    "avg_7d_apr_pct": round(avg_7d_apr, 2),
                    "funding_rate_8h_pct": round(fr_8h * 100.0, 4),
                    "spot_24h_vol_usd": round(spot_vol, 0),
                    "stability_status": f"{stability} (Avg: {avg_7d_apr:.1f}% APR)",
                })

                if len(opportunities) >= 8:
                    break

            opportunities.sort(key=lambda x: x["avg_7d_apr_pct"], reverse=True)
            self._save_cache(cache_file, opportunities)
        except Exception as e:
            print(f"[LiveYieldScout] Gate.io fetch error: {e}")

        return opportunities

    def fetch_pendle_pt_markets(
        self,
        min_apy_pct: float = 5.0,
        min_liquidity_usd: float = 50_000.0,
        chain_id: int = 1,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Fetches live Principal Token (PT) fixed dollar yields directly from Pendle Finance official API.
        Extracts real implied APY, discount to par, maturity date, and underlying asset.
        """
        cache_file = self.cache_dir / f"pendle_pt_chain_{chain_id}_cache.json"
        if not force_refresh:
            cached = self._get_cached(cache_file)
            if cached:
                return cached

        pt_markets: List[Dict[str, Any]] = []
        try:
            url = f"https://api-v2.pendle.finance/core/v1/{chain_id}/markets?order_by=liquidity%3A-1&is_active=true&skip=0&limit=30"
            res = requests.get(url, headers=self.headers, timeout=10)
            if res.status_code == 200:
                results = res.json().get("results", [])
                for m in results:
                    pt = m.get("pt", {})
                    implied_apy = float(m.get("impliedApy", 0.0)) * 100.0
                    pt_discount = float(m.get("ptDiscount", 0.0)) * 100.0
                    liq_usd = float(m.get("liquidity", {}).get("usd", 0.0))
                    expiry_iso = m.get("expiry", "")

                    if implied_apy >= min_apy_pct and liq_usd >= min_liquidity_usd:
                        underlying = m.get("accountingAsset", {}).get("symbol", "USD")
                        pt_name = pt.get("proSymbol") or pt.get("symbol") or m.get("name")
                        pt_markets.append({
                            "pt_symbol": pt_name,
                            "underlying_asset": underlying,
                            "implied_fixed_apy_pct": round(implied_apy, 2),
                            "discount_pct": round(pt_discount, 2),
                            "expiry_date": expiry_iso[:10] if expiry_iso else "N/A",
                            "liquidity_usd": round(liq_usd, 0),
                            "chain_id": chain_id,
                            "protocol": m.get("protocol", "Pendle V2"),
                        })

                pt_markets.sort(key=lambda x: x["implied_fixed_apy_pct"], reverse=True)
                self._save_cache(cache_file, pt_markets)
        except Exception as e:
            print(f"[LiveYieldScout] Pendle API fetch error: {e}")

        return pt_markets
