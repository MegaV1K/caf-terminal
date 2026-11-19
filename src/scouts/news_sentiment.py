"""
News & Sentiment Scout for CAF-Terminal.

Integrates:
1. CryptoPanic Developer API (curated news, sentiment votes: bullish, bearish, important).
2. Alternative.me Fear & Greed Index (open macro sentiment barometer).
3. Open RSS Breaking News stream (failsafe fallback for zero-cost operation).
4. Master kill-switch via CRYPTOPANIC_ENABLED in config.
"""

import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

from config import (
    CACHE_DIR,
    CRYPTOPANIC_API_KEY,
    CRYPTOPANIC_BASE_URL,
    CRYPTOPANIC_ENABLED,
)

FEAR_AND_GREED_URL = "https://api.alternative.me/fng/?limit=7"
OPEN_RSS_URL = "https://cointelegraph.com/rss"


class NewsSentimentScout:
    """Scout for gathering real-time crypto news, community sentiment, and panic indicators."""

    def __init__(self, cache_ttl: int = 900, cache_dir: Optional[Path] = None):
        self.cache_ttl = cache_ttl
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = CRYPTOPANIC_API_KEY
        self.enabled = CRYPTOPANIC_ENABLED
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

    def fetch_fear_and_greed_index(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetches macro market sentiment via Alternative.me Fear & Greed Index."""
        cache_file = self.cache_dir / "fear_and_greed_cache.json"
        if not force_refresh:
            cached = self._get_cached(cache_file)
            if cached:
                return cached

        default_res = {
            "value": 50,
            "classification": "Neutral",
            "historical_7d_avg": 50.0,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        try:
            res = requests.get(FEAR_AND_GREED_URL, headers=self.headers, timeout=6)
            if res.status_code == 200:
                data = res.json().get("data", [])
                if data:
                    current_val = int(data[0].get("value", 50))
                    current_cls = data[0].get("value_classification", "Neutral")
                    vals = [int(d.get("value", 50)) for d in data if "value" in d]
                    avg_7d = round(sum(vals) / len(vals), 1) if vals else float(current_val)

                    result = {
                        "value": current_val,
                        "classification": current_cls,
                        "historical_7d_avg": avg_7d,
                        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    }
                    self._save_cache(cache_file, result)
                    return result
        except Exception as e:
            print(f"[NewsSentimentScout] Fear & Greed fetch notice: {e}")

        return default_res

    def fetch_cryptopanic_posts(
        self,
        currencies: Optional[List[str]] = None,
        filter_type: str = "important",
        limit: int = 15,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        Fetches curated news from CryptoPanic API if auth token is configured.
        Falls back gracefully if token is missing, invalid, or blocked.
        """
        if not self.enabled:
            return {"status": "disabled", "posts": [], "reason": "CRYPTOPANIC_ENABLED=false"}

        cache_key = f"cryptopanic_{filter_type}_{limit}.json"
        cache_file = self.cache_dir / cache_key
        if not force_refresh:
            cached = self._get_cached(cache_file)
            if cached:
                return cached

        if not self.api_key:
            return {
                "status": "unauthenticated",
                "posts": [],
                "reason": "CRYPTOPANIC_API_KEY is not set in environment or .env",
            }

        params = {
            "auth_token": self.api_key,
            "public": "true",
            "filter": filter_type,
        }
        if currencies:
            params["currencies"] = ",".join(c.upper() for c in currencies)

        try:
            res = requests.get(CRYPTOPANIC_BASE_URL, headers=self.headers, params=params, timeout=8)
            if res.status_code == 200:
                results = res.json().get("results", [])
                posts = []
                for p in results[:limit]:
                    votes = p.get("votes", {})
                    curr_list = [c.get("code") for c in p.get("currencies", []) if c.get("code")]
                    posts.append({
                        "id": p.get("id"),
                        "title": p.get("title", ""),
                        "url": p.get("url", ""),
                        "domain": p.get("domain", ""),
                        "published_at": p.get("published_at", "")[:16],
                        "currencies": curr_list,
                        "votes_positive": votes.get("positive", 0),
                        "votes_negative": votes.get("negative", 0),
                        "votes_important": votes.get("important", 0),
                    })

                output = {"status": "ok", "posts": posts, "source": "CryptoPanic API"}
                self._save_cache(cache_file, output)
                return output
            elif res.status_code in (401, 403):
                return {
                    "status": "error",
                    "code": res.status_code,
                    "posts": [],
                    "reason": "CryptoPanic API authentication required or rate limit hit.",
                }
        except Exception as e:
            return {"status": "error", "posts": [], "reason": str(e)}

        return {"status": "empty", "posts": []}

    def fetch_rss_breaking_news(
        self,
        portfolio_symbols: Optional[List[str]] = None,
        limit: int = 10,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Open failsafe RSS news stream parser.
        Extracts breaking news and matches mentions of active portfolio symbols.
        """
        cache_file = self.cache_dir / "breaking_rss_cache.json"
        if not force_refresh:
            cached = self._get_cached(cache_file)
            if cached:
                return cached

        articles = []
        try:
            res = requests.get(OPEN_RSS_URL, headers=self.headers, timeout=8)
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                for item in root.findall("./channel/item")[:limit]:
                    title = item.findtext("title") or ""
                    link = item.findtext("link") or ""
                    pub_date = item.findtext("pubDate") or ""
                    desc = item.findtext("description") or ""

                    # Check matched tokens
                    matched = []
                    if portfolio_symbols:
                        title_upper = title.upper()
                        for s in portfolio_symbols:
                            if s in title_upper or f"${s}" in title_upper:
                                matched.append(s)

                    articles.append({
                        "title": title.strip(),
                        "url": link.strip(),
                        "published_at": pub_date[:16] if pub_date else "Recent",
                        "matched_portfolio_tokens": matched,
                    })

                if articles:
                    self._save_cache(cache_file, articles)
        except Exception as e:
            print(f"[NewsSentimentScout] Open RSS fetch notice: {e}")

        return articles

    def audit_portfolio_sentiment(
        self,
        portfolio_symbols: Optional[List[str]] = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        Performs holistic sentiment and breaking news scan for the active portfolio.
        Returns Fear & Greed index, CryptoPanic alerts, and breaking headlines.
        """
        fng = self.fetch_fear_and_greed_index(force_refresh=force_refresh)
        cp_data = self.fetch_cryptopanic_posts(
            currencies=portfolio_symbols[:8] if portfolio_symbols else None,
            filter_type="important",
            limit=5,
            force_refresh=force_refresh,
        )
        rss_news = self.fetch_rss_breaking_news(
            portfolio_symbols=portfolio_symbols,
            limit=6,
            force_refresh=force_refresh,
        )

        relevant_alerts = []
        # CryptoPanic alerts
        for p in cp_data.get("posts", []):
            relevant_alerts.append({
                "type": "CryptoPanic",
                "title": p["title"],
                "currencies": p.get("currencies", []),
                "important_votes": p.get("votes_important", 0),
                "url": p.get("url", ""),
            })

        # RSS token matches
        for r in rss_news:
            if r.get("matched_portfolio_tokens"):
                relevant_alerts.append({
                    "type": "Breaking RSS",
                    "title": r["title"],
                    "currencies": r["matched_portfolio_tokens"],
                    "important_votes": "—",
                    "url": r.get("url", ""),
                })

        return {
            "fear_and_greed": fng,
            "cryptopanic_status": cp_data.get("status", "unknown"),
            "cryptopanic_reason": cp_data.get("reason", "OK"),
            "alerts": relevant_alerts,
            "recent_headlines": rss_news[:4],
        }
