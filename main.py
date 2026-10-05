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
    """Displays and exports the CAF/CVE Portfolio (strictly max 20 assets) & Watchlist with Valuation Layer."""
    from src.database.registry import CAFRegistry
    from src.scoring.valuation import ValuationEngine

    reg = CAFRegistry()
    active_portfolio = reg.get_active_portfolio()
    if not active_portfolio:
        print("[Info] База данных пуста. Запуск наполнения из базового анализа...")
        reg.seed_from_conversation()
        active_portfolio = reg.get_active_portfolio()

    all_assets = reg.get_all_assets()
    watchlist_count = len(all_assets) - len(active_portfolio)
    report_file = reg.generate_registry_markdown()

    # Calculate valuation ratings
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

    total_target = sum(r.target_weight for r in val_ratings)
    total_deployed = sum(r.deployed_weight for r in val_ratings)
    total_dry_powder = sum(r.dry_powder_weight for r in val_ratings)
    cash_reserve = max(0.0, round(100.0 - total_target, 1))
    total_liquid = round(cash_reserve + total_dry_powder, 1)

    print("\n" + "=" * 115)
    print("💼 ИНВЕСТИЦИОННЫЙ ПОРТФЕЛЬ CAF / CVE — 5-LAYER VALUATION & TACTICAL DEPLOYMENT")
    print("=" * 115)
    print("Разделение слоев: Фундаментальное качество (CVE) vs Оценка точки входа (Entry Score) & Сетки добора.")
    print("-" * 115)
    print(f"{'Тикер':<7} {'Проект':<15} {'Цена':<8} {'ATH DD':<8} {'CVE':<5} {'Entry':<6} {'Сигнал':<15} {'Цель %':<7} {'Развёрн.':<9} {'Резерв':<7} {'Зона добора'}")
    print("-" * 115)

    for vr in val_ratings:
        p_str = f"${vr.current_price:,.2f}" if vr.current_price >= 1.0 else f"${vr.current_price:.3f}"
        dd_str = f"{vr.ath_drawdown_pct:+.1f}%"
        cve_str = f"{vr.fundamental_score:.1f}"
        entry_str = f"{vr.entry_score:.1f}"
        tgt_str = f"{vr.target_weight:.1f}%"
        dep_str = f"{vr.deployed_weight:.1f}%"
        dry_str = f"{vr.dry_powder_weight:.1f}%"
        name_short = (vr.name[:13] + "..") if len(vr.name) > 13 else vr.name
        zone_short = vr.buy_zones[0] if vr.buy_zones else "—"
        print(f"{vr.symbol:<7} {name_short:<15} {p_str:<8} {dd_str:<8} {cve_str:<5} {entry_str:<6} {vr.entry_signal:<15} {tgt_str:<7} {dep_str:<9} {dry_str:<7} {zone_short}")

    print("-" * 115)
    print(f"{'USDC':<7} {'Cash Reserve':<15} {'$1.00':<8} {'0.0%':<8} {'100.0':<5} {'100.0':<6} {'STABLE_BUFFER':<15} {cash_reserve:<6.1f}% {cash_reserve:<8.1f}% {'0.0%':<7} Базовый буфер ликвидности")
    print(f"{'USDC_DCA':<7} {'Tactical Reserve':<15} {'$1.00':<8} {'0.0%':<8} {'100.0':<5} {'—':<6} {'LIMIT_POWDER':<15} {total_dry_powder:<6.1f}% {'0.0%':<8} {total_dry_powder:<6.1f}% Отложенные лимитные сетки выкупа")
    print("=" * 115)
    print(f"• Активов в активном портфеле: {len(active_portfolio)} / 20 (100% лимит)")
    print(f"• Стратегический потолок альтов (Target): {total_target:.1f}% | Фактически развёрнуто сегодня: {total_deployed:.1f}%")
    print(f"• Тактический Dry Powder под лимитные зоны: {total_dry_powder:.1f}% | Базовый кэш (USDC): {cash_reserve:.1f}%")
    print(f"• Совокупная ликвидная подушка (USDC + Dry Powder): {total_liquid:.1f}%")
    print(f"• На скамье наблюдения (Watchlist): {watchlist_count} проектов")
    print(f"[OK] Полный реестр экспортирован в: {report_file}")
    print("=" * 115)

    # Optional Telegram Alert
    try:
        from src.notifications.telegram import notify_portfolio_registry
        notify_portfolio_registry(active_portfolio, watchlist_count)
        print("[Telegram] Сводка портфеля отправлена в Telegram.")
    except Exception:
        pass


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

    # Optional Telegram Alert
    try:
        from src.notifications.telegram import notify_pnl_summary
        notify_pnl_summary(summary)
        print("[Telegram] PnL сводка отправлена в Telegram.")
    except Exception:
        pass


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


def run_weekly_cycle(top_n: int = 20, candidates: int = 5, force_refresh: bool = False):
    """Executes the complete weekly investment cycle: Radar Top 20 + Committee."""
    print("\n" + "=" * 70)
    print("🗓️ ЕЖЕНЕДЕЛЬНЫЙ ИНВЕСТИЦИОННЫЙ ЦИКЛ CAF-TERMINAL")
    print("=" * 70)
    print("1. Поиск ТОП-20 Emerging / Incubator проектов на радаре")
    print("2. Заседание 3-агентного Инвестиционного Комитета по топ-сигналам")
    print("3. Обновление базы данных портфеля и реестра")
    print("4. Отправка дайджеста в Telegram")
    print("=" * 70)

    run_emerging_radar(top_n=top_n, force_refresh=force_refresh)
    run_committee(max_candidates=candidates, force_refresh=force_refresh)


def main():
    parser = argparse.ArgumentParser(description="CAF-Terminal: Automated Radar & CVE Scoring")
    # Cadence framework
    parser.add_argument("--daily",      action="store_true", help="[День] Экспресс-сенсор суточных аномалий (0 LLM, быстрый скан)")
    parser.add_argument("--weekly",     action="store_true", help="[Неделя] Полный еженедельный цикл: Радар Топ-20 + Комитет")
    parser.add_argument("--audit",      action="store_true", help="[Месяц] Ежемесячный аудит портфеля (пересчёт CVE, разлоки, GitHub)")
    parser.add_argument("--monthly",    action="store_true", help="Алиас для --audit")
    parser.add_argument("--rebalance",  action="store_true", help="[Квартал] Квартальная ребалансировка, PnL и фиксация прибыли")
    parser.add_argument("--quarterly",  action="store_true", help="Алиас для --rebalance")

    # Core components
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
    parser.add_argument("--top",        type=int, default=20, help="Количество проектов в радаре (по умолчанию: 20)")
    parser.add_argument("--candidates", type=int, default=5,  help="Сколько сигналов рассматривает комитет (по умолчанию: 5)")

    args = parser.parse_args()

    # 1. Maintenance
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

    # 2. Cadence framework execution
    if args.daily:
        from src.scouts.daily_sensor import run_daily_sensor
        run_daily_sensor(force_refresh=args.refresh)
        return

    if args.weekly:
        run_weekly_cycle(top_n=args.top, candidates=args.candidates, force_refresh=args.refresh)
        return

    if args.audit or args.monthly:
        from src.scoring.portfolio_audit import run_monthly_audit
        run_monthly_audit(force_refresh=args.refresh)
        return

    if args.rebalance or args.quarterly:
        from src.scoring.portfolio_audit import run_quarterly_rebalance
        run_quarterly_rebalance(force_refresh=args.refresh)
        return

    # 3. Individual views & runs
    if args.pnl:
        run_pnl_view()
    elif args.registry:
        run_registry_view()
    elif args.committee:
        run_committee(max_candidates=args.candidates, force_refresh=args.refresh)
    elif args.radar:
        run_emerging_radar(top_n=args.top, force_refresh=args.refresh)
    elif args.cve:
        run_cve_scoring(force_refresh=args.refresh)
    else:
        # Default: Full weekly cycle
        run_weekly_cycle(top_n=args.top, candidates=args.candidates, force_refresh=args.refresh)


if __name__ == "__main__":
    main()


