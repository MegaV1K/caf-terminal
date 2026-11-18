"""
Markdown Exporter for CAF / CVE Investment Registry.
Generates institutional markdown reports with valuation scenarios and risk clusters.
"""
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from config import REPORTS_DIR

if TYPE_CHECKING:
    from src.database.registry import CAFRegistry


def export_registry_markdown(registry: "CAFRegistry") -> Path:
    """Exports the entire portfolio registry into clean GitHub-flavored Markdown with Valuation Layer."""
    from src.scoring.valuation import ValuationEngine

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "caf_portfolio_registry.md"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    active_portfolio = registry.get_active_portfolio()
    all_assets = registry.get_all_assets()
    watchlist = [a for a in all_assets if a["status"] != "Portfolio"]
    decisions = registry.get_decisions(limit=10)
    clusters = registry.get_cluster_exposure()

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
        f"**Активов в активном портфеле:** {len(active_portfolio)} / {registry.MAX_ACTIVE_PORTFOLIO} (Лимит: 20)  ",
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
