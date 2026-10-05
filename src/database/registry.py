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
                    -- PnL tracking fields (v2)
                    entry_price REAL,
                    entry_date TEXT,
                    target_price REAL,
                    current_price REAL,
                    pnl_pct REAL
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

            # 3. Migrate existing DBs: add PnL and allocation columns if they don't exist
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
            # Fetch current values
            row = cur.execute(
                "SELECT entry_price, current_price FROM assets WHERE symbol = ?",
                (symbol.upper(),)
            ).fetchone()
            if not row:
                print(f"[Registry] Symbol {symbol} not found — skipping price update.")
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

    def get_pnl_summary(self) -> List[Dict[str, Any]]:
        """
        Returns list of assets with PnL data for portfolio performance review.
        Only includes assets where entry_price is set.
        """
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
                now_str,
                s.symbol.upper(),
                s.name,
                s.category,
                s.signal_type,
                s.signal_strength,
                report.verdict.value,
                report.conviction_score,
                report.analyst_thesis,
                report.skeptic_critique,
                report.cfo_reasoning,
                actions_str,
            ))

            # If verdict is FULL_CAF or INCUBATOR, also update assets table
            tier_map = {
                "FULL_CAF": "Core Candidate",
                "INCUBATOR": "High Conviction",
                "PASS": "Watch",
            }
            mapped_tier = tier_map.get(report.verdict.value, "Watch")
            status_map = {
                "FULL_CAF": "Deep Review",
                "INCUBATOR": "Incubator",
                "PASS": "Archived",
            }

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
                s.symbol.upper(),
                s.name,
                s.category,
                mapped_tier,
                report.analyst_thesis[:300],
                report.skeptic_critique[:300],
                report.conviction_score,
                status_map.get(report.verdict.value, "Active"),
                now_str,
                now_str,
            ))
            conn.commit()

    MAX_CORE_ASSETS = 6          # Core (55% капитала, ~9.1% на актив)
    MAX_HIGH_CONV_ASSETS = 8     # High Conviction (30% капитала, ~3.75% на актив)
    MAX_INCUBATOR_ASSETS = 6     # Incubator (15% капитала, ~2.5% на актив)
    MAX_ACTIVE_PORTFOLIO = 20    # СТРОГО максимум 20 активов в активном портфеле

    def enforce_portfolio_limit(self) -> Dict[str, Any]:
        """
        Enforces Darwinian selection rule:
        - Portfolio CANNOT have more than 20 assets.
        - Rank 1..6 by score (min 80) -> Core tier (55% capital, ~9.1% each)
        - Rank 7..14 by score (min 70) -> High Conviction tier (30% capital, ~3.75% each)
        - Rank 15..20 by score (min 60) -> Incubator / Invest tier (15% capital, ~2.5% each)
        - Rank 21+ and projects below threshold -> status='Watchlist'
        """
        displaced = []
        with self._get_conn() as conn:
            cur = conn.cursor()

            # 1. Reset all to Watchlist initially
            cur.execute("UPDATE assets SET status = 'Watchlist'")

            # 2. Select candidates with valid score, excluding explicit Watch
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
        """
        Returns ONLY the active portfolio assets (strictly maximum 20 assets):
        - Core (max 6, target 55% allocation)
        - High Conviction (max 8, target 30% allocation)
        - Incubator (max 6, target 15% allocation)
        """
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
        """
        Seeds registry with modern October 2026 CAF/CVE investment portfolio from scratch.
        Implements dynamic risk-adjusted target weights, correlation cluster caps,
        and eliminates all legacy zombie tokens.
        """
        if clear_existing:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM assets")
                conn.commit()

        initial_projects = [
            # 1. CORE TIER (50.0% Capital, 6 Assets, Range: 6.0% - 10.5%)
            ("HYPE", "Hyperliquid", "Perp DEX / Sovereign L1", "Sovereign L1 / CLOB", "Core", "Крупнейший ончейн-ордербук бессрочных фьючерсов с суверенным L1, рекордный ончейн-кэшфлоу ($500M+ годовых сборов), Assistance Fund выкупает HYPE с открытого рынка, 0% венчурных анлоков", "Риск регуляторного давления на деривативы и децентрализацию валидаторов", 89.5, 10.5),
            ("AAVE", "Aave", "DeFi Lending Monopoly", "Ethereum DeFi / Lending", "Core", "Абсолютный гегемон кредитования в Web3 (TVL > $20B), запущенный fee switch и действующая программа выкупа AAVE из протокольной выручки до $50M/год с еженедельными покупками", "Риск появления протоколов с изолированной ликвидностью нового поколения (Fluid, Morpho)", 88.5, 10.0),
            ("TAO", "Bittensor", "Decentralized AI / Subnets", "AI & Compute", "Core", "Базовый товарный слой машинного интеллекта, halving пройден в декабре 2025 (эмиссия 0.5 TAO/блок, max 21M TAO), лидер децентрализованного AI", "Сложность субсетей и зависимость от качества конкретных решений", 88.0, 9.0),
            ("AKT", "Akash Network", "DePIN / GPU Cloud", "AI & Compute", "Core", "Работающий прибыльный DePIN маркетплейс GPU для AI вычислений с подтвержденной выручкой и сжиганием токенов через settlement", "Конкуренция с централизованными Web2 облаками (Lambda, CoreWeave)", 87.5, 8.0),
            ("RAY", "Raydium", "Solana DEX Infra", "Solana Ecosystem", "Core", "Доминирующий генератор ончейн-комиссий в экосистеме Solana ($1M–$3M daily fees), непрерывный байбэк и сжигание RAY (вес и оценка скорректированы с учетом цикличности розничного объема)", "Высокая цикличность и зависимость от спекулятивного объема Solana", 82.5, 6.5),
            ("JUP", "Jupiter", "Solana Super-App / DEX", "Solana Ecosystem", "Core", "Финансовый хаб Solana (маршрутизация 70%+ объема), DEX + Perps + JupUSD, программа Active Staking Rewards (ASR) (оценка скорректирована, так как 70% buyback остается на стадии governance-предложения)", "Риск снижения активности на Solana и статус buyback на уровне governance", 81.5, 6.0),

            # 2. HIGH CONVICTION TIER (33.5% Capital, 9 Assets, Range: 2.0% - 5.0%)
            ("SUI", "Sui", "Layer 1 Move", "Sui Ecosystem", "High Conviction", "Самый быстрорастущий L1 нового поколения на языке Move, высокая реальная пропускная способность, институциональный приток ликвидности и сетевой эффект", "График инфляционных разблокировок токенов до 2030 года", 84.5, 5.0),
            ("TRAC", "OriginTrail", "Decentralized Knowledge Graph", "Knowledge / AI Data", "High Conviction", "Фиксированный supply 500M, 0% инфляции, 100% в обращении, ~20% заблокировано в DKG нодах под утилити, проверенная корпоративная выручка (BSI, GS1)", "Медленный цикл продаж в традиционном enterprise-секторе", 84.0, 4.5),
            ("PENDLE", "Pendle Finance", "Yield Stripping / DeFi", "DeFi Yield Trading", "High Conviction", "Монополия на рынке торговли и фиксации ончейн-доходности, ключевой строительный блок институционального ликвидного стейкинга и RWA", "Зависимость от циклов доходности на более широком рынке DeFi", 83.5, 4.5),
            ("ONDO", "Ondo Finance", "RWA / Tokenized Treasuries", "RWA", "High Conviction", "Безоговорочный лидер сектора RWA, интеграция с BlackRock BUIDL, токенизация казначейских векселей США институционального масштаба", "Регуляторные требования SEC к ценным бумагам", 83.0, 4.0),
            ("GEOD", "GEODNET", "DePIN / RTK Positioning", "DePIN Physical Infra", "High Conviction", "Крупнейшая RTK GNSS сеть базовых станций, продажа данных корпоративным клиентам -> реальный buyback & burn токенов GEOD", "Более узкий нишевый рынок по сравнению с общими вычислениями", 83.0, 4.0),
            ("FLUID", "Fluid (Instadapp)", "DeFi Liquidity Layer", "Ethereum DeFi / Lending", "High Conviction", "Масштаб $3.6B market size, $1.6B loans, $18.1B H1 volume, запущенный reserve/buyback механизм, агрегированный слой кредитования", "Конкуренция с устоявшимися пулами Aave", 82.0, 3.5),
            ("ENA", "Ethena", "Synthetic Dollar / Basis Trade", "DeFi Synthetic Dollar", "High Conviction", "Синтетический доллар USDe, генерирующий масштабные сборы на базисной торговле бессрочными фьючерсами", "Риск отрицательных ставок фандинга (negative funding rate) на затяжном спаде", 81.5, 3.0),
            ("RENDER", "Render Network", "DePIN / GPU Rendering & AI", "AI & Compute", "High Conviction", "Лидер децентрализованного рендеринга и AI вычислений на Solana, дефляционная BME модель токена", "Волатильность спроса на рендеринг и конкуренция с централизованными рендер-фермами", 80.0, 3.0),
            ("GRASS", "Grass", "DePIN / AI Web Scraping", "AI & Compute", "High Conviction", "Крупнейшая пользовательская DePIN сеть для сбора веб-данных для обучения LLM (оценка и вес скорректированы вниз из-за тяжелого графика разблокировок до 2030 года)", "Значительный supply overhang и инфляционные разблокировки до 2030 года", 78.5, 2.0),

            # 3. INCUBATOR TIER (9.5% Capital, 5 Assets, Range: 1.5% - 2.5%)
            ("INJ", "Injective", "Financial L1 / CLOB", "Sovereign L1 / CLOB", "Invest", "100% токенов в обращении, 0 будущих разблокировок, еженедельный ончейн-аукцион сжигания 60% комиссий экосистемных dApps", "Конкуренция за ликвидность с Solana и L2", 79.5, 2.5),
            ("DEEP", "DeepBook Protocol", "CLOB DEX Infra", "Sui Ecosystem", "Invest", "Центральная книга лимитных ордеров Sui, нативная интеграция в блокчейн, 100% сжигание сборов тейкеров", "Полная прямая зависимость от объема торгов внутри блокчейна Sui", 78.5, 2.0),
            ("DRIFT", "Drift Protocol", "Solana Perps & Prediction", "Solana Ecosystem", "Invest", "Ведущая DEX бессрочных фьючерсов и рынков предсказаний на Solana, кросс-маржинальная архитектура", "Конкуренция с централизованными биржами и Hyperliquid", 76.5, 2.0),
            ("ATH", "Aethir", "DePIN / Enterprise Cloud", "AI & Compute", "Invest", "Корпоративная распределенная сеть мощных GPU (вес снижен для ограничения перегрузки AI/compute кластера)", "Навес будущих разблокировок токенов и инфляция наград нодам", 74.0, 1.5),
            ("KMNO", "Kamino Finance", "Solana DeFi Liquidity", "Solana Ecosystem", "Invest", "Ключевой автоматизированный движок ликвидности и кредитования на Solana (K-Lend, Multiply vaults)", "Умеренный прямой захват ценности токеном на текущем этапе", 74.0, 1.5),

            # 4. WATCHLIST / RADAR (10 активов, вес 0.0%)
            ("SOL", "Solana", "High-Throughput L1", "Solana Ecosystem", "Watch", "Базовый L1 высокой пропускной способности, ядро розничной ликвидности и DePIN активности", "Эмиссия инфляционных наград валидаторам", 73.0, 0.0),
            ("NEAR", "NEAR Protocol", "AI & Chain Abstraction L1", "AI & Compute", "Watch", "Ведущий блокчейн в нарративе User-Owned AI и абстракции чейнов", "Конкуренция за разработчиков dApps", 72.0, 0.0),
            ("PYTH", "Pyth Network", "Low-Latency Oracle Infra", "Solana Ecosystem", "Watch", "Высокочастотные ценовые оракулы первого уровня для DeFi и деривативов", "Зависимость ценности токена от модели стейкинга", 71.5, 0.0),
            ("JTO", "Jito Network", "Solana MEV & Liquid Staking", "Solana Ecosystem", "Watch", "Монополист MEV-клиента и крупнейший LST-протокол на Solana", "Governance-heavy модель распределения наград", 71.0, 0.0),
            ("MORPHO", "Morpho Labs", "Modular Lending Primitive", "Ethereum DeFi / Lending", "Watch", "Модульный протокол изолированных кредитных рынков нового поколения", "Конкуренция с устоявшимися пулами Aave", 70.5, 0.0),
            ("EIGEN", "EigenLayer", "Ethereum Restaking Infra", "Ethereum DeFi / Lending", "Watch", "Базовый протокол коллективной криптоэкономической безопасности через restaking", "Медленный запуск монетизации AVS сервисов", 70.0, 0.0),
            ("SAFE", "Safe", "Account Abstraction Infra", "Ethereum DeFi / Lending", "Watch", "Стандарт мультисиг и смарт-аккаунтов институционального уровня", "Медленная трансляция сетевого эффекта в стоимость токена", 69.0, 0.0),
            ("SEI", "Sei Network", "Parallelized EVM L1", "Other L1", "Watch", "Параллелизованный EVM первого уровня с высокой скоростью финализации", "Необходимость формирования устойчивого DeFi ландшафта", 68.5, 0.0),
            ("TIA", "Celestia", "Modular DA Layer", "Modular Infra", "Watch", "Пионер модульной архитектуры и доступности данных (Data Availability)", "Крупные разблокировки токенов для ранних фондов", 67.0, 0.0),
            ("W", "Wormhole", "Cross-chain Messaging Infra", "Cross-chain Infra", "Watch", "Инфраструктурный стандарт кроссчейн-коммуникации и передачи сообщений", "Низкий захват ценности токеном при высоком FDV", 65.0, 0.0),
        ]

        count = 0
        for symbol, name, sector, cluster, tier, thesis, cthesis, score, weight in initial_projects:
            self.upsert_asset(
                symbol=symbol,
                name=name,
                sector=sector,
                tier=tier,
                thesis=thesis,
                counter_thesis=cthesis,
                score=score,
                status="Active" if tier != "Watch" else "Watchlist",
                target_weight=weight,
                cluster=cluster,
            )
            count += 1

        self.enforce_portfolio_limit()
        return count

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
        """Exports the entire portfolio registry into clean GitHub-flavored Markdown with Valuation Layer."""
        from src.scoring.valuation import ValuationEngine

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / "caf_portfolio_registry.md"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        active_portfolio = self.get_active_portfolio()
        all_assets = self.get_all_assets()
        watchlist = [a for a in all_assets if a["status"] != "Portfolio"]
        decisions = self.get_decisions(limit=10)
        clusters = self.get_cluster_exposure()

        # Calculate ValuationRatings for all active assets
        val_ratings = []
        for a in active_portfolio:
            vr = ValuationEngine.evaluate_entry(
                symbol=a["symbol"],
                name=a["name"],
                tier=a["tier"],
                cluster=a.get("cluster") or a.get("sector") or "",
                fundamental_score=a["score"] or 70.0,
                target_weight=a.get("target_weight") or 0.0,
            )
            val_ratings.append(vr)

        total_target_weight = sum(r.target_weight for r in val_ratings)
        total_deployed_weight = sum(r.deployed_weight for r in val_ratings)
        total_dry_powder = sum(r.dry_powder_weight for r in val_ratings)
        structural_cash = max(0.0, round(100.0 - total_target_weight, 1))
        total_liquid_reserves = round(structural_cash + total_dry_powder, 1)

        signal_badges = {
            "AGGRESSIVE_BUY": "🟢 **AGGRESSIVE BUY**",
            "BUY": "🔵 **BUY**",
            "ACCUMULATE": "🟡 **ACCUMULATE**",
            "WAIT_PULLBACK": "🟠 **WAIT PULLBACK**",
            "WAIT": "⚪ **WAIT**",
        }

        tier_badges = {
            "Core": "🟢 **CORE**",
            "Core Candidate": "🟢 **CORE**",
            "High Conviction": "🔵 **HIGH CONVICTION**",
            "Invest": "🟡 **INCUBATOR**",
            "Incubator": "🟡 **INCUBATOR**",
            "Watch": "⚪ **WATCH**",
        }

        lines = [
            "# CAF / CVE Portfolio & Incubator Registry (Institutional Architecture)",
            f"**Дата актуализации:** {now_str}  ",
            f"**Активов в активном портфеле:** {len(active_portfolio)} / {self.MAX_ACTIVE_PORTFOLIO} (Лимит: 20)  ",
            f"**Целевой вес альтов (Target Ceiling):** {total_target_weight:.1f}% | **Фактически развёрнуто сегодня:** {total_deployed_weight:.1f}%  ",
            f"**Тактический Dry Powder под лимитные зоны:** {total_dry_powder:.1f}% | **Структурный кэш (USDC):** {structural_cash:.1f}%  ",
            f"**Совокупный ликвидный буфер (USDC + Dry Powder):** **{total_liquid_reserves:.1f}%**  ",
            f"**Активов в списке наблюдения (Watchlist):** {len(watchlist)}  ",
            "",
            "## 💼 1. CAF Altcoin Alpha Sleeve — Тактическое распределение капитала",
            "Архитектура разделения: **Качество проекта (CVE Score)** задаёт целевой потолок доли (Target Weight), а **Оценка точки входа (Entry Score)** определяет объём фактического развёртывания капитала сегодня (Deployed Weight) и размер отложенного лимитного ордера (Dry Powder).",
            "",
            "| Тикер | Проект | Кластер риска | Уровень | Цель % | Развёрнуто % | Резерв % | CVE | Entry | Сигнал | Зона добора (Buy Limit Zone) |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]

        for vr in val_ratings:
            t_badge = tier_badges.get(vr.tier, vr.tier)
            s_badge = signal_badges.get(vr.entry_signal, vr.entry_signal)
            primary_zone = vr.buy_zones[0] if vr.buy_zones else "—"
            lines.append(
                f"| `{vr.symbol}` | **{vr.name}** | {vr.cluster} | {t_badge} | **{vr.target_weight:.1f}%** | {vr.deployed_weight:.1f}% | {vr.dry_powder_weight:.1f}% | {vr.fundamental_score:.1f} | **{vr.entry_score:.1f}** | {s_badge} | `{primary_zone}` |"
            )

        lines += [
            "",
            f"| `USDC` | **Cash Reserve** | Liquidity Buffer | 🛡️ **RESERVE** | **{structural_cash:.1f}%** | {structural_cash:.1f}% | 0.0% | 100.0 | 100.0 | 🛡️ **STABLE** | Базовый структурный буфер ликвидности |",
            f"| `USDC_DCA`| **Tactical Dry Powder** | Tactical Buffer | ⏳ **DRY POWDER** | **{total_dry_powder:.1f}%** | 0.0% | {total_dry_powder:.1f}% | 100.0 | — | ⏳ **PENDING** | Отложенные лимитные сетки на откатах (HYPE, TAO и др.) |",
            "",
            "---",
            "## 📐 2. Матрица Оценки и Сценарного Анализа (5-Layer Valuation Engine)",
            "Сценарный анализ асимметрии доходности: вероятностно-взвешенные сценарии (Bear 35% / Base 45% / Bull 20%) и соотношение потенциала роста к риску просадки (Asymmetry Ratio = Base Upside / Downside Risk).",
            "",
            "| Тикер | Текущая ($) | ATH ($) | От ATH % | Bear ($) | Base ($) | Bull ($) | EV Доход % | Downside % | Асимметрия R/R | Тактический Сигнал |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]

        for vr in val_ratings:
            s_badge = signal_badges.get(vr.entry_signal, vr.entry_signal)
            cur_fmt = f"${vr.current_price:,.2f}" if vr.current_price >= 1.0 else f"${vr.current_price:.3f}"
            ath_fmt = f"${vr.ath_price:,.2f}" if vr.ath_price >= 1.0 else f"${vr.ath_price:.3f}"
            bear_fmt = f"${vr.expected_value:,.2f}"  # helper
            # Get raw scenario values from ASSET_PRICE_SCENARIOS
            sc_data = ValuationEngine.ASSET_PRICE_SCENARIOS.get(vr.symbol, {})
            b_bear = f"${sc_data.get('bear', 0):,.2f}" if sc_data.get('bear', 0) >= 1.0 else f"${sc_data.get('bear', 0):.3f}"
            b_base = f"${sc_data.get('base', 0):,.2f}" if sc_data.get('base', 0) >= 1.0 else f"${sc_data.get('base', 0):.3f}"
            b_bull = f"${sc_data.get('bull', 0):,.2f}" if sc_data.get('bull', 0) >= 1.0 else f"${sc_data.get('bull', 0):.3f}"

            lines.append(
                f"| `{vr.symbol}` | {cur_fmt} | {ath_fmt} | {vr.ath_drawdown_pct:+.1f}% | {b_bear} | {b_base} | {b_bull} | {vr.ev_return_pct:+.1f}% | {vr.downside_pct:+.1f}% | **{vr.asymmetry_ratio:.2f}x** | {s_badge} |"
            )

        lines += [
            "",
            "---",
            "## 🛡️ 3. Контроль Концентрации и Кластерных Лимитов (Cluster Risk Caps)",
            "| Кластер риска | Текущий вес (Целевой) | Лимит риска | Статус контроля | Активы кластера |",
            "|---|---|---|---|---|",
        ]

        cluster_limits = {
            "AI & Compute": (24.0, "TAO, AKT, RENDER, GRASS, ATH"),
            "Solana Ecosystem": (20.0, "RAY, JUP, DRIFT, KMNO"),
            "Ethereum DeFi / Lending": (25.0, "AAVE, FLUID"),
            "Sovereign L1 / CLOB": (15.0, "HYPE, INJ"),
            "RWA": (10.0, "ONDO"),
            "DePIN Physical Infra": (10.0, "GEOD"),
            "DeFi Yield Trading": (10.0, "PENDLE"),
            "Sui Ecosystem": (8.0, "SUI, DEEP"),
            "Knowledge / AI Data": (10.0, "TRAC"),
            "DeFi Synthetic Dollar": (8.0, "ENA"),
        }

        for c_name, c_weight in clusters.items():
            cap, assets_str = cluster_limits.get(c_name, (20.0, "—"))
            status = "✅ В пределах лимита" if c_weight <= cap else "⚠️ ПРЕВЫШЕНИЕ"
            lines.append(f"| **{c_name}** | **{c_weight:.1f}%** | $\\le {cap:.1f}\\%$ | {status} | {assets_str} |")

        lines += [
            "",
            "---",
            "## 🌐 4. Институциональный Macro-Портфель (Total Crypto Portfolio)",
            "Если CAF управляет **всем совокупным криптокапиталом**, базовый слой формируют монетарный якорь BTC и расчетная инфраструктура ETH:",
            "",
            "| Компонент | Роль в балансе | Доля от капитала | Активы и стратегия |",
            "|---|---|---|---|",
            "| 🥇 **Macro Core Anchor** | Монетарный резерв и базовый L1 | **45.0%** | **BTC (35.0%)** + **ETH (10.0%)** — минимальный бета-риск, защита капитала |",
            "| 🚀 **CAF Alpha Sleeve** | Генерация избыточной доходности | **50.0%** | 20 активов CAF (вес каждого актива = 50% от целевого веса в Altcoin Sleeve) |",
            "| 💵 **Tactical Cash** | Буфер ликвидности | **5.0%** | **USDC / USDT** — тактический резерв под ребалансировку и волатильность |",
            "",
            "---",
            f"## 📋 5. Резервная скамья и наблюдение (Watchlist — {len(watchlist)} активов)",
            "",
            "| Тикер | Проект | Сектор | Уровень CVE | Score | Причина нахождения в резерве |",
            "|---|---|---|---|---|---|",
        ]

        for a in watchlist:
            badge = tier_badges.get(a["tier"], a["tier"])
            score_str = f"{a['score']:.1f}" if a["score"] else "—"
            reason = (a["counter_thesis"][:80] + "...") if a.get("counter_thesis") else (a["thesis"][:80] if a.get("thesis") else "Наблюдение")
            lines.append(
                f"| `{a['symbol']}` | {a['name']} | {a['sector']} | {badge} | {score_str} | {reason} |"
            )

        if decisions:
            lines += [
                "",
                "---",
                "## 🏛️ 6. Последние решения Инвестиционного Комитета",
                "",
                "| Дата | Проект | Сигнал | Вердикт | Уверенность | Резюме CFO |",
                "|---|---|---|---|---|---|",
            ]
            verdict_badges = {
                "FULL_CAF": "🔴 **FULL CAF**",
                "INCUBATOR": "🟡 **INCUBATOR**",
                "PASS": "⚪ **PASS**",
            }
            for d in decisions:
                v_badge = verdict_badges.get(d["verdict"], d["verdict"])
                cfo_short = (d["cfo_reasoning"][:100] + "...") if d["cfo_reasoning"] and len(d["cfo_reasoning"]) > 100 else (d["cfo_reasoning"] or "—")
                cfo_clean = cfo_short.replace("\n", " ")
                lines.append(
                    f"| {d['created_at'][:16]} | **{d['name']}** (`{d['symbol']}`) | {d['signal_type']} | {v_badge} | {d['conviction_score']:.0f}% | {cfo_clean} |"
                )

        report_path.write_text("\n".join(lines), encoding="utf-8")
        return report_path
