import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from config import CACHE_DIR, CACHE_TTL, GITHUB_TOKEN


class GitHubScout:
    """
    Scout for analyzing developer and engineering activity on GitHub.
    Philosophy: Capital follows code. Real protocols have active developers,
    frequent commits, and regular releases — not just marketing hype.

    v2 Improvements:
    - Added search_repo() for dynamic repository discovery
    - Fixed broken KNOWN_REPOS entries (pumpswap/contracts → removed)
    - Expanded KNOWN_REPOS with verified repos
    """

    BASE_URL = "https://api.github.com"

    # Verified, correct GitHub repository mappings.
    # Only include repos that are confirmed to exist.
    KNOWN_REPOS = {
        "SUI":    "MystenLabs/sui",
        "APT":    "aptos-labs/aptos-core",
        "STRK":   "starkware-libs/cairo",
        "EIGEN":  "Layr-Labs/eigenlayer-contracts",
        "RUNE":   "thorchain/thornode",
        "RAY":    "raydium-io/raydium-clmm",
        "GRT":    "graphprotocol/graph-node",
        "AKT":    "akash-network/node",
        "AR":     "ArweaveTeam/arweave",
        "CFG":    "centrifuge/centrifuge-chain",
        "SNX":    "Synthetixio/synthetix",
        "KMNO":   "Kamino-Finance/kamino-lending",
        "TRAC":   "OriginTrail/ot-node",
        "DEEP":   "MystenLabs/deepbook-v3",
        "FLUID":  "Instadapp/fluid-contracts",
        "AAVE":   "aave/aave-v3-core",
        "UNI":    "Uniswap/v3-core",
        "CRV":    "curvefi/curve-contract",
        "MKR":    "makerdao/dss",
        "COMP":   "compound-finance/compound-protocol",
        "GMX":    "gmx-io/gmx-contracts",
        "JUP":    "jup-ag/jupiter-core",
        "JTO":    "jito-foundation/jito-programs",
        "WIF":    "solana-labs/solana",     # on Solana network
        "PENDLE": "pendle-finance/pendle-core-v2",
        "LIDO":   "lidofinance/lido-dao",
        "RPL":    "rocket-pool/rocketpool",
        "ENA":    "ethena-labs/ethena-core",
        "GRASS":  "getgrass-io/grass",
        "DYDX":   "dydxprotocol/v4-chain",
        "GEOD":   "GEODNET/geodnet-core",
    }

    def __init__(self, cache_ttl: int = 86400):  # 24-hour cache for GitHub data
        self.cache_ttl = cache_ttl
        self.cache_dir = CACHE_DIR
        self.token = GITHUB_TOKEN
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "CAF-Terminal/1.0",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    def _get_cache_path(self, key: str) -> Path:
        safe_name = key.replace("/", "_").replace(" ", "_")
        return self.cache_dir / f"github_{safe_name}.json"

    def _get_cached(self, path: Path) -> Optional[Dict[str, Any]]:
        if path.exists():
            if time.time() - path.stat().st_mtime < self.cache_ttl:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
        return None

    def _save_cache(self, path: Path, data: Any) -> None:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def search_repo(self, project_name: str, min_stars: int = 50) -> Optional[str]:
        """
        Dynamically searches GitHub for a project's primary repository.
        Used when symbol is NOT in KNOWN_REPOS.
        Returns "owner/repo" string or None if not found.
        """
        cache_key = f"search_{project_name.lower().replace(' ', '_')}"
        cache_path = self._get_cache_path(cache_key)
        cached = self._get_cached(cache_path)
        if cached:
            return cached.get("repo")

        query = f"{project_name} topic:defi OR topic:blockchain OR topic:web3"
        try:
            res = requests.get(
                f"{self.BASE_URL}/search/repositories",
                headers=self.headers,
                params={"q": query, "sort": "stars", "order": "desc", "per_page": 5},
                timeout=10,
            )
            if res.status_code in (403, 429):
                print("[Warning] GitHub Search API rate limit reached.")
                return None
            if res.status_code != 200:
                return None

            items = res.json().get("items", [])
            for item in items:
                if item.get("stargazers_count", 0) >= min_stars:
                    full_name = item["full_name"]
                    self._save_cache(cache_path, {"repo": full_name})
                    print(f"[GitHub] Dynamic search found: {project_name} → {full_name}")
                    return full_name
        except Exception as e:
            print(f"[GitHub] Search failed for '{project_name}': {e}")
        return None

    def fetch_repo_metrics(self, repo_full_name: str, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Fetches repository statistics: stars, forks, commits in last 30d,
        contributors, and days since last commit.
        """
        parts = repo_full_name.strip().split("/")
        if len(parts) != 2:
            return {}
        owner, repo = parts[0], parts[1]

        cache_path = self._get_cache_path(f"{owner}_{repo}")
        if not force_refresh:
            cached = self._get_cached(cache_path)
            if cached:
                return cached

        print(f"[GitHub] Fetching metrics for {owner}/{repo}...")
        try:
            # 1. Base repo info
            res = requests.get(
                f"{self.BASE_URL}/repos/{owner}/{repo}",
                headers=self.headers,
                timeout=12,
            )
            if res.status_code == 404:
                print(f"[GitHub] Repo not found: {owner}/{repo}")
                return {"error": "Repository not found", "repo": repo_full_name}
            if res.status_code in (403, 429):
                print("[Warning] GitHub API rate limit reached.")
                return {"error": "Rate limit reached"}
            res.raise_for_status()
            base = res.json()

            # 2. Recent commits (last 30 days)
            since_date = datetime.now(timezone.utc).replace(day=1).isoformat()
            commits_res = requests.get(
                f"{self.BASE_URL}/repos/{owner}/{repo}/commits",
                headers=self.headers,
                params={"per_page": 100, "since": since_date},
                timeout=12,
            )
            commits_30d = (
                len(commits_res.json())
                if commits_res.status_code == 200 and isinstance(commits_res.json(), list)
                else 0
            )

            # 3. Days since last commit
            pushed_at = base.get("pushed_at")
            days_since_push = None
            if pushed_at:
                push_dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
                days_since_push = (datetime.now(timezone.utc) - push_dt).days

            # 4. Calculate Developer Momentum Score (0-100)
            dev_score = self._calculate_dev_score(
                stars=base.get("stargazers_count", 0),
                forks=base.get("forks_count", 0),
                commits_30d=commits_30d,
                days_since_push=days_since_push,
            )

            metrics = {
                "repo": f"{owner}/{repo}",
                "stars": base.get("stargazers_count", 0),
                "forks": base.get("forks_count", 0),
                "open_issues": base.get("open_issues_count", 0),
                "commits_30d": commits_30d,
                "days_since_push": days_since_push,
                "dev_score": dev_score,
                "license": (base.get("license") or {}).get("spdx_id"),
                "is_active": days_since_push is not None and days_since_push <= 14,
            }

            self._save_cache(cache_path, metrics)
            return metrics

        except Exception as e:
            print(f"[Error] GitHub metrics failed for {owner}/{repo}: {e}")
            return {}

    def _calculate_dev_score(
        self,
        stars: int,
        forks: int,
        commits_30d: int,
        days_since_push: Optional[int],
    ) -> float:
        """Calculates 0-100 score for engineering health and momentum."""
        score = 30.0

        # Freshness of code (Lindy / abandonware test)
        if days_since_push is not None:
            if days_since_push <= 3:
                score += 30.0
            elif days_since_push <= 14:
                score += 20.0
            elif days_since_push <= 30:
                score += 10.0
            elif days_since_push > 90:
                score -= 20.0  # Zombie repo penalty

        # Monthly commit velocity
        if commits_30d >= 50:
            score += 25.0
        elif commits_30d >= 20:
            score += 18.0
        elif commits_30d >= 5:
            score += 10.0

        # Community adoption (stars/forks)
        if stars > 1000:
            score += 10.0
        elif stars > 300:
            score += 5.0
        if forks > 200:
            score += 5.0

        return round(min(100.0, max(0.0, score)), 1)

    def get_repo_for_symbol(self, symbol: str) -> Optional[str]:
        """Resolves known GitHub repo for a token symbol. Returns None if unknown."""
        return self.KNOWN_REPOS.get(symbol.upper())
