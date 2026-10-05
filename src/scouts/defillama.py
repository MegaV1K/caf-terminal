import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from config import CACHE_DIR, CACHE_TTL, DEFILLAMA_PROTOCOLS_URL, DEFILLAMA_FEES_URL


class DefiLlamaScout:
    """Scout for gathering on-chain protocol data from DefiLlama."""

    def __init__(self, cache_ttl: int = CACHE_TTL):
        self.cache_ttl = cache_ttl
        self.cache_dir = CACHE_DIR
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

    def fetch_protocols(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch all protocols with TVL, category, chains, mcap, and change rates."""
        cache_file = self.cache_dir / "defillama_protocols.json"
        if not force_refresh:
            cached = self._get_cached(cache_file)
            if cached:
                return cached

        print("[Scout] Fetching protocols from DefiLlama...")
        try:
            res = requests.get(DEFILLAMA_PROTOCOLS_URL, headers=self.headers, timeout=20)
            res.raise_for_status()
            data = res.json()
            if isinstance(data, list):
                self._save_cache(cache_file, data)
                return data
        except Exception as e:
            print(f"[Error] DefiLlama fetch_protocols failed: {e}")
            cached = self._get_cached(cache_file)
            if cached:
                print("[Info] Returning stale cached data.")
                return cached
        return []

    def fetch_fees_and_revenue(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch 24h/7d/30d fees and revenue per protocol."""
        cache_file = self.cache_dir / "defillama_fees.json"
        if not force_refresh:
            cached = self._get_cached(cache_file)
            if cached:
                return cached

        print("[Scout] Fetching fees and revenue from DefiLlama...")
        try:
            url = f"{DEFILLAMA_FEES_URL}?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true"
            res = requests.get(url, headers=self.headers, timeout=20)
            res.raise_for_status()
            data = res.json()
            self._save_cache(cache_file, data)
            return data
        except Exception as e:
            print(f"[Error] DefiLlama fetch_fees failed: {e}")
            cached = self._get_cached(cache_file)
            if cached:
                return cached
        return {}

    def get_emerging_candidates(
        self,
        min_tvl: float = 1_000_000,
        max_mcap: float = 800_000_000,
        min_change_7d: float = 5.0,
    ) -> List[Dict[str, Any]]:
        """
        Filters candidates showing strong on-chain momentum (Emerging / Incubator):
        - Significant TVL or growth
        - TVL > min_tvl ($1M+)
        - Market Cap under max_mcap ($800M) to capture outside top 100/200
        - 7-day TVL momentum > +5%
        """
        protocols = self.fetch_protocols()
        fees_data = self.fetch_fees_and_revenue()
        
        # Build lookup for fees using stable defillamaId as primary key,
        # with fallback to lowercase name for protocols missing the ID.
        fees_by_id:   Dict[str, Any] = {}
        fees_by_name: Dict[str, Any] = {}
        for p in fees_data.get("protocols", []):
            did = p.get("defillamaId")
            if did:
                fees_by_id[str(did)] = p
            name_lc = (p.get("name") or "").lower()
            if name_lc:
                fees_by_name[name_lc] = p
            # Also index by module slug if present
            if p.get("module"):
                fees_by_name[p["module"].lower()] = p

        candidates = []
        for p in protocols:
            tvl    = p.get("tvl") or 0
            mcap   = p.get("mcap") or 0
            change_7d = p.get("change_7d") or 0
            change_1m = p.get("change_1m") or 0

            if tvl < min_tvl:
                continue

            # v2 MCap filter fix:
            # - If MCap is known and too large → skip
            # - If MCap unknown (0) but TVL very large → probably a giant with missing data → skip
            if mcap > 0 and mcap > max_mcap:
                continue
            if mcap == 0 and tvl > 50_000_000:
                continue

            if change_7d < min_change_7d and change_1m < min_change_7d:
                continue

            # Resolve fees: try defillamaId first (stable), then name fallback
            proto_id   = str(p.get("id") or "")
            name_lower = (p.get("name") or "").lower()
            fee_info   = (
                fees_by_id.get(proto_id)
                or fees_by_name.get(name_lower)
                or {}
            )

            # Mcap / TVL ratio (lower means fundamentally cheaper protocol TVL)
            mcap_tvl_ratio = round(mcap / tvl, 2) if tvl > 0 and mcap > 0 else None

            candidates.append({
                "id":           p.get("id"),
                "name":         p.get("name"),
                "symbol":       (p.get("symbol") or "").upper(),
                "category":     p.get("category", "Uncategorized"),
                "chains":       p.get("chains", []),
                "tvl":          tvl,
                "change_1d":    round(p.get("change_1d") or 0, 2),
                "change_7d":    round(change_7d, 2),
                "change_1m":    round(change_1m, 2),
                "mcap":         mcap if mcap > 0 else None,
                "mcap_tvl_ratio": mcap_tvl_ratio,
                "daily_fees":   fee_info.get("total24h"),
                "daily_revenue": fee_info.get("totalRevenue24h"),
                "url":          p.get("url"),
                "gecko_id":     p.get("gecko_id"),
            })

        # Sort by 7-day TVL growth descending
        candidates.sort(key=lambda x: (x["change_7d"] or 0), reverse=True)
        return candidates
