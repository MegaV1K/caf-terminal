import argparse
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.scouts.defillama import DefiLlamaScout
from src.scouts.coingecko import CoinGeckoScout
from src.scoring.caf_scorer import CAFScorer
from src.reports.report_generator import ReportGenerator
from src.ai.llm_agent import LLMAgent


def run_emerging_radar(top_n: int = 15, force_refresh: bool = False):
    """Executes the Emerging / Incubator Radar search."""
    print("\n" + "=" * 60)
    print("[RADAR] ЗАПУСК РАДАРА: ПОИСК EMERGING / INCUBATOR ПРОЕКТОВ")
    print("=" * 60)

    scout = DefiLlamaScout()
    candidates = scout.get_emerging_candidates(
        min_tvl=1_000_000,
        max_mcap=800_000_000,
        min_change_7d=5.0,
    )

    if not candidates:
        print("[!] Не удалось найти кандидатов по заданным критериям.")
        return

    print(f"[+] Найдено {len(candidates)} потенциальных проектов. Расчет скоринга...")
    for c in candidates:
        c["radar_score"] = CAFScorer.score_emerging_candidate(c)

    # Sort by radar score descending
    candidates.sort(key=lambda x: x["radar_score"], reverse=True)

    print("\n" + "-" * 75)
    print(f"{'#':<3} {'Тикер':<8} {'Проект':<22} {'Сектор':<15} {'TVL':<12} {'7d TVL':<8} {'Score':<6}")
    print("-" * 75)

    for i, c in enumerate(candidates[:top_n], start=1):
        tvl_str = f"${c['tvl']:,.0f}" if c.get('tvl') else "—"
        c7d = c.get('change_7d', 0)
        c7d_str = f"+{c7d:.1f}%" if c7d > 0 else f"{c7d:.1f}%"
        name_short = (c['name'][:20] + "..") if len(c['name']) > 20 else c['name']
        print(f"{i:<3} {c['symbol']:<8} {name_short:<22} {c['category'][:14]:<15} {tvl_str:<12} {c7d_str:<8} {c['radar_score']:<6}")

    # Generate AI Summary
    llm = LLMAgent()
    ai_summary = llm.summarize_candidates(candidates[:top_n])
    
    print("\n" + "*" * 60)
    print("🤖 АНАЛИТИКА ОТ AI (GEMINI):")
    print("*" * 60)
    print(ai_summary)

    # Generate Reports
    reporter = ReportGenerator()
    report_file = reporter.generate_emerging_radar_report(candidates, top_n=top_n, ai_summary=ai_summary)
    print("\n" + "=" * 60)
    print(f"[OK] Отчет сохранен в файл: {report_file}")
    print("=" * 60)


def run_cve_scoring(tokens_list: list = None, force_refresh: bool = False):
    """Scores key tokens from the CVE portfolio / conversation."""
    print("\n" + "=" * 60)
    print("[CVE] СКОРИНГ ПРОЕКТОВ ПО МЕТОДОЛОГИИ CVE (5 СТОЛПОВ)")
    print("=" * 60)

    # Key tokens from the conversation
    default_tokens = [
        "SUI", "RAY", "STRK", "EIGEN", "GRT", "RUNE", "AKT", "CVX",
        "AR", "1INCH", "CFG", "SNX", "KMNO", "METIS", "GRASS", "BEAM"
    ]
    tokens = tokens_list or default_tokens

    cg_scout = CoinGeckoScout()
    llama_scout = DefiLlamaScout()

    print("[1/3] Загрузка рыночных метрик с CoinGecko...")
    markets = cg_scout.fetch_markets(pages=3, force_refresh=force_refresh)
    token_metrics = cg_scout.get_token_metrics(markets)

    print("[2/3] Загрузка ончейн-данных с DefiLlama...")
    protocols = llama_scout.fetch_protocols(force_refresh=force_refresh)
    fees = llama_scout.fetch_fees_and_revenue(force_refresh=force_refresh)

    # Map protocols by symbol
    proto_by_symbol = {}
    for p in protocols:
        sym = (p.get("symbol") or "").upper()
        if sym and sym not in proto_by_symbol:
            proto_by_symbol[sym] = p

    print("[3/3] Расчет 5-столпового CVE скоринга...")
    scores = []
    for sym in tokens:
        sym_upper = sym.upper()
        cg_data = token_metrics.get(sym_upper, {})
        llama_data = proto_by_symbol.get(sym_upper, {})

        combined = {
            "symbol": sym_upper,
            "name": cg_data.get("name") or llama_data.get("name") or sym_upper,
            "category": llama_data.get("category") or "Layer 1 / Infrastructure",
            "rank": cg_data.get("rank") or 999,
            "mcap": cg_data.get("mcap") or llama_data.get("mcap"),
            "fdv": cg_data.get("fdv"),
            "fdv_mcap_ratio": cg_data.get("fdv_mcap_ratio"),
            "tvl": llama_data.get("tvl"),
            "chains": llama_data.get("chains", []),
        }

        score_res = CAFScorer.calculate_cve_score(combined)
        scores.append(score_res)

    scores.sort(key=lambda x: x["composite_score"], reverse=True)

    print("\n" + "-" * 85)
    print(f"{'#':<3} {'Тикер':<8} {'Проект':<18} {'Уровень':<18} {'Score':<7} {'BQ':<6} {'EVC':<6} {'T':<6} {'R':<6} {'Safety':<6}")
    print("-" * 85)

    for i, s in enumerate(scores, start=1):
        p = s["pillars"]
        print(f"{i:<3} {s['symbol']:<8} {s['name'][:16]:<18} {s['tier']:<18} {s['composite_score']:<7} {p['business_quality']:<6} {p['value_capture']:<6} {p['tokenomics']:<6} {p['resilience']:<6} {p['safety_anti_fragility']:<6}")

    reporter = ReportGenerator()
    report_file = reporter.generate_cve_scoring_report(scores)
    print("\n" + "=" * 60)
    print(f"[OK] Итоговый CVE отчет сохранен в: {report_file}")
    print("=" * 60)


def run_committee(max_candidates: int = 5, force_refresh: bool = False):
    """Runs the 3-agent Investment Committee monthly scan."""
    from src.ai.committee import InvestmentCommittee
    from src.reports.committee_report import CommitteeReportGenerator

    print("\n" + "=" * 60)
    print("[COMMITTEE] ИНВЕСТИЦИОННЫЙ КОМИТЕТ: ЕЖЕМЕСЯЧНЫЙ СКАН")
    print("=" * 60)
    print("Агенты: Analyst (тезис) | Skeptic (критика) | CFO (решение)")
    print(f"Кандидатов на рассмотрение: топ-{max_candidates} по силе сигнала")
    print("=" * 60)

    # 1. Fetch on-chain protocols & fees (DefiLlama)
    print("\n[1/3] Загрузка ончейн-протоколов и сборов с DefiLlama...")
    llama = DefiLlamaScout()
    protocols = llama.fetch_protocols(force_refresh=force_refresh)
    fees_data = llama.fetch_fees_and_revenue(force_refresh=force_refresh)

    fees_by_name = {}
    for p in fees_data.get("protocols", []):
        fees_by_name[(p.get("name") or "").lower()] = p

    for p in protocols:
        name_key = (p.get("name") or "").lower()
        fee_info = fees_by_name.get(name_key, {})
        if fee_info:
            p["daily_fees"] = fee_info.get("total24h")
            p["daily_revenue"] = fee_info.get("totalRevenue24h")

    # 2. Fetch market volume anomalies & trending (CoinGecko)
    print("[2/3] Загрузка объемов и трендовых нарративов с CoinGecko...")
    cg = CoinGeckoScout()
    cg_markets = cg.fetch_markets(pages=2, force_refresh=force_refresh)
    volume_anomalies = cg.get_volume_anomalies(markets=cg_markets)
    trending_coins = cg.fetch_trending(force_refresh=force_refresh)

    # 3. Setup GitHub developer activity scout
    print("[3/3] Подключение анализа активности разработчиков (GitHub)...")
    from src.scouts.github import GitHubScout
    github_scout = GitHubScout()

    # Run committee
    committee = InvestmentCommittee()
    reports = committee.run_monthly_scan(
        protocols=protocols,
        volume_anomalies=volume_anomalies,
        trending_coins=trending_coins,
        github_scout=github_scout,
        max_candidates=max_candidates,
    )

    if not reports:
        print("[!] Комитет не нашел достаточно сильных сигналов в этом месяце.")
        return

    # Save report
    generator = CommitteeReportGenerator()
    report_path = generator.generate(reports)

    # Print summary
    print("\n" + "=" * 60)
    print("[ИТОГ КОМИТЕТА]")
    print("=" * 60)
    verdicts = {"FULL_CAF": [], "INCUBATOR": [], "PASS": []}
    for r in reports:
        verdicts[r.verdict.value].append(f"{r.signal.name} ({r.signal.symbol})")

    if verdicts["FULL_CAF"]:
        print(f"[!] СРОЧНЫЙ АНАЛИЗ: {', '.join(verdicts['FULL_CAF'])}")
    if verdicts["INCUBATOR"]:
        print(f"[~] ИНКУБАТОР:      {', '.join(verdicts['INCUBATOR'])}")
    if verdicts["PASS"]:
        print(f"[-] ПРОПУСТИТЬ:     {', '.join(verdicts['PASS'])}")

    print(f"\n[OK] Полный отчет сохранен в: {report_path}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="CAF-Terminal: Automated Radar & CVE Scoring")
    parser.add_argument("--radar",     action="store_true", help="Запустить поиск Emerging/Incubator проектов")
    parser.add_argument("--cve",       action="store_true", help="Запустить CVE скоринг ключевых активов")
    parser.add_argument("--committee", action="store_true", help="Запустить 3-агентный инвестиционный комитет")
    parser.add_argument("--refresh",   action="store_true", help="Игнорировать кэш и обновить данные")
    parser.add_argument("--top",       type=int, default=15, help="Количество проектов в радаре (по умолчанию: 15)")
    parser.add_argument("--candidates",type=int, default=5,  help="Сколько сигналов рассматривает комитет (по умолчанию: 5)")

    args = parser.parse_args()

    if args.committee:
        run_committee(max_candidates=args.candidates, force_refresh=args.refresh)
    elif not args.radar and not args.cve:
        print("[Info] Запуск полного цикла (Радар + CVE Скоринг)...")
        run_emerging_radar(top_n=args.top, force_refresh=args.refresh)
        run_cve_scoring(force_refresh=args.refresh)
    else:
        if args.radar:
            run_emerging_radar(top_n=args.top, force_refresh=args.refresh)
        if args.cve:
            run_cve_scoring(force_refresh=args.refresh)


if __name__ == "__main__":
    main()
