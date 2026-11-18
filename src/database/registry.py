import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional
from config import DATA_DIR, REPORTS_DIR


DB_PATH = DATA_DIR / "caf_registry.db"


class CAFRegistry:
    """
    Persistent SQLite Registry for CAF/CVE Asset Portfolio,
    Incubator Watchlist, and Committee Deliberation History.
    """

    MAX_CORE_ASSETS = 6          # Core (55% капитала, ~9.1% на актив)
    MAX_HIGH_CONV_ASSETS = 8     # High Conviction (30% капитала, ~3.75% на актив)
    MAX_INCUBATOR_ASSETS = 6     # Incubator (15% капитала, ~2.5% на актив)
    MAX_ACTIVE_PORTFOLIO = 20    # СТРОГО максимум 20 активов в активном портфеле

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            cur = conn.cursor()
            # 1. Assets / Portfolio Registry table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS assets (
                    symbol TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    sector TEXT,
                    tier TEXT NOT NULL,
                    thesis TEXT,
                    counter_thesis TEXT,
                    score REAL,
                    status TEXT DEFAULT 'Active',
                    last_reviewed TEXT,
                    updated_at TEXT,
                    entry_price REAL,
                    entry_date TEXT,
                    target_price REAL,
                    current_price REAL,
                    pnl_pct REAL,
                    target_weight REAL,
                    cluster TEXT
                )
            """)

            # 2. Committee Decisions History table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS committee_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    name TEXT NOT NULL,
                    sector TEXT,
                    signal_type TEXT NOT NULL,
                    signal_strength REAL,
                    verdict TEXT NOT NULL,
                    conviction_score REAL,
                    analyst_thesis TEXT,
                    skeptic_critique TEXT,
                    cfo_reasoning TEXT,
                    follow_up_actions TEXT
                )
            """)

            # 3. Add any missing columns to existing databases
            existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(assets)")}
            extra_cols = {
                "entry_price":   "REAL",
                "entry_date":    "TEXT",
                "target_price":  "REAL",
                "current_price": "REAL",
                "pnl_pct":       "REAL",
                "target_weight": "REAL",
                "cluster":       "TEXT",
            }
            for col, col_type in extra_cols.items():
                if col not in existing_cols:
                    cur.execute(f"ALTER TABLE assets ADD COLUMN {col} {col_type}")

            conn.commit()

    def upsert_asset(
        self,
        symbol: str,
        name: str,
        tier: str,
        sector: str = "",
        thesis: str = "",
        counter_thesis: str = "",
        score: Optional[float] = None,
        status: str = "Active",
        target_weight: Optional[float] = None,
        cluster: str = "",
    ) -> None:
        """Adds or updates an asset in the registry."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO assets (symbol, name, sector, tier, thesis, counter_thesis, score, status, last_reviewed, updated_at, target_weight, cluster)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    name = excluded.name,
                    sector = CASE WHEN excluded.sector != '' THEN excluded.sector ELSE assets.sector END,
                    tier = excluded.tier,
                    thesis = CASE WHEN excluded.thesis != '' THEN excluded.thesis ELSE assets.thesis END,
                    counter_thesis = CASE WHEN excluded.counter_thesis != '' THEN excluded.counter_thesis ELSE assets.counter_thesis END,
                    score = COALESCE(excluded.score, assets.score),
                    status = excluded.status,
                    last_reviewed = excluded.last_reviewed,
                    updated_at = excluded.updated_at,
                    target_weight = COALESCE(excluded.target_weight, assets.target_weight),
                    cluster = CASE WHEN excluded.cluster != '' THEN excluded.cluster ELSE assets.cluster END
            """, (symbol.upper(), name, sector, tier, thesis, counter_thesis, score, status, now_str, now_str, target_weight, cluster))
            conn.commit()

    def update_price(
        self,
        symbol: str,
        entry_price: Optional[float] = None,
        entry_date: Optional[str] = None,
        target_price: Optional[float] = None,
        current_price: Optional[float] = None,
    ) -> None:
        """
        Records entry/target/current price for PnL tracking.
        Automatically calculates pnl_pct if both entry_price and current_price are available.
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_conn() as conn:
            cur = conn.cursor()
            row = cur.execute(
                "SELECT entry_price, current_price FROM assets WHERE symbol = ?",
                (symbol.upper(),)
            ).fetchone()
            if not row:
                return

            eff_entry = entry_price if entry_price is not None else (row["entry_price"] or 0)
            eff_current = current_price if current_price is not None else (row["current_price"] or 0)
            pnl = None
            if eff_entry and eff_current:
                pnl = round((eff_current - eff_entry) / eff_entry * 100, 2)

            cur.execute("""
                UPDATE assets SET
                    entry_price   = COALESCE(?, entry_price),
                    entry_date    = COALESCE(?, entry_date),
                    target_price  = COALESCE(?, target_price),
                    current_price = COALESCE(?, current_price),
                    pnl_pct       = ?,
                    updated_at    = ?
                WHERE symbol = ?
            """, (entry_price, entry_date, target_price, current_price, pnl, now_str, symbol.upper()))
            conn.commit()

    def update_live_prices(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Queries live prices across market scouts (CoinGecko + Gate.io fallback)
        and updates all registered assets with live market prices and recalculated PnL.
        """
        import requests
        from src.scouts.coingecko import CoinGeckoScout
        from src.scoring.valuation import ValuationEngine

        cg = CoinGeckoScout()
        markets = cg.fetch_markets(pages=4, force_refresh=force_refresh)
        price_map: Dict[str, float] = {}

        for m in markets:
            sym = m.get("symbol", "").upper()
            p = m.get("current_price")
            if sym and p is not None:
                price_map[sym] = float(p)

        # Gate.io spot tickers fallback for any tokens missing in CoinGecko
        try:
            r = requests.get("https://api.gateio.ws/api/v4/spot/tickers", timeout=8)
            if r.status_code == 200:
                for t in r.json():
                    cp = t.get("currency_pair", "")
                    if cp.endswith("_USDT"):
                        base = cp.replace("_USDT", "").upper()
                        if base not in price_map and t.get("last"):
                            price_map[base] = float(t["last"])
        except Exception:
            pass

        updated_count = 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._get_conn() as conn:
            cur = conn.cursor()
            rows = cur.execute("SELECT symbol, entry_price, current_price FROM assets").fetchall()

            for row in rows:
                sym = row["symbol"]
                live_p = price_map.get(sym)
                if not live_p:
                    sc = ValuationEngine.ASSET_PRICE_SCENARIOS.get(sym)
                    if sc and sc.get("current"):
                        live_p = float(sc["current"])

                if live_p:
                    entry_p = row["entry_price"]
                    if not entry_p:
                        sc = ValuationEngine.ASSET_PRICE_SCENARIOS.get(sym)
                        entry_p = float(sc["current"]) if (sc and sc.get("current")) else live_p

                    pnl = round((live_p - entry_p) / entry_p * 100, 2) if entry_p else 0.0

                    cur.execute("""
                        UPDATE assets SET
                            current_price = ?,
                            entry_price   = COALESCE(entry_price, ?),
                            pnl_pct       = ?,
                            updated_at    = ?
                        WHERE symbol = ?
                    """, (live_p, entry_p, pnl, now_str, sym))
                    updated_count += 1

            conn.commit()

        return {"updated_count": updated_count, "total_assets": len(rows)}

    def get_pnl_summary(self) -> List[Dict[str, Any]]:
        """Returns list of assets with PnL data for portfolio performance review."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            rows = cur.execute("""
                SELECT symbol, name, tier, entry_price, entry_date, target_price,
                       current_price, pnl_pct, status
                FROM assets
                WHERE entry_price IS NOT NULL
                ORDER BY pnl_pct DESC NULLS LAST
            """).fetchall()
            return [dict(r) for r in rows]

    def record_committee_decision(self, report: Any) -> None:
        """Records deliberation from Investment Committee report into database."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        s = report.signal
        actions_str = json.dumps(report.follow_up_actions, ensure_ascii=False)

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO committee_decisions (
                    created_at, symbol, name, sector, signal_type, signal_strength,
                    verdict, conviction_score, analyst_thesis, skeptic_critique,
                    cfo_reasoning, follow_up_actions
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now_str, s.symbol.upper(), s.name, s.category, s.signal_type,
                s.signal_strength, report.verdict.value, report.conviction_score,
                report.analyst_thesis, report.skeptic_critique, report.cfo_reasoning, actions_str
            ))

            tier_map = {"FULL_CAF": "Core Candidate", "INCUBATOR": "High Conviction", "PASS": "Watch"}
            status_map = {"FULL_CAF": "Deep Review", "INCUBATOR": "Incubator", "PASS": "Archived"}

            cur.execute("""
                INSERT INTO assets (symbol, name, sector, tier, thesis, counter_thesis, score, status, last_reviewed, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    tier = excluded.tier,
                    thesis = excluded.thesis,
                    status = excluded.status,
                    last_reviewed = excluded.last_reviewed,
                    updated_at = excluded.updated_at
            """, (
                s.symbol.upper(), s.name, s.category, tier_map.get(report.verdict.value, "Watch"),
                report.analyst_thesis[:300], report.skeptic_critique[:300], report.conviction_score,
                status_map.get(report.verdict.value, "Active"), now_str, now_str
            ))
            conn.commit()

    def enforce_portfolio_limit(self) -> Dict[str, Any]:
        """Enforces Darwinian selection rule (strictly <= 20 assets in active portfolio)."""
        displaced = []
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE assets SET status = 'Watchlist'")
            cur.execute("""
                SELECT symbol, name, score, tier, target_weight FROM assets 
                WHERE score IS NOT NULL AND tier != 'Watch'
                ORDER BY 
                    CASE tier 
                        WHEN 'Core' THEN 1 
                        WHEN 'Core Candidate' THEN 2 
                        WHEN 'High Conviction' THEN 3 
                        WHEN 'Invest' THEN 4 
                        WHEN 'Incubator' THEN 5 
                        ELSE 6 
                    END,
                    score DESC, symbol ASC
            """)
            candidates = cur.fetchall()

            for idx, r in enumerate(candidates):
                sym = r["symbol"]
                sc = r["score"] or 0
                if idx < self.MAX_ACTIVE_PORTFOLIO:
                    cur.execute("UPDATE assets SET status = 'Portfolio' WHERE symbol = ?", (sym,))
                else:
                    displaced.append({"symbol": sym, "score": sc, "displaced_to": "Watchlist"})
                    cur.execute("UPDATE assets SET status = 'Watchlist' WHERE symbol = ?", (sym,))
            conn.commit()

        return {"displaced": displaced}

    def get_active_portfolio(self) -> List[Dict[str, Any]]:
        """Returns ONLY active portfolio assets (strictly <= 20 assets)."""
        self.enforce_portfolio_limit()
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM assets 
                WHERE status = 'Portfolio'
                ORDER BY 
                    CASE tier 
                        WHEN 'Core' THEN 1 
                        WHEN 'Core Candidate' THEN 2 
                        WHEN 'High Conviction' THEN 3 
                        WHEN 'Invest' THEN 4 
                        WHEN 'Incubator' THEN 5 
                        ELSE 6 
                    END, 
                    score DESC, 
                    symbol ASC
                LIMIT 20
            """)
            return [dict(row) for row in cur.fetchall()]

    def get_all_assets(self, tier: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns all assets ordered by tier priority."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            if tier:
                cur.execute("SELECT * FROM assets WHERE tier = ? ORDER BY score DESC, symbol ASC", (tier,))
            else:
                cur.execute("SELECT * FROM assets ORDER BY CASE tier WHEN 'Core' THEN 1 WHEN 'Core Candidate' THEN 2 WHEN 'High Conviction' THEN 3 WHEN 'Invest' THEN 4 ELSE 5 END, score DESC, symbol ASC")
            return [dict(row) for row in cur.fetchall()]

    def get_decisions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns latest committee decisions."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM committee_decisions ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cur.fetchall()]

    def seed_from_conversation(self, clear_existing: bool = True) -> int:
        """Seeds registry with initial portfolio data via registry_seed module."""
        from src.database.registry_seed import seed_initial_portfolio
        return seed_initial_portfolio(self, clear_existing=clear_existing)

    def get_cluster_exposure(self) -> Dict[str, float]:
        """Calculates total allocation percentage per risk cluster."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT cluster, SUM(COALESCE(target_weight, 0)) as total_weight
                FROM assets
                WHERE status = 'Portfolio' AND cluster IS NOT NULL AND cluster != ''
                GROUP BY cluster
                ORDER BY total_weight DESC
            """)
            return {row["cluster"]: round(row["total_weight"], 2) for row in cur.fetchall()}

    def generate_registry_markdown(self) -> Path:
        """Exports the entire portfolio registry into clean GitHub-flavored Markdown."""
        from src.database.registry_exporter import export_registry_markdown
        return export_registry_markdown(self)
