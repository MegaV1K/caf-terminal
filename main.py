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

    # Optional Telegram Alert
    try:
        from src.notifications.telegram import notify_radar_results
        notify_radar_results(candidates, top_n=top_n)
    except Exception:
        pass


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

    # Robust fees join: use defillamaId as primary key, lowercase name as fallback
    fees_by_id: dict = {}
    fees_by_name: dict = {}
    for p in fees_data.get("protocols", []):
        did = p.get("defillamaId")
        if did:
            fees_by_id[str(did)] = p
        name_lc = (p.get("name") or "").lower()
        if name_lc:
            fees_by_name[name_lc] = p
        if p.get("module"):
            fees_by_name[p["module"].lower()] = p

    for p in protocols:
        proto_id = str(p.get("id") or "")
        name_key = (p.get("name") or "").lower()
        fee_info = fees_by_id.get(proto_id) or fees_by_name.get(name_key) or {}
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

    # Record to Registry Database
    from src.database.registry import CAFRegistry
    reg = CAFRegistry()
    for r in reports:
        reg.record_committee_decision(r)
    reg_file = reg.generate_registry_markdown()

    # Optional Telegram Alert
    try:
        from src.notifications.telegram import notify_committee_results
        notify_committee_results(reports)
    except Exception:
        pass

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

    print(f"\n[OK] Полный протокол сохранен в: {report_path}")
    print(f"[OK] База данных портфеля обновлена: {reg_file}")
    print("=" * 60)


def run_registry_view():
    """Displays and exports the CAF/CVE Portfolio & Incubator Registry."""
    from src.database.registry import CAFRegistry
    reg = CAFRegistry()
    assets = reg.get_all_assets()
    if not assets:
        print("[Info] База данных пуста. Запуск наполнения из базового анализа...")
        count = reg.seed_from_conversation()
        print(f"[+] Добавлено {count} проектов в базу.")
        assets = reg.get_all_assets()

    report_file = reg.generate_registry_markdown()

    print("\n" + "=" * 80)
    print("📋 РЕЕСТР ПОРТФЕЛЯ И ИНКУБАТОРА CAF / CVE (БАЗА ДАННЫХ)")
    print("=" * 80)
    print(f"{'Тикер':<8} {'Проект':<22} {'Уровень':<18} {'Score':<6} {'Сектор':<20}")
    print("-" * 80)

    for a in assets:
        score_str = f"{a['score']:.1f}" if a['score'] else "—"
        name_short = (a['name'][:20] + "..") if len(a['name']) > 20 else a['name']
        sec_short = (a['sector'][:18] + "..") if a['sector'] and len(a['sector']) > 18 else (a['sector'] or "—")
        print(f"{a['symbol']:<8} {name_short:<22} {a['tier']:<18} {score_str:<6} {sec_short:<20}")

    print("\n" + "=" * 80)
    print(f"Всего активов в базе: {len(assets)}")
    print(f"[OK] Полный реестр экспортирован в: {report_file}")
    print("=" * 80)


def run_pnl_view():
    """Displays portfolio PnL performance table."""
    from src.database.registry import CAFRegistry
    reg = CAFRegistry()
    summary = reg.get_pnl_summary()
    if not summary:
        print("\n" + "=" * 80)
        print("📊 PnL ТРЕКИНГ ПОРТФЕЛЯ (БАЗА ДАННЫХ)")
        print("=" * 80)
        print("[!] Нет активов с заданной ценой входа.")
        print("    Чтобы добавить актив в трекинг цен, используйте команду:")
        print("    python main.py --set-price --symbol SUI --entry 1.85 --current 2.10 --target 4.50")
        print("=" * 80)
        return

    print("\n" + "=" * 80)
    print("📊 PnL ТРЕКИНГ ПОРТФЕЛЯ")
    print("=" * 80)
    print(f"{'Тикер':<8} {'Проект':<18} {'Уровень':<16} {'Вход':<10} {'Текущая':<10} {'Цель':<10} {'PnL %':<10}")
    print("-" * 80)
    for a in summary:
        e_str = f"${a['entry_price']:.3f}" if a['entry_price'] else "—"
        c_str = f"${a['current_price']:.3f}" if a['current_price'] else "—"
        t_str = f"${a['target_price']:.3f}" if a['target_price'] else "—"
        pnl = a['pnl_pct']
        pnl_str = f"{pnl:+.1f}%" if pnl is not None else "—"
        print(f"{a['symbol']:<8} {a['name'][:16]:<18} {a['tier']:<16} {e_str:<10} {c_str:<10} {t_str:<10} {pnl_str:<10}")
    print("=" * 80)


def run_set_price(symbol: str, entry: float = None, current: float = None, target: float = None):
    """Sets entry/current/target price for an asset."""
    from src.database.registry import CAFRegistry
    reg = CAFRegistry()
    reg.update_price(
        symbol=symbol,
        entry_price=entry,
        current_price=current,
        target_price=target,
    )
    print(f"[OK] Цены для {symbol.upper()} успешно обновлены в базе данных.")
    run_pnl_view()


def main():
    parser = argparse.ArgumentParser(description="CAF-Terminal: Automated Radar & CVE Scoring")
    parser.add_argument("--radar",      action="store_true", help="Запустить поиск Emerging/Incubator проектов")
    parser.add_argument("--cve",        action="store_true", help="Запустить CVE скоринг ключевых активов")
    parser.add_argument("--committee",  action="store_true", help="Запустить 3-агентный инвестиционный комитет")
    parser.add_argument("--registry",   action="store_true", help="Показать реестр портфеля и базы проектов")
    parser.add_argument("--pnl",        action="store_true", help="Показать таблицу PnL доходности портфеля")
    parser.add_argument("--set-price",  action="store_true", help="Обновить цены входа/цели/текущую для токена")
    parser.add_argument("--symbol",     type=str, default="", help="Тикер токена для обновления цены")
    parser.add_argument("--entry",      type=float, default=None, help="Цена входа ($)")
    parser.add_argument("--current",    type=float, default=None, help="Текущая рыночная цена ($)")
    parser.add_argument("--target",     type=float, default=None, help="Целевая цена ($)")
    parser.add_argument("--seed",       action="store_true", help="Перезаполнить базу данных из истории беседы")
    parser.add_argument("--refresh",    action="store_true", help="Игнорировать кэш и обновить данные")
    parser.add_argument("--top",        type=int, default=15, help="Количество проектов в радаре (по умолчанию: 15)")
    parser.add_argument("--candidates", type=int, default=5,  help="Сколько сигналов рассматривает комитет (по умолчанию: 5)")

    args = parser.parse_args()

    if args.seed:
        from src.database.registry import CAFRegistry
        reg = CAFRegistry()
        count = reg.seed_from_conversation()
        print(f"[+] База данных успешно наполнена {count} проектами.")
        return

    if args.set_price:
        if not args.symbol:
            print("[!] Укажите тикер токена: --symbol TICKER")
            return
        run_set_price(args.symbol, entry=args.entry, current=args.current, target=args.target)
        return

    if args.pnl:
        run_pnl_view()
        return

    if args.registry:
        run_registry_view()
    elif args.committee:
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

