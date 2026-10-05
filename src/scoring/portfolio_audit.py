"""
Monthly Portfolio Audit and Quarterly Rebalancing Engine.

Cadence Framework:
1. Monthly Audit (Каждый месяц):
   - Recalculates 5-pillar CVE scores for all portfolio assets.
   - Audits developer activity via GitHub (detects zombie repositories).
   - Checks token unlock overhang (FDV/MCap changes).
   - Re-evaluates tiers (promotions from Incubator to Core, demotions).
   - Exports reports/monthly_audit_YYYY-MM.md and notifies Telegram.

2. Quarterly Rebalance (Раз в квартал):
   - Analyzes real PnL across tracked positions.
   - Identifies take-profit triggers (current_price >= target_price).
   - Flags drawdowns and broken investment theses for stop-loss review.
   - Recommends target allocation weights: Core 55% | High Conviction 30% | Incubator 15%.
   - Exports reports/quarterly_rebalance_YYYY-Qx.md and notifies Telegram.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from config import REPORTS_DIR
from src.database.registry import CAFRegistry
from src.scouts.defillama import DefiLlamaScout
from src.scouts.coingecko import CoinGeckoScout
from src.scouts.github import GitHubScout
from src.scoring.caf_scorer import CAFScorer
from src.notifications.telegram import notify_audit_results, notify_rebalance_results


class MonthlyAuditor:
    """Performs deep monthly re-evaluation of all assets in the registry."""

    def __init__(self):
        self.reg = CAFRegistry()
        self.llama = DefiLlamaScout()
        self.cg = CoinGeckoScout()
        self.github = GitHubScout()

    def audit(self, force_refresh: bool = False) -> Dict[str, Any]:
        assets = self.reg.get_all_assets()
        if not assets:
            self.reg.seed_from_conversation()
            assets = self.reg.get_all_assets()

        # 1. Fetch live market and on-chain data
        cg_markets = self.cg.fetch_markets(pages=3, force_refresh=force_refresh)
        cg_metrics = self.cg.get_token_metrics(cg_markets)
        protocols = self.llama.fetch_protocols(force_refresh=force_refresh)

        proto_by_symbol = {}
        for p in protocols:
            sym = (p.get("symbol") or "").upper()
            if sym and sym not in proto_by_symbol:
                proto_by_symbol[sym] = p

        audit_results = []
        promotions = []
        demotions = []
        active_dev_count = 0

        # Tier rank for comparing promotions/demotions
        tier_ranks = {
            "Core Candidate": 4,
            "High Conviction": 3,
            "Invest": 2,
            "Watch": 1,
        }

        for a in assets:
            sym = a["symbol"].upper()
            old_tier = a["tier"]
            old_score = a["score"] or 50.0

            cg_data = cg_metrics.get(sym, {})
            llama_data = proto_by_symbol.get(sym, {})

            # Developer activity check
            repo = self.github.get_repo_for_symbol(sym)
            dev_metrics = {}
            if repo:
                dev_metrics = self.github.fetch_repo_metrics(repo)
                if dev_metrics.get("is_active"):
                    active_dev_count += 1

            # Recalculate CVE score
            metrics_payload = {
                "symbol": sym,
                "name": a["name"],
                "category": a.get("sector") or llama_data.get("category") or "Layer 1",
                "rank": cg_data.get("rank") or 999,
                "mcap": cg_data.get("mcap") or llama_data.get("mcap") or 0,
                "fdv": cg_data.get("fdv"),
                "fdv_mcap_ratio": cg_data.get("fdv_mcap_ratio"),
                "tvl": llama_data.get("tvl") or 0,
                "daily_fees": llama_data.get("daily_fees") or 0,
                "chains": llama_data.get("chains") or [],
            }

            score_res = CAFScorer.calculate_cve_score(metrics_payload)
            new_score = score_res["composite_score"]
            new_tier = score_res["tier"]

            # Update database
            self.reg.upsert_asset(
                symbol=sym,
                name=a["name"],
                tier=new_tier,
                sector=a.get("sector", ""),
                thesis=a.get("thesis", ""),
                counter_thesis=a.get("counter_thesis", ""),
                score=new_score,
                status=a.get("status", "Active"),
            )

            # Check tier change
            old_rank = tier_ranks.get(old_tier, 2)
            new_rank = tier_ranks.get(new_tier, 2)

            if new_rank > old_rank:
                promotions.append({
                    "symbol": sym,
                    "name": a["name"],
                    "old_tier": old_tier,
                    "new_tier": new_tier,
                    "score": new_score,
                })
            elif new_rank < old_rank:
                demotions.append({
                    "symbol": sym,
                    "name": a["name"],
                    "old_tier": old_tier,
                    "new_tier": new_tier,
                    "reason": f"Балл CVE снизился до {new_score:.1f}",
                })

            audit_results.append({
                "symbol": sym,
                "name": a["name"],
                "old_tier": old_tier,
                "new_tier": new_tier,
                "old_score": old_score,
                "new_score": new_score,
                "score_delta": round(new_score - old_score, 1),
                "pillars": score_res["pillars"],
                "dev_active": dev_metrics.get("is_active", False),
            })

        summary = {
            "total_assets": len(assets),
            "active_dev_count": active_dev_count,
            "promotions": promotions,
            "demotions": demotions,
            "results": audit_results,
        }

        # Generate Markdown Report
        self._save_audit_report(summary)
        return summary

    def _save_audit_report(self, summary: Dict[str, Any]) -> Path:
        date_str = datetime.now().strftime("%Y-%m")
        file_path = REPORTS_DIR / f"monthly_audit_{date_str}.md"

        lines = [
            f"# Ежемесячный Аудит Портфеля CAF/CVE — {datetime.now().strftime('%B %Y')}\n",
            f"**Дата проведения:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"**Всего активов на аудите:** {summary['total_assets']}",
            f"**Проектов с активным кодом (GitHub):** {summary['active_dev_count']}\n",
            "## 1. Изменения в тирах портфеля\n",
        ]

        if summary["promotions"]:
            lines.append("### 📈 Повышения в статусе (Promotions):")
            for p in summary["promotions"]:
                lines.append(f"- **{p['symbol']}** ({p['name']}): `{p['old_tier']}` ➔ **`{p['new_tier']}`** (Балл: {p['score']})")
            lines.append("")

        if summary["demotions"]:
            lines.append("### 📉 Понижения в статусе (Demotions):")
            for d in summary["demotions"]:
                lines.append(f"- **{d['symbol']}** ({d['name']}): `{d['old_tier']}` ➔ **`{d['new_tier']}`** ({d['reason']})")
            lines.append("")

        if not summary["promotions"] and not summary["demotions"]:
            lines.append("✅ Все инвестиционные тезисы стабильны, изменений в тирах нет.\n")

        lines.append("## 2. Сводная таблица переоценки\n")
        lines.append("| Тикер | Проект | Старый Тир | Новый Тир | Балл CVE | Изм. | Dev Health |")
        lines.append("|---|---|---|---|---|---|---|")

        for r in summary["results"]:
            sign = "+" if r["score_delta"] > 0 else ""
            delta_str = f"{sign}{r['score_delta']:.1f}" if r["score_delta"] != 0 else "0.0"
            dev_str = "🟢 Active" if r["dev_active"] else "⚪ N/A"
            lines.append(f"| **{r['symbol']}** | {r['name']} | {r['old_tier']} | {r['new_tier']} | **{r['new_score']:.1f}** | {delta_str} | {dev_str} |")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return file_path


class QuarterlyRebalancer:
    """Calculates quarterly portfolio PnL, take-profit triggers, and target asset weights."""

    TARGET_ALLOCATION = {
        "Core Candidate":  55.0,  # 55% of capital
        "High Conviction": 30.0,  # 30% of capital
        "Invest":          10.0,  # 10% of capital
        "Watch":            5.0,  # 5% of capital (tactical/incubator)
    }

    def __init__(self):
        self.reg = CAFRegistry()
        self.cg = CoinGeckoScout()

    def rebalance(self, force_refresh: bool = False) -> Dict[str, Any]:
        pnl_data = self.reg.get_pnl_summary()
        if not pnl_data:
            return {"empty": True}

        # Auto-update current prices via CoinGecko if available
        cg_markets = self.cg.fetch_markets(pages=3, force_refresh=force_refresh)
        price_by_sym = {m["symbol"].upper(): m.get("current_price") for m in cg_markets if m.get("symbol")}

        for pos in pnl_data:
            sym = pos["symbol"].upper()
            live_price = price_by_sym.get(sym)
            if live_price:
                self.reg.update_price(symbol=sym, current_price=live_price)

        # Re-fetch refreshed summary
        pnl_data = self.reg.get_pnl_summary()

        targets_hit = []
        drawdowns = []
        pnl_values = []

        for p in pnl_data:
            pnl = p.get("pnl_pct") or 0.0
            pnl_values.append(pnl)
            cur = p.get("current_price") or 0.0
            target = p.get("target_price") or 0.0

            # Take profit trigger
            if (target > 0 and cur >= target) or pnl >= 100.0:
                targets_hit.append({
                    "symbol": p["symbol"],
                    "name": p["name"],
                    "pnl": pnl,
                    "current": cur,
                    "target": target,
                })

            # Drawdown trigger (> -25%)
            if pnl <= -25.0:
                drawdowns.append({
                    "symbol": p["symbol"],
                    "name": p["name"],
                    "pnl": pnl,
                    "current": cur,
                })

        avg_pnl = sum(pnl_values) / len(pnl_values) if pnl_values else 0.0

        summary = {
            "empty": False,
            "total_positions": len(pnl_data),
            "avg_pnl": round(avg_pnl, 1),
            "targets_hit": targets_hit,
            "drawdowns": drawdowns,
            "positions": pnl_data,
            "target_allocation": self.TARGET_ALLOCATION,
        }

        self._save_rebalance_report(summary)
        return summary

    def _save_rebalance_report(self, summary: Dict[str, Any]) -> Path:
        quarter = f"Q{(datetime.now().month - 1) // 3 + 1}_{datetime.now().year}"
        file_path = REPORTS_DIR / f"quarterly_rebalance_{quarter}.md"

        lines = [
            f"# Квартальный Отчёт Ребалансировки и PnL — {quarter}\n",
            f"**Дата отчёта:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"**Средняя доходность портфеля:** {summary['avg_pnl']:+.1f}%",
            f"**Позиций в портфеле:** {summary['total_positions']}\n",
            "## 1. Рекомендации по позициям\n",
        ]

        if summary["targets_hit"]:
            lines.append("### 🎯 Фиксация прибыли (Take Profit):")
            for t in summary["targets_hit"]:
                lines.append(f"- **{t['symbol']}**: PnL `+{t['pnl']:.1f}%` (Текущая: ${t['current']:.3f} / Цель: ${t['target']:.3f}) ➔ *Рекомендовано зафиксировать 50-70% позиции*")
            lines.append("")

        if summary["drawdowns"]:
            lines.append("### ⚠️ Глубокая просадка (Ревизия тезиса):")
            for d in summary["drawdowns"]:
                lines.append(f"- **{d['symbol']}**: PnL `{d['pnl']:.1f}%` (Текущая: ${d['current']:.3f}) ➔ *Проверить сохранность фундаментального тезиса*")
            lines.append("")

        lines.append("## 2. Целевая модель распределения капитала\n")
        lines.append("| Категория | Целевая доля | Описание |")
        lines.append("|---|---|---|")
        lines.append("| **Core Candidates** | **55%** | Базовые надёжные активы с подтверждённым захватом ценности |")
        lines.append("| **High Conviction** | **30%** | Сильные фундаментальные проекты с высоким потенциалом роста |")
        lines.append("| **Invest / Emerging** | **15%** | Тактические инкубаторные позиции с высоким бета-коэффициентом |")

        lines.append("\n## 3. Таблица доходности позиций\n")
        lines.append("| Тикер | Проект | Тир | Цена входа | Текущая цена | Цель | PnL % |")
        lines.append("|---|---|---|---|---|---|---|")

        for pos in summary["positions"]:
            e_str = f"${pos['entry_price']:.3f}" if pos.get('entry_price') else "—"
            c_str = f"${pos['current_price']:.3f}" if pos.get('current_price') else "—"
            t_str = f"${pos['target_price']:.3f}" if pos.get('target_price') else "—"
            pnl_val = pos.get('pnl_pct')
            pnl_str = f"**{pnl_val:+.1f}%**" if pnl_val is not None else "—"
            lines.append(f"| **{pos['symbol']}** | {pos['name']} | {pos['tier']} | {e_str} | {c_str} | {t_str} | {pnl_str} |")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return file_path


def run_monthly_audit(force_refresh: bool = False) -> Dict[str, Any]:
    """CLI runner for monthly audit."""
    print("\n" + "=" * 70)
    print("🔍 ЕЖЕМЕСЯЧНЫЙ АУДИТ ПОРТФЕЛЯ (ПЕРЕСЧЁТ CVE 5 СТОЛПОВ И DEV HEALTH)")
    print("=" * 70)
    print("Проверка: актуализация баллов CVE, навес разлоков, активность кода")
    print("-" * 70)

    auditor = MonthlyAuditor()
    summary = auditor.audit(force_refresh=force_refresh)

    print(f"[OK] Проверено {summary['total_assets']} активов в базе.")
    print(f"[+] Проектов с активным кодом GitHub: {summary['active_dev_count']}")

    if summary["promotions"]:
        print("\n📈 Повышения в статусе (Promotions):")
        for p in summary["promotions"]:
            print(f"  • {p['symbol']}: {p['old_tier']} ➔ {p['new_tier']} (Балл: {p['score']})")

    if summary["demotions"]:
        print("\n📉 Понижения в статусе (Demotions):")
        for d in summary["demotions"]:
            print(f"  • {d['symbol']}: {d['old_tier']} ➔ {d['new_tier']} ({d['reason']})")

    if not summary["promotions"] and not summary["demotions"]:
        print("[OK] Все инвестиционные тезисы стабильны, изменений тиров нет.")

    print("\n" + "=" * 70)
    print("[Telegram] Отправка сводки аудита...")
    try:
        notify_audit_results(summary)
        print("[OK] Сводка аудита доставлена в Telegram.")
    except Exception as e:
        print(f"[!] Ошибка отправки: {e}")
    print("=" * 70)

    return summary


def run_quarterly_rebalance(force_refresh: bool = False) -> Dict[str, Any]:
    """CLI runner for quarterly rebalancing."""
    print("\n" + "=" * 70)
    print("⚖️ КВАРТАЛЬНАЯ РЕБАЛАНСИРОВКА И PnL АНАЛИЗ")
    print("=" * 70)

    rebalancer = QuarterlyRebalancer()
    summary = rebalancer.rebalance(force_refresh=force_refresh)

    if summary.get("empty"):
        print("[!] Нет позиций с заданной ценой входа.")
        print("    Добавьте цену входа: python main.py --set-price --symbol SUI --entry 1.85 --target 4.50")
        print("=" * 70)
        return summary

    sign = "+" if summary["avg_pnl"] > 0 else ""
    print(f"• Средняя доходность портфеля: {sign}{summary['avg_pnl']}%\n")

    if summary["targets_hit"]:
        print("🎯 Целевые уровни достигнуты (Take Profit):")
        for t in summary["targets_hit"]:
            print(f"  • {t['symbol']}: +{t['pnl']:.1f}% (Текущая: ${t['current']:.3f} / Цель: ${t['target']:.3f})")

    if summary["drawdowns"]:
        print("\n⚠️ Глубокая просадка (Ревизия тезиса):")
        for d in summary["drawdowns"]:
            print(f"  • {d['symbol']}: {d['pnl']:.1f}%")

    print("\n" + "=" * 70)
    print("[Telegram] Отправка рекомендаций по ребалансировке...")
    try:
        notify_rebalance_results(summary)
        print("[OK] Рекомендации доставлены в Telegram.")
    except Exception as e:
        print(f"[!] Ошибка отправки: {e}")
    print("=" * 70)

    return summary
