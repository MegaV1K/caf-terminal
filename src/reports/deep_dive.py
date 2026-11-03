"""
Deep-Dive Factsheet & Institutional Dossier Generator.
Implements the 10-pillar research methodology:
1. Founders, Team & Backers (Engineering credibility, funding rounds, reputation)
2. Tokenomics & Vesting Pressure (Total/Circulating supply, insider share, unlocks)
3. Utility & Real Value Capture (Gas, Staking, Fee-switch, Buyback vs Governance)
4. Product-Market Fit & Onchain Metrics (TVL, volume, active users, dApps)
5. Roadmap & Technological Catalysts (ZK, subnets, modularity, new primitives)
6. Liquidity & Market Depth (CEX/DEX volume, slippage risk, market makers)
7. Red Flags & Structural Risks (Corporate pre-farm, central sequencer, regulatory)
8. Competitive Landscape (Direct/Indirect rivals, moats, displacement threats)
9. Narrative Alignment & Market Mindshare (L2, AI, DePIN, RWA cycle timing)
10. Final Institutional Verdict & CAF Matrix Placement
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from config import REPORTS_DIR
from src.ai.gemini_client import generate
from src.scouts.coingecko import CoinGeckoScout
from src.scouts.defillama import DefiLlamaScout
from src.scouts.github import GitHubScout
from src.scoring.caf_scorer import CAFScorer


class DeepDiveEngine:
    """Generates a complete 10-point institutional research dossier for any crypto asset."""

    SYSTEM_PROMPT = """Ты — ведущий институциональный криптоаналитик CAF (Crypto Asset Framework).
Твоя задача: составить исчерпывающее, строго фактологическое досье по проекту по 10 ключевым разделам.
Не используй маркетинговые штампы. Оценивай суровым взглядом управляющего фондом.

СТРУКТУРА ДОСЬЕ (СТРОГО 10 РАЗДЕЛОВ):

# 🧱 1. Founders, Team & Investors
- Кто основал проект (фаундеры, инженерный/научный бэкграунд, репутация в криптографии/P2P).
- Кто инвесторы (венчурные раунды, сумма привлеченных средств, tier фондов: a16z, Paradigm, Polychain и др.).
- Юридическая структура (децентрализованное DAO, швейцарский фонд или коммерческая корпорация типа Matter Labs / Chia Network Inc.).

# 🪙 2. Tokenomics & Dilution Overhang
- Total Supply, Circulating Supply и процент в свободном обращении (Float %).
- Доля инвесторов и команды (Insiders %).
- График разблокировок (Cliff, линейный вестинг, ежемесячное инфляционное давление в $).
- Текущая оценка: Market Cap vs FDV (насколько FDV оторван от реальности).

# 🧩 3. Real Utility & Value Capture (EVC)
- Роль токена: Газ, Стейкинг для безопасности, Fee Switch, Buyback & Burn или исключительно бесполезный Governance?
- Куда физически идут комиссии протокола (валидаторам, разработчикам, в казначейство или на выкуп токена)?
- Статус Economic Value Capture: доказанный денежный поток или пустые декларации.

# 📈 4. PMF, Adoption & Onchain Metrics
- В чем конкретно заключается Product-Market Fit (решает ли протокол реальную боль пользователей/разработчиков).
- Фактические метрики: TVL, суточный объем торгов, суточная выручка, количество dApps и активных адресов.
- Качество активности (органика vs накрутка поинт-фермерами).

# 🗺 5. Roadmap & Technological Catalysts
- Ключевые технологические апгрейды (ZK-стек, параллелизация, децентрализация сиквенсера, кастомные VM).
- Что может стать драйвером переоценки актива на горизонте 12–24 месяцев.

# 💧 6. Liquidity & Trading Profile
- Где торгуется (Tier-1 CEX: Binance, Coinbase, Bybit vs ончейн DEX).
- Доступная ликвидность и проскальзывание (slippage) для институционального объема ($50k–$200k).

# ⚠️ 7. Red Flags & Structural Risks
- Корпоративный контроль и Pre-farm (принадлежит ли значительная часть эмиссии одному юрлицу).
- Централизация сиквенсера/валидаторов.
- Совместимость кода (проблемы неполной EVM-совместимости, сложность миграции разработчиков).
- Регуляторные риски и претензии SEC/MiCA.

# 🥊 8. Competitive Landscape & Moat
- Прямые конкуренты (кто делает то же самое лучше, быстрее или дешевле).
- Наличие защитного рва (Network Effects, технологический отрыв, патенты, ликвидность).
- Риск вытеснения более сильными экосистемами (Solana, Base, Hyperliquid).

# 📣 9. Narrative Alignment & Mindshare
- В какие макро-нарративы попадает актив (L2, AI Agentic, RWA, DePIN, Interoperability).
- Внимание рынка: находится ли проект в фокусе или забыт рынком («зомби-чейн»).

# 🧾 10. Institutional Verdict & CAF Classification
- Итоговая оценка по шкале CAF (0–100).
- Рекомендуемый статус: CORE (Ядро) | HIGH CONVICTION | INCUBATOR (Карантин) | PASS / WATCHLIST (Отказ).
- Резюме решения в 3–4 предложениях.

Пиши на чистом русском языке, четко, без воды, с акцентом на цифры и риски."""

    def __init__(self, output_dir: Path = REPORTS_DIR):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cg = CoinGeckoScout()
        self.llama = DefiLlamaScout()
        self.github = GitHubScout()

    def generate_dossier(
        self,
        symbol: str,
        name: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Path:
        sym = symbol.upper().strip()
        print(f"\n[DEEP-DIVE] Сбор ончейн-данных и рыночных метрик для {sym}...")

        # 1. Fetch market data
        markets = self.cg.fetch_markets(pages=3, force_refresh=force_refresh)
        metrics = self.cg.get_token_metrics(markets).get(sym, {})

        # 2. Fetch DeFi data
        protocols = self.llama.fetch_protocols(force_refresh=force_refresh)
        fees_data = self.llama.fetch_fees_and_revenue(force_refresh=force_refresh)

        proto = None
        for p in protocols:
            if (p.get("symbol") or "").upper() == sym:
                proto = p
                break

        daily_fees = 0.0
        daily_revenue = 0.0
        if proto:
            proto_id = str(proto.get("id") or "")
            name_lc = (proto.get("name") or "").lower()
            for fp in fees_data.get("protocols", []):
                if str(fp.get("defillamaId") or "") == proto_id or (fp.get("name") or "").lower() == name_lc:
                    daily_fees = float(fp.get("total24h") or 0)
                    daily_revenue = float(fp.get("totalRevenue24h") or 0)
                    break

        # 3. Fetch GitHub data
        repo = self.github.get_repo_for_symbol(sym)
        git_metrics = {}
        if repo:
            git_metrics = self.github.fetch_repo_metrics(repo)

        # 4. Calculate automated CAF score as foundation
        score_payload = {
            "symbol": sym,
            "name": name or metrics.get("name") or (proto.get("name") if proto else sym),
            "category": (proto.get("category") if proto else "Infrastructure"),
            "mcap": metrics.get("mcap") or (proto.get("mcap") if proto else 0),
            "fdv": metrics.get("fdv"),
            "fdv_mcap_ratio": metrics.get("fdv_mcap_ratio"),
            "tvl": proto.get("tvl") if proto else 0,
            "daily_fees": daily_fees,
            "daily_revenue": daily_revenue,
            "chains": proto.get("chains", []) if proto else [],
            "rank": metrics.get("rank") or 999,
        }
        caf_eval = CAFScorer.calculate_cve_score(score_payload)

        fdv_val = score_payload.get('fdv')
        fdv_str = f"${fdv_val:,.0f}" if fdv_val else "N/A"
        mcap_val = score_payload.get('mcap') or 0
        tvl_val = score_payload.get('tvl') or 0

        # Format input context for LLM
        prompt_context = (
            f"ТИКЕР: {sym}\n"
            f"ИМЯ: {score_payload['name']}\n"
            f"СЕКТОР: {score_payload['category']}\n"
            f"РЫНОЧНЫЙ РАНГ: #{score_payload['rank']}\n"
            f"CAPITALIZATION (MCap): ${mcap_val:,.0f}\n"
            f"FDV: {fdv_str}\n"
            f"FDV/MCAP RATIO: {score_payload.get('fdv_mcap_ratio') or 'N/A'}\n"
            f"TVL: ${tvl_val:,.0f}\n"
            f"24h FEES: ${daily_fees:,.0f}\n"
            f"24h REVENUE: ${daily_revenue:,.0f}\n"
            f"CHAINS: {', '.join(score_payload['chains']) or 'N/A'}\n"
            f"GITHUB DEV SCORE: {git_metrics.get('dev_score', 'N/A')}/100 (Commits 30d: {git_metrics.get('commits_30d', 'N/A')}, Repo: {repo or 'N/A'})\n"
            f"БАЗОВЫЙ CAF СКОРИНГ:\n"
            f"- Composite Score: {caf_eval['composite_score']}/100 ({caf_eval['tier']})\n"
            f"- Business Quality: {caf_eval['pillars']['business_quality']}\n"
            f"- Value Capture (EVC): {caf_eval['pillars']['value_capture']}\n"
            f"- Tokenomics: {caf_eval['pillars']['tokenomics']}\n"
            f"- Resilience: {caf_eval['pillars']['resilience']}\n"
            f"- Safety: {caf_eval['pillars']['safety_anti_fragility']}\n"
        )

        print("[DEEP-DIVE] Генерация институционального досье по 10-пунктовому стандарту...")
        dossier_text = generate(prompt_context, system_instruction=self.SYSTEM_PROMPT)

        # Write to Markdown
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        file_ts = datetime.now().strftime("%Y-%m-%d_%H%M")
        report_path = self.output_dir / f"deep_dive_{sym.lower()}_{file_ts}.md"

        full_md = (
            f"# 📋 Институциональное Досье CAF: {score_payload['name']} ({sym})\n\n"
            f"**Дата анализа:** {now_str}  \n"
            f"**Категория:** {score_payload['category']} | **Ранг:** #{score_payload['rank']}  \n"
            f"**Базовый CVE Score:** {caf_eval['composite_score']}/100 ({caf_eval['tier']})  \n\n"
            f"---\n\n"
            f"{dossier_text}\n"
        )

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(full_md)

        print(f"[OK] Досье успешно сохранено в: {report_path}")
        return report_path
