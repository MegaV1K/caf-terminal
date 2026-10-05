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

            # 3. Migrate existing DBs: add PnL columns if they don't exist
            existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(assets)")}
            pnl_cols = {
                "entry_price":   "REAL",
                "entry_date":    "TEXT",
                "target_price":  "REAL",
                "current_price": "REAL",
                "pnl_pct":       "REAL",
            }
            for col, col_type in pnl_cols.items():
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
    ) -> None:
        """Adds or updates an asset in the registry."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO assets (symbol, name, sector, tier, thesis, counter_thesis, score, status, last_reviewed, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    name = excluded.name,
                    sector = CASE WHEN excluded.sector != '' THEN excluded.sector ELSE assets.sector END,
                    tier = excluded.tier,
                    thesis = CASE WHEN excluded.thesis != '' THEN excluded.thesis ELSE assets.thesis END,
                    counter_thesis = CASE WHEN excluded.counter_thesis != '' THEN excluded.counter_thesis ELSE assets.counter_thesis END,
                    score = COALESCE(excluded.score, assets.score),
                    status = excluded.status,
                    last_reviewed = excluded.last_reviewed,
                    updated_at = excluded.updated_at
            """, (symbol.upper(), name, sector, tier, thesis, counter_thesis, score, status, now_str, now_str))
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

            # 2. Select candidates with valid score, excluding explicit Watch/Meme
            cur.execute("""
                SELECT symbol, name, score, tier FROM assets 
                WHERE score IS NOT NULL AND score >= 60.0
                ORDER BY score DESC, symbol ASC
            """)
            candidates = cur.fetchall()

            for idx, r in enumerate(candidates):
                sym = r["symbol"]
                sc = r["score"] or 0
                if idx < self.MAX_CORE_ASSETS and sc >= 80.0:
                    cur.execute("UPDATE assets SET status = 'Portfolio', tier = 'Core' WHERE symbol = ?", (sym,))
                elif idx < (self.MAX_CORE_ASSETS + self.MAX_HIGH_CONV_ASSETS) and sc >= 70.0:
                    cur.execute("UPDATE assets SET status = 'Portfolio', tier = 'High Conviction' WHERE symbol = ?", (sym,))
                elif idx < self.MAX_ACTIVE_PORTFOLIO and sc >= 60.0:
                    cur.execute("UPDATE assets SET status = 'Portfolio', tier = 'Invest' WHERE symbol = ?", (sym,))
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
        Strictly eliminates legacy zombie tokens (COMP, IOTA, NEO, etc.) and focuses on
        real revenue, buyback & burn, DePIN cash flow, and modern high-throughput winners.
        """
        if clear_existing:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM assets")
                conn.commit()

        initial_projects = [
            # 1. CORE TIER (55% Capital, 6 Assets, Target Score >= 86.0)
            ("HYPE", "Hyperliquid", "Perp DEX / Sovereign L1", "Core", "Крупнейший ончейн-ордербук бессрочных фьючерсов с суверенным L1, рекордный ончейн-кэшфлоу ($500M+ годовых сборов), 100% честное распределение без хищнических венчурных анлоков", "Риск регуляторного давления на бессрочные деривативы и децентрализацию валидаторов", 89.5),
            ("AAVE", "Aave", "DeFi Lending Monopoly", "Core", "Абсолютный гегемон кредитования в Web3 (TVL > $20B), запуск fee switch и регулярный buyback AAVE с рынка из сборов протокола", "Риск появления протоколов с изолированной ликвидностью нового поколения (Fluid, Morpho)", 88.5),
            ("TAO", "Bittensor", "Decentralized AI / Subnets", "Core", "Базовый децентрализованный товарный слой машинного интеллекта, экономика соревновательных субсетей для AI обучения и инференса", "Высокая сложность архитектуры субсетей и зависимость от качества конкретных AI-решений", 88.0),
            ("AKT", "Akash Network", "DePIN / GPU Cloud", "Core", "Работающий прибыльный DePIN маркетплейс GPU для AI вычислений с подтвержденной выручкой и сжиганием токенов через settlement", "Конкуренция с централизованными Web2 облаками (Lambda, CoreWeave) и доступность новейших чипов", 87.5),
            ("RAY", "Raydium", "Solana DEX Infra", "Core", "Доминирующий генератор ончейн-комиссий в экосистеме Solana ($1M–$3M daily fees), непрерывный байбэк и сжигание RAY", "Зависимость от объемов спекулятивной активности в экосистеме Solana", 86.5),
            ("JUP", "Jupiter", "Solana Super-App / DEX", "Core", "Финансовый хаб Solana (маршрутизация 70%+ объема), DEX + Perps + JupUSD, программа Active Staking Rewards (ASR) с распределением комиссий", "Риск снижения активности на Solana и давление от распределения ASR наград", 86.0),

            # 2. HIGH CONVICTION TIER (30% Capital, 8 Assets, Target Score 80.0 - 85.0)
            ("SUI", "Sui", "Layer 1 Move", "High Conviction", "Самый быстрорастущий L1 нового поколения на языке Move, высокая реальная пропускная способность, институциональный приток ликвидности", "График инфляционных разблокировок токенов для ранних инвесторов", 84.5),
            ("PENDLE", "Pendle Finance", "Yield Stripping / DeFi", "High Conviction", "Монополия на рынке торговли и фиксации ончейн-доходности, ключевой строительный блок ликвидного стейкинга и RWA", "Зависимость от циклов доходности на более широком рынке DeFi", 83.5),
            ("ONDO", "Ondo Finance", "RWA / Tokenized Treasuries", "High Conviction", "Безоговорочный лидер сектора RWA, интеграция с BlackRock BUIDL, токенизация казначейских векселей США институционального масштаба", "Жесткие регуляторные требования SEC к ценным бумагам и юрисдикционные барьеры", 83.0),
            ("ENA", "Ethena", "Synthetic Dollar / Basis Trade", "High Conviction", "Высокодоходный синтетический доллар USDe, генерирующий колоссальные сборы на базисной торговле бессрочными фьючерсами", "Риск отрицательных ставок фандинга (negative funding rate) на медвежьем рынке", 82.5),
            ("GRASS", "Grass", "DePIN / AI Web Scraping", "High Conviction", "Крупнейшая пользовательская DePIN сеть для сбора и валидации чистых веб-данных для обучения LLM, прямые B2B контракты", "Юридические риски сбора веб-данных и удержание миллионов операторов нод", 82.0),
            ("GEOD", "GEODNET", "DePIN / RTK Positioning", "High Conviction", "Глобальная сеть базовых станций высокоточного GNSS позиционирования, реальная коммерческая выручка, механизм buyback & burn", "Скорость физического развертывания наземных станций в отдаленных регионах", 81.5),
            ("TRAC", "OriginTrail", "Decentralized Knowledge Graph", "High Conviction", "Децентрализованный граф знаний (DKG) для проверяемого AI и верификации фактов, корпоративные интеграции (BSI, GS1)", "Медленный цикл продаж в традиционном enterprise-секторе", 80.5),
            ("RENDER", "Render Network", "DePIN / GPU Rendering & AI", "High Conviction", "Лидер децентрализованного рендеринга и AI вычислений на Solana, модель Burn-and-Mint Equilibrium (BME)", "Волатильность спроса на рендеринг и конкуренция со стороны централизованных рендер-ферм", 80.0),

            # 3. INCUBATOR / EMERGING TIER (15% Capital, 6 Assets, Target Score 74.0 - 79.0)
            ("DEEP", "DeepBook Protocol", "CLOB DEX Infra", "Invest", "Центральная книга лимитных ордеров Sui, нативная интеграция в блокчейн, 100% сжигание сборов тейкеров", "Полная прямая зависимость от объема торгов внутри блокчейна Sui", 78.5),
            ("FLUID", "Fluid (Instadapp)", "DeFi Liquidity Layer", "Invest", "Инновационный агрегированный слой кредитования и DEX с рекордной капиталоэффективностью пулов ликвидности", "Жесткая конкуренция с монополистами кредитования (Aave, Morpho)", 78.0),
            ("DRIFT", "Drift Protocol", "Solana Perps & Prediction", "Invest", "Ведущая DEX бессрочных фьючерсов и рынков предсказаний на Solana, кросс-маржинальная архитектура", "Конкуренция с централизованными биржами и Hyperliquid", 76.5),
            ("ATH", "Aethir", "DePIN / Enterprise Cloud", "Invest", "Корпоративная распределенная сеть мощных GPU для облачного гейминга и AI inference с институциональными контрактами", "Навес будущих разблокировок токенов и инфляция наград нодам", 75.5),
            ("INJ", "Injective", "Financial L1 / CLOB", "Invest", "Сверхбыстрый финансовый L1 с непрерывным еженедельным ончейн-аукционом сжигания токенов из сборов экосистемных dApps", "Конкуренция за ликвидность с L1 общего назначения (Solana, Sui)", 75.0),
            ("KMNO", "Kamino Finance", "Solana DeFi Liquidity", "Invest", "Ключевой автоматизированный движок ликвидности и кредитования на Solana (K-Lend, Multiply vaults)", "Умеренный прямой захват ценности токеном на текущем этапе", 74.0),

            # 4. WATCHLIST / EMERGING RADAR (Резервная скамья — перспективные инфраструктурные активы)
            ("SOL", "Solana", "High-Throughput L1", "Watch", "Базовый L1 высокой пропускной способности, ядро розничной ликвидности и DePIN активности", "Эмиссия инфляционных наград валидаторам", 73.0),
            ("NEAR", "NEAR Protocol", "AI & Chain Abstraction L1", "Watch", "Ведущий блокчейн в нарративе User-Owned AI и абстракции чейнов", "Конкуренция за разработчиков dApps", 72.0),
            ("PYTH", "Pyth Network", "Low-Latency Oracle Infra", "Watch", "Высокочастотные ценовые оракулы первого уровня для DeFi и деривативов", "Зависимость ценности токена от модели стейкинга", 71.5),
            ("JTO", "Jito Network", "Solana MEV & Liquid Staking", "Watch", "Монополист MEV-клиента и крупнейший LST-протокол на Solana", "Governance-heavy модель распределения наград", 71.0),
            ("MORPHO", "Morpho Labs", "Modular Lending Primitive", "Watch", "Модульный протокол изолированных кредитных рынков нового поколения", "Конкуренция с устоявшимися пулами Aave", 70.5),
            ("EIGEN", "EigenLayer", "Ethereum Restaking Infra", "Watch", "Базовый протокол коллективной криптоэкономической безопасности через restaking", "Медленный запуск монетизации AVS сервисов", 70.0),
            ("SAFE", "Safe", "Account Abstraction Infra", "Watch", "Стандарт мультисиг и смарт-аккаунтов институционального уровня", "Медленная трансляция сетевого эффекта в стоимость токена", 69.0),
            ("SEI", "Sei Network", "Parallelized EVM L1", "Watch", "Параллелизованный EVM первого уровня с высокой скоростью финализации", "Необходимость формирования устойчивого DeFi ландшафта", 68.5),
            ("TIA", "Celestia", "Modular DA Layer", "Watch", "Пионер модульной архитектуры и доступности данных (Data Availability)", "Крупные разблокировки токенов для ранних фондов", 67.0),
            ("W", "Wormhole", "Cross-chain Messaging Infra", "Watch", "Инфраструктурный стандарт кроссчейн-коммуникации и передачи сообщений", "Низкий захват ценности токеном при высоком FDV", 65.0),
        ]

        count = 0
        for symbol, name, sector, tier, thesis, cthesis, score in initial_projects:
            self.upsert_asset(
                symbol=symbol,
                name=name,
                sector=sector,
                tier=tier,
                thesis=thesis,
                counter_thesis=cthesis,
                score=score,
                status="Active" if tier != "Watch" else "Watchlist",
            )
            count += 1

        self.enforce_portfolio_limit()
        return count

    def generate_registry_markdown(self) -> Path:
        """Exports the entire portfolio registry into clean GitHub-flavored Markdown."""
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / "caf_portfolio_registry.md"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        active_portfolio = self.get_active_portfolio()
        all_assets = self.get_all_assets()
        watchlist = [a for a in all_assets if a["status"] != "Portfolio"]
        decisions = self.get_decisions(limit=10)

        lines = [
            "# CAF / CVE Portfolio & Incubator Registry",
            f"**Дата актуализации:** {now_str}  ",
            f"**Активов в активном портфеле:** {len(active_portfolio)} / {self.MAX_ACTIVE_PORTFOLIO} (Лимит: 20)  ",
            f"**Активов в списке наблюдения (Watchlist):** {len(watchlist)}  ",
            "",
            "## 💼 1. Активный инвестиционный портфель (Лимит: 20 активов)",
            "Правило Дарвина: при входе нового проекта с высоким баллом худший проект вытесняется в Watchlist.",
            "",
            "| Тикер | Проект | Сектор | Уровень | Целевая доля | Score | Тезис / Обоснование |",
            "|---|---|---|---|---|---|---|",
        ]

        tier_badges = {
            "Core": "🟢 **CORE**",
            "Core Candidate": "🟢 **CORE**",
            "High Conviction": "🔵 **HIGH CONVICTION**",
            "Invest": "🟡 **INCUBATOR**",
            "Incubator": "🟡 **INCUBATOR**",
            "Watch": "⚪ **WATCH**",
        }

        tier_allocations = {
            "Core": "~9.1% (55% пул)",
            "Core Candidate": "~9.1% (55% пул)",
            "High Conviction": "~3.75% (30% пул)",
            "Invest": "~2.5% (15% пул)",
            "Incubator": "~2.5% (15% пул)",
        }

        for a in active_portfolio:
            badge = tier_badges.get(a["tier"], a["tier"])
            alloc = tier_allocations.get(a["tier"], "—")
            score_str = f"**{a['score']:.1f}**" if a["score"] else "—"
            thesis_short = (a["thesis"][:80] + "...") if a["thesis"] and len(a["thesis"]) > 80 else (a["thesis"] or "—")
            lines.append(
                f"| `{a['symbol']}` | **{a['name']}** | {a['sector']} | {badge} | **{alloc}** | {score_str} | {thesis_short} |"
            )

        lines += [
            "",
            "---",
            f"## 📋 2. Резервная скамья и наблюдение (Watchlist — {len(watchlist)} активов)",
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
                "## 🏛️ Последние решения Инвестиционного Комитета",
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
                # clean newlines in markdown table cells
                cfo_clean = cfo_short.replace("\n", " ")
                lines.append(
                    f"| {d['created_at'][:16]} | **{d['name']}** (`{d['symbol']}`) | {d['signal_type']} | {v_badge} | {d['conviction_score']:.0f}% | {cfo_clean} |"
                )

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return report_path
