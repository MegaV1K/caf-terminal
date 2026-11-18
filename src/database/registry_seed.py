"""
Seed initial portfolio for CAF / CVE Investment Registry.
Implements modern October 2026 asset allocation with risk clusters.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.database.registry import CAFRegistry


def seed_initial_portfolio(registry: "CAFRegistry", clear_existing: bool = True) -> int:
    """
    Seeds registry with modern October 2026 CAF/CVE investment portfolio from scratch.
    Implements dynamic risk-adjusted target weights, correlation cluster caps,
    and eliminates all legacy zombie tokens.
    """
    if clear_existing:
        with registry._get_conn() as conn:
            conn.execute("DELETE FROM assets")
            conn.commit()

    initial_projects = [
        # 1. CORE TIER (50.0% Capital, 6 Assets, Range: 6.0% - 11.0%)
        ("HYPE", "Hyperliquid", "Perp DEX / Sovereign L1", "Sovereign L1 / CLOB", "Core", "Крупнейший ончейн-ордербук бессрочных фьючерсов с суверенным L1, рекордный ончейн-кэшфлоу ($500M+ годовых сборов), Assistance Fund выкупает HYPE с открытого рынка, 0% венчурных анлоков", "Риск регуляторного давления на деривативы и децентрализацию валидаторов", 89.5, 11.0),
        ("AAVE", "Aave", "DeFi Lending Monopoly", "Ethereum DeFi / Lending", "Core", "Абсолютный гегемон кредитования в Web3 (TVL > $20B), запущенный fee switch и действующая программа выкупа AAVE из протокольной выручки до $50M/год с еженедельными покупками", "Риск появления протоколов с изолированной ликвидностью нового поколения (Fluid, Morpho)", 88.5, 10.5),
        ("RAY", "Raydium", "Solana DEX Infra", "Solana Ecosystem", "Core", "Рекордный чистый кэшфлоу ($260M годовых сборов), 12% байбэк ($31M/год) превышает эмиссию ($3.3M/год) почти в 10 раз, 0% венчурных анлоков (вестинг завершен в феврале 2024)", "Высокая цикличность и зависимость от спекулятивного объема Solana", 88.0, 8.5),
        ("JUP", "Jupiter", "Solana Super-App / DEX", "Solana Ecosystem", "Core", "Финансовый хаб Solana ($210M годовых сборов), 50% байбэк ($105M/год) в Litterbox Trust, принята политика Net-Zero Emissions (анлоки команды заморожены)", "Риск снижения активности на Solana", 86.5, 7.5),
        ("TAO", "Bittensor", "Decentralized AI / Subnets", "AI & Compute", "Core", "Базовый товарный слой машинного интеллекта, halving пройден в декабре 2025 (эмиссия 0.5 TAO/блок, max 21M TAO), лидер децентрализованного AI", "Сложность субсетей и отсутствие корпоративных дивидендов", 86.0, 6.5),
        ("SOL", "Solana", "High-Throughput L1", "Solana Ecosystem", "Core", "Базовый L1 высокой пропускной способности, ядро розничной ликвидности и DePIN активности, 50% сжигание базовых транзакционных комиссий сети", "Эмиссия инфляционных наград валидаторам (~5% в год)", 85.5, 6.0),

        # 2. HIGH CONVICTION TIER (30.0% Capital, 8 Assets, Range: 3.0% - 5.0%)
        ("PENDLE", "Pendle Finance", "Yield Stripping / DeFi", "DeFi Yield Trading", "High Conviction", "Монополия на рынке ончейн-доходности, модель AIM снизила эмиссию до 0.2%/год, 80% байбэк опережает выпуск в 8-10 раз, вестинг инвесторов завершен", "Зависимость от циклов доходности на более широком рынке DeFi", 85.0, 5.0),
        ("FLUID", "Fluid (Instadapp)", "DeFi Liquidity Layer", "Ethereum DeFi / Lending", "High Conviction", "$44M годовых сборов ($3.65M/мес), преодолен порог $10M для алгоритмического выкупа токенов, 83.7% предложения в обращении", "Конкуренция с устоявшимися пулами Aave", 84.0, 4.5),
        ("COW", "CoW Protocol", "MEV-Protected DEX Aggregator", "Ethereum DeFi / Lending", "High Conviction", "Подтвержденный кэшфлоу ($24M годовых сборов), еженедельный TWAP-выкуп COW из сборов за MEV-защиту, 1B hard cap", "Зависимость от объемов торговли на Ethereum и Gnosis", 83.5, 4.0),
        ("SUI", "Sui", "Layer 1 Move", "Sui Ecosystem", "High Conviction", "Самый быстрорастущий L1 нового поколения на языке Move, высокая реальная пропускная способность, институциональный приток ликвидности, блокировка в Storage Fund", "График инфляционных разблокировок токенов до 2030 года", 83.5, 4.0),
        ("AERO", "Aerodrome", "Base DEX Infra", "Base Ecosystem", "High Conviction", "Доминирующий DEX на Base (Coinbase экосистема), 100% торговых комиссий и bribes распределяются держателям veAERO", "Инфляция эмиссии по модели ve(3,3)", 83.0, 3.5),
        ("SKY", "Sky (MakerDAO)", "Decentralized Stablecoin & Debt", "RWA", "High Conviction", "Крупнейший эмитент децентрализованного стейблкоина ($200M+ выручки), Smart Burn Engine сжигает SKY/MKR из стабильных сборов и US Treasuries, 100% supply", "Регуляторный комплаенс и freeze-функция в USDS", 82.0, 3.0),
        ("ENA", "Ethena", "Synthetic Dollar / Basis Trade", "DeFi Synthetic Dollar", "High Conviction", "Синтетический доллар USDe, $215M годовых сборов на базисной торговле, утвержденный фреймворк выкупа 95% выручки", "Риск отрицательных ставок фандинга и задержка активации выкупа до $7.5B supply", 81.5, 3.0),
        ("TRAC", "OriginTrail", "Decentralized Knowledge Graph", "Knowledge / AI Data", "High Conviction", "Фиксированный supply 500M, 0% инфляции, 100% в обращении, ~20% заблокировано в DKG нодах под утилити, проверенные корпоративные партнерства", "Микроскопический объем сборов в фиатном выражении", 81.0, 3.0),

        # 3. INCUBATOR TIER (5.5% Capital, 3 Assets, Range: 1.5% - 2.5%)
        ("INJ", "Injective", "Financial L1 / CLOB", "Sovereign L1 / CLOB", "Invest", "100% токенов в обращении, 0 будущих разблокировок, еженедельный ончейн-аукцион сжигания 60% комиссий экосистемных dApps", "Конкуренция за ликвидность с Solana и L2", 79.5, 2.5),
        ("GMX", "GMX", "Real Yield Perp DEX", "Ethereum DeFi / Lending", "Invest", "Пионер модели Real Yield ($66M годовых сборов на Arbitrum и Solana), 27% всех сборов направляются на выкуп GMX в казначейство, низкий P/Fees ~1.2x", "Конкуренция со стороны L1-ордербуков нового поколения (Hyperliquid)", 77.5, 1.5),
        ("SYRUP", "Maple Finance", "Institutional Credit & Yield", "RWA", "Invest", "Крупнейший институциональный кредитный пул ($1.9B займов, $103M годовых сборов), 20-25% сборов займов выкупают SYRUP для stSYRUP (MIP-021)", "Кредитный хвостовой риск дефолта институциональных заемщиков", 77.0, 1.5),

        # 4. WATCHLIST / RADAR (Вес 0.0%, статус Watchlist)
        ("GEOD", "GEODNET", "DePIN / RTK Positioning", "DePIN Physical Infra", "Watch", "Заморожен по PriceTrendGate: просадка -37%, устойчивый даунтренд. Капитал переведён в USDC_RESERVE", "Низкая ликвидность на Tier-1, риск дальнейшего дрейфа цены", 72.0, 0.0),
        ("AKT", "Akash Network", "DePIN / GPU Cloud", "AI & Compute", "Watch", "Дисквалифицирован по HardInflationGate: эмиссия ($33.5M/год) превышает реальные сборы ($2.7M/год) в 12.4x. Переведён в Short Radar", "Структурное размытие стакана инфляцией наград валидаторам", 65.0, 0.0),
        ("RENDER", "Render Network", "DePIN / GPU Rendering & AI", "AI & Compute", "Watch", "Дисквалифицирован по HardInflationGate: эмиссия наград нодам ($20M/год) превышает сборы рендеринга ($4.5M/год) в 4.4x. Переведён в Short Radar", "Несбалансированная BME модель с постоянным давлением продаж", 66.0, 0.0),
        ("DEEP", "DeepBook Protocol", "CLOB DEX Infra", "Sui Ecosystem", "Watch", "Центральная книга ордеров на Sui", "EVC = 0.6%: сборы $39k/мес не способны абсорбировать навес разблокировки $80M+/год", 55.0, 0.0),
        ("ONDO", "Ondo Finance", "RWA / Tokenized Treasuries", "RWA", "Watch", "Лидер RWA, но токен чисто управленческий", "EVC = 0: выручка фонда остается в Ondo Finance Inc., отсутствует fee-switch или байбэк", 62.0, 0.0),
        ("GRASS", "Grass", "DePIN / AI Web Scraping", "AI & Compute", "Watch", "Сеть сбора данных для AI", "EVC = 0: коммерческая выручка Grass DataCo отделена от токена, тяжелый навес разблокировок", 60.0, 0.0),
        ("DRIFT", "Drift Protocol", "Solana Perps & Prediction", "Solana Ecosystem", "Watch", "DEX деривативов на Solana", "Байбэк не активирован в коде, утилити ограничена торговыми скидками", 64.0, 0.0),
        ("KMNO", "Kamino Finance", "Solana DeFi Liquidity", "Solana Ecosystem", "Watch", "Кредитный хаб Solana", "EVC = 0: процентный спред оседает в казначействе DAO без прямого байбэка", 63.0, 0.0),
        ("ATH", "Aethir", "DePIN / Enterprise Cloud", "AI & Compute", "Watch", "Корпоративная GPU сеть", "EVC = 0: выкуп нод оплачивался новыми токенами, тяжелая эмиссия наград", 58.0, 0.0),
        ("NEAR", "NEAR Protocol", "AI & Chain Abstraction L1", "AI & Compute", "Watch", "Ведущий блокчейн в нарративе User-Owned AI и абстракции чейнов", "Сжигание газа покрывает менее 0.5% от 5% годовой инфляции", 72.0, 0.0),
        ("PYTH", "Pyth Network", "Low-Latency Oracle Infra", "Solana Ecosystem", "Watch", "Высокочастотные ценовые оракулы первого уровня для DeFi и деривативов", "Зависимость ценности токена от модели стейкинга", 71.5, 0.0),
        ("JTO", "Jito Network", "Solana MEV & Liquid Staking", "Solana Ecosystem", "Watch", "Монополист MEV-клиента и крупнейший LST-протокол на Solana", "Governance-heavy модель распределения наград", 71.0, 0.0),
        ("MORPHO", "Morpho Labs", "Modular Lending Primitive", "Ethereum DeFi / Lending", "Watch", "Модульный протокол изолированных кредитных рынков нового поколения", "Fee switch не активирован на уровне протокола", 70.5, 0.0),
        ("EIGEN", "EigenLayer", "Ethereum Restaking Infra", "Ethereum DeFi / Lending", "Watch", "Базовый протокол коллективной криптоэкономической безопасности через restaking", "Медленный запуск монетизации AVS сервисов", 70.0, 0.0),
        ("SAFE", "Safe", "Account Abstraction Infra", "Ethereum DeFi / Lending", "Watch", "Стандарт мультисиг и смарт-аккаунтов институционального уровня", "Медленная трансляция сетевого эффекта в стоимость токена", 69.0, 0.0),
        ("GNS", "Gains Network", "Decentralized Perps / gTrade", "Ethereum DeFi / Lending", "Watch", "Перп-DEX с устойчивым денежным потоком ($6M-$10M/год сборов) при микрокапе $10M, модель Buyback & Burn и стейкинг", "Конкуренция с Hyperliquid и L1 ордербуками нового поколения", 76.0, 0.0),
        ("JUSD", "JUSD Finance", "Basis Trading / Private Credit", "DeFi Synthetic Dollar", "Watch", "Дельта-нейтральный базис-трейдинг и структурированная доходность в связке с Accountable", "Риск заёмщиков частных кредитных пулов и короткая история работы", 65.0, 0.0),
        ("SEI", "Sei Network", "Parallelized EVM L1", "Other L1", "Watch", "Параллелизованный EVM первого уровня с высокой скоростью финализации", "Необходимость формирования устойчивого DeFi ландшафта", 68.5, 0.0),
        ("TIA", "Celestia", "Modular DA Layer", "Modular Infra", "Watch", "Пионер модульной архитектуры и доступности данных (Data Availability)", "Крупные разблокировки токенов для ранних фондов", 67.0, 0.0),
        ("W", "Wormhole", "Cross-chain Messaging Infra", "Cross-chain Infra", "Watch", "Инфраструктурный стандарт кроссчейн-коммуникации и передачи сообщений", "Низкий захват ценности токеном при высоком FDV", 65.0, 0.0),
        ("ZK", "zkSync", "ZK-Rollup Layer 2", "Ethereum DeFi / Lending", "Watch", "Флагманский ZK-rollup от Matter Labs ($458M VC), сильная криптографическая база и ZK-Stack", "Токеномика: 40% инсайдерам, огромный FDV, токен не используется для газа (EVC = 0)", 64.0, 0.0),
        ("ARB", "Arbitrum", "Optimistic Rollup Layer 2", "Ethereum DeFi / Lending", "Watch", "Лидер L2 по TVL ($3B+) и сборам, развитая экосистема Stylus и Orbit", "Токен чисто управленческий (газ в ETH), долгосрочный навес разблокировок DAO/инвесторов", 72.0, 0.0),
        ("ICP", "Internet Computer", "Onchain Cloud / Sovereign L1", "Other L1", "Watch", "Амбициозное децентрализованное облако от DFINITY Foundation, прямой utility через сжигание cycles", "Умеренный розничный adoption, сильная зависимость от привлечения энтерпрайз-разработчиков", 66.0, 0.0),
        ("XCH", "Chia Network", "Proof-of-Space-and-Time L1", "Other L1", "Watch", "Зелёный консенсус Брэма Коэна (BitTorrent), фокус на RWA и институциональные карбоновые рынки", "Корпоративный pre-farm под контролем юрлица Chia Network Inc., слабый розничный DeFi-спрос", 55.0, 0.0),
    ]

    count = 0
    for symbol, name, sector, cluster, tier, thesis, cthesis, score, weight in initial_projects:
        registry.upsert_asset(
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

    registry.enforce_portfolio_limit()
    return count
