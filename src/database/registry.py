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
        - Core tier: top 6 assets (highest score) -> status='Portfolio'
        - High Conviction tier: top 8 assets -> status='Portfolio'
        - Incubator tier: top 6 assets -> status='Portfolio'
        - All other assets and excess projects get status='Watchlist'.
        """
        displaced = []
        with self._get_conn() as conn:
            cur = conn.cursor()

            # 1. Core candidates
            cur.execute("""
                SELECT symbol, name, score FROM assets 
                WHERE tier IN ('Core', 'Core Candidate')
                ORDER BY score DESC, symbol ASC
            """)
            cores = cur.fetchall()
            for idx, row in enumerate(cores):
                new_status = 'Portfolio' if idx < self.MAX_CORE_ASSETS else 'Watchlist'
                if idx >= self.MAX_CORE_ASSETS:
                    displaced.append({"symbol": row["symbol"], "tier": "Core", "displaced_to": "Watchlist"})
                cur.execute("UPDATE assets SET status = ? WHERE symbol = ?", (new_status, row["symbol"]))

            # 2. High Conviction candidates
            cur.execute("""
                SELECT symbol, name, score FROM assets 
                WHERE tier = 'High Conviction'
                ORDER BY score DESC, symbol ASC
            """)
            high_conv = cur.fetchall()
            for idx, row in enumerate(high_conv):
                new_status = 'Portfolio' if idx < self.MAX_HIGH_CONV_ASSETS else 'Watchlist'
                if idx >= self.MAX_HIGH_CONV_ASSETS:
                    displaced.append({"symbol": row["symbol"], "tier": "High Conviction", "displaced_to": "Watchlist"})
                cur.execute("UPDATE assets SET status = ? WHERE symbol = ?", (new_status, row["symbol"]))

            # 3. Incubator candidates (Invest / Incubator)
            cur.execute("""
                SELECT symbol, name, score FROM assets 
                WHERE tier IN ('Incubator', 'Invest')
                ORDER BY score DESC, symbol ASC
            """)
            incubators = cur.fetchall()
            for idx, row in enumerate(incubators):
                new_status = 'Portfolio' if idx < self.MAX_INCUBATOR_ASSETS else 'Watchlist'
                if idx >= self.MAX_INCUBATOR_ASSETS:
                    displaced.append({"symbol": row["symbol"], "tier": "Incubator", "displaced_to": "Watchlist"})
                cur.execute("UPDATE assets SET status = ? WHERE symbol = ?", (new_status, row["symbol"]))

            # 4. Watch tier is always Watchlist
            cur.execute("UPDATE assets SET status = 'Watchlist' WHERE tier = 'Watch'")

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

    def seed_from_conversation(self) -> int:
        """
        Seeds registry with all coins evaluated during the initial CAF/CVE analysis.
        """
        initial_projects = [
            # Candidates for Core / High Conviction
            ("TRAC", "OriginTrail", "Decentralized Knowledge Graph / AI", "Core Candidate", "Проверяемые данные и децентрализованный граф знаний для AI и корпораций", "Конкуренция со стороны централизованных графов знаний", 88.0),
            ("GEOD", "GEODNET", "DePIN / RTK Positioning", "Core Candidate", "DePIN для высокоточного позиционирования с подтвержденным коммерческим спросом, buyback & burn", "Зависимость от темпа физического развертывания базовых станций", 87.0),
            ("CFG", "Centrifuge", "RWA Infrastructure", "Core Candidate", "Базовый протокол для токенизации реальных активов и связки TradFi с DeFi", "Регуляторные риски и скорость внедрения институционалами", 86.0),
            ("SUI", "Sui", "Layer 1", "Core Candidate", "Высокопроизводительный L1 нового поколения на Move с сильной пропускной способностью", "Навес разлоков и жесткая конкуренция среди L1", 85.0),
            ("FLUID", "Fluid (Instadapp)", "DeFi Liquidity Layer", "Core Candidate", "Единый агрегированный слой ликвидности и кредитования DeFi с высокой капиталоэффективностью", "Конкуренция с монополистами lending-рынка (Aave, Morpho)", 85.0),
            ("MET", "Meteora", "Solana DEX Infra / DLMM", "Core Candidate", "Ликвидная инфраструктура Solana через динамические пулы DLMM", "Зависимость от экосистемы Solana и конкуренция с Raydium", 84.0),
            ("DEEP", "DeepBook Protocol", "CLOB DEX Infra", "Core Candidate", "Центральная книга ордеров Sui, глубокая интеграция в ядро сети, buyback & burn", "Прямая зависимость от активности на Sui", 84.0),
            ("SNX", "Synthetix", "Derivatives Infra", "Core Candidate", "Синтетические активы, v3 perpetuals и слой ликвидности деривативов", "Сложность модели и риск смарт-контрактов", 83.0),
            ("AR", "Arweave", "Decentralized Storage / AO", "Core Candidate", "Постоянное децентрализованное хранение данных и вычислительная среда AO", "Необходимость устойчивого коммерческого спроса", 83.0),
            ("AKT", "Akash Network", "DePIN / Cloud Compute", "High Conviction", "Децентрализованный маркетплейс вычислений и GPU для AI", "Конкуренция с централизованными облаками и Web2 агрегаторами", 81.0),
            ("RUNE", "THORChain", "Cross-chain Liquidity", "High Conviction", "Кроссчейн-обмен нативными активами без обёрток, прямой захват ценности через пул", "Исторические риски безопасности кроссчейн-маршрутизации", 80.0),
            ("RAY", "Raydium", "Solana DEX", "High Conviction", "Ключевой DEX Solana, агрегатор ликвидности мем-токенов и DLMM", "Высокая зависимость от мем-цикла Solana", 79.0),
            ("EIGEN", "EigenLayer", "Restaking", "High Conviction", "Базовый уровень коллективной криптоэкономической безопасности Ethereum через restaking", "Молодой рынок restaking, AVS еще не генерируют массовый денежный поток", 79.0),
            ("STRK", "Starknet", "Layer 2 ZK", "High Conviction", "Один из ключевых ZK L2 для Ethereum, уникальная виртуальная машина Cairo", "Высокая конкуренция среди L2, связь активности с ценностью токена еще доказывается", 78.0),
            ("GRT", "The Graph", "Web3 Indexing", "High Conviction", "Стандарт индексации данных блокчейнов для dApps", "Не до конца доказанная прямая связь роста запросов с ценностью токена", 78.0),
            ("ZAMA", "Zama", "FHE / Privacy", "High Conviction", "Инфраструктура конфиденциальных вычислений на полностью гомоморфном шифровании (FHE)", "Ранняя стадия технологии, тяжелые вычисления", 77.0),
            ("1INCH", "1inch", "DEX Aggregator", "High Conviction", "Ведущий DEX-агрегатор ликвидности и маршрутизации ордеров", "Слабый прямой захват ценности токеном (governance-heavy)", 76.0),
            ("KMNO", "Kamino Finance", "Solana DeFi", "High Conviction", "Ведущий протокол кредитования, автоматических хранилищ и левереджа на Solana", "Конкуренция внутри Solana, умеренный захват ценности", 76.0),
            ("GLM", "Golem", "Compute", "High Conviction", "Децентрализованный рынок вычислительных мощностей", "Необходимость подтверждения устойчивого спроса", 75.0),
            ("METIS", "Metis", "Layer 2", "High Conviction", "Ethereum L2 с децентрализованным секвенсором и AI-направлением", "Конкуренция с Arbitrum, Optimism, Base", 74.0),
            ("NEX", "Nexus", "Verifiable Compute", "High Conviction", "Инфраструктура для верифицируемых вычислений и ZK", "Ранняя стадия, навес будущих анлоков", 74.0),
            ("GRASS", "Grass", "DePIN / AI Data", "High Conviction", "Децентрализованная сеть веб-скрейпинга и данных для обучения AI моделей", "Юридические и операционные риски сбора веб-данных", 74.0),
            ("BEAM", "Beam", "Web3 Gaming Infra", "High Conviction", "Игровая экосистема и сеть на Avalanche для Web3 тайтлов", "Зависимость от успеха отдельных игровых студий", 73.0),
            ("NXPC", "NEXPACE", "Web3 Gaming / MapleStory", "High Conviction", "Web3-экономика на базе IP Nexon и MapleStory Universe", "Цикличность GameFi и удержание игроков", 73.0),
            ("H", "Humanity Protocol", "Identity / PoH", "High Conviction", "Инфраструктура цифровой идентичности с сохранением приватности", "Массовое внедрение еще предстоит доказать", 72.0),

            # Invest Tier
            ("TWT", "Trust Wallet Token", "Wallet Utility", "Invest", "Ключевой utility-токен популярного кошелька Trust Wallet", "Продукт успешен, но связь роста кошелька с токеном ограничена", 66.0),
            ("TEL", "Telcoin", "Mobile Payments", "Invest", "Инфраструктура для мобильных денежных переводов через сотовых операторов", "Зависимость от регулирования и конкуренция со стейблкоинами", 64.0),
            ("COMP", "Compound", "Lending", "Invest", "Проверенный временем протокол кредитования DeFi", "Слабая связь роста TVL с капитализацией токена управления", 63.0),
            ("IOTA", "IOTA", "IoT / RWA", "Invest", "Инфраструктура для интернета вещей и токенизации активов", "Долгий путь к массовому коммерческому принятию", 62.0),
            ("AXS", "Axie Infinity", "Gaming", "Invest", "Крупнейшая историческая Web3-игровая экосистема", "Цикличность Play-to-Earn и инфляция внутриигровой экономики", 60.0),
            ("APE", "ApeCoin", "NFT / Metaverse", "Invest", "Токен экосистемы Yuga Labs и метаверс-проектов", "Зависимость от хайпа NFT и отсутствие гарантированного денежного потока", 59.0),
            ("CHZ", "Chiliz", "Fan Tokens", "Invest", "Спортивная инфраструктура и фан-токены клубов", "Рынок фан-токенов узкий и спекулятивный", 58.0),
            ("MANA", "Decentraland", "Metaverse", "Invest", "Децентрализованный виртуальный мир", "Ограниченное удержание ежедневных пользователей", 56.0),
            ("SAND", "The Sandbox", "Metaverse", "Invest", "Метавселенная пользовательского контента", "Низкая активность вне маркетинговых сезонов", 56.0),
            ("NEO", "NEO", "Layer 1", "Invest", "Платформа смарт-контрактов китайской экосистемы, двухтокеновая модель", "Слабый глобальный сетевой эффект разработчиков", 57.0),
            ("SFP", "SafePal", "Hardware Wallet", "Invest", "Экосистема аппаратных и программных кошельков", "Токен не захватывает выручку от продажи физических кошельков", 62.0),
            ("BAT", "Basic Attention Token", "AdTech", "Invest", "Токен внимания внутри браузера Brave", "Рост браузера слабо транслируется в рост цены BAT", 61.0),
            ("GALA", "Gala Games", "Gaming", "Invest", "Игровая Web3 платформа и распределенная сеть нод", "Зависимость от выпуска хитовых игр и гиперинфляция наград", 58.0),
            ("EGLD", "MultiversX", "Layer 1", "Invest", "Высокоскоростной шардированный блокчейн", "Слабый сетевой эффект экосистемы разработчиков", 60.0),
            ("RSR", "Reserve Rights", "Stablecoin Infra", "Invest", "Протокол выпуска децентрализованных индексных стейблкоинов", "Сверхжесткая конкуренция с централизованными стейблкоинами", 61.0),
            ("ZEN", "Horizen", "ZK Sidechains", "Invest", "Масштабируемые блокчейн-приложения через ZK-сайдчейны", "Высокая конкуренция с новыми L2", 60.0),

            # Watch Tier
            ("WIF", "dogwifhat", "Meme", "Watch", "Мем-токен на Solana", "Полное отсутствие фундаментальной утилиты и ценности", 35.0),
            ("CHEEMS", "Cheems", "Meme", "Watch", "Мем-токен", "Спекулятивный хайп без ценности", 30.0),
            ("YZY", "Yeezy Money", "Celebrity / Brand", "Watch", "Платежный бренд-токен", "Экстремальная концентрация и репутационные риски", 25.0),
            ("Melania", "Melania", "Celebrity Meme", "Watch", "Медийный хайп", "Отсутствие продукта и экономической функции", 20.0),
            ("BANANAS31", "Banana for Scale", "Meme", "Watch", "Мем-токен", "Чистая спекуляция", 20.0),
            ("DATA", "Streamr DATA", "Data Monetization", "Watch", "Децентрализованный брокер данных", "Отсутствие массового коммерческого спроса", 42.0),
            ("ATH", "Aethir", "Compute / GPU", "Watch", "Рынок GPU для игр и AI", "Сомнительная экономическая устойчивость наград", 45.0),
            ("ORDI", "ORDI", "BRC-20", "Watch", "Первый токен стандарта BRC-20 на Bitcoin", "Спекулятивный нарратив без утилиты", 40.0),
            ("UNFI", "Unifi Protocol", "DeFi", "Watch", "Мультичейн DeFi протокол", "Слабая ликвидность и низкая активность", 38.0),
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
