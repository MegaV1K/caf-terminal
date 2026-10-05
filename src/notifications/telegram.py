"""
Telegram notification module for CAF-Terminal.
Sends summaries after each committee or radar run.

Setup:
1. Create a bot via @BotFather → get TELEGRAM_BOT_TOKEN
2. Start a conversation with your bot → get your TELEGRAM_CHAT_ID
   (or send a message and check https://api.telegram.org/bot<TOKEN>/getUpdates)
3. Add to .env:
   TELEGRAM_BOT_TOKEN=1234567890:AAxxxxxx
   TELEGRAM_CHAT_ID=123456789

Usage:
    from src.notifications.telegram import notify, notify_committee_results
    notify("CAF Radar finished — 12 signals found")
    notify_committee_results(reports)
"""

import os
from typing import Any, Dict, List, Optional
import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def notify(message: str, parse_mode: str = "HTML") -> bool:
    """
    Sends a message to the configured Telegram chat.
    Returns True on success, False on failure.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": parse_mode,
            },
            timeout=10,
        )
        if not resp.ok:
            print(f"[Telegram] Failed: {resp.status_code} — {resp.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"[Telegram] Error: {e}")
        return False


def notify_committee_results(reports: List[Any]) -> None:
    """
    Sends a formatted Telegram summary of Investment Committee verdicts.
    Always notifies the user about committee deliberations.
    """
    if not reports:
        return

    full_cafs  = [r for r in reports if r.verdict.value == "FULL_CAF"]
    incubators = [r for r in reports if r.verdict.value == "INCUBATOR"]
    passes     = [r for r in reports if r.verdict.value == "PASS"]

    lines = ["<b>🏛️ CAF-Terminal | Заседание Инвестиционного Комитета</b>\n"]

    if full_cafs:
        lines.append("🔴 <b>FULL CAF — Срочный глубокий анализ:</b>")
        for r in full_cafs:
            lines.append(
                f"  • <b>{r.signal.symbol}</b> ({r.signal.name}) "
                f"— {r.signal.signal_type} | Уверенность: {r.conviction_score:.0f}%"
            )

    if incubators:
        lines.append("\n📋 <b>INCUBATOR — Добавить в портфель наблюдения:</b>")
        for r in incubators:
            lines.append(
                f"  • <b>{r.signal.symbol}</b> ({r.signal.name}) "
                f"— {r.signal.signal_type} | Уверенность: {r.conviction_score:.0f}%"
            )

    if passes and not full_cafs and not incubators:
        lines.append("⚪ <b>Все кандидаты отклонены (PASS):</b>")
        for r in passes:
            lines.append(f"  • <b>{r.signal.name}</b> ({r.signal.symbol}) — риски превышают потенциал")
        lines.append("\n<i>💡 Качественных точек входа в этом цикле не найдено. Капитал защищён от сомнительных токенов.</i>")
    elif passes:
        lines.append(f"\n⚪ <b>Отклонено:</b> {', '.join(r.signal.symbol for r in passes)}")

    lines.append(f"\n<i>Всего рассмотрено сигналов: {len(reports)}</i>")
    message = "\n".join(lines)
    sent = notify(message)
    if sent:
        print("[Telegram] Уведомление отправлено.")


def notify_radar_results(candidates: List[Dict[str, Any]], top_n: int = 5) -> None:
    """Sends top radar findings as a Telegram notification."""
    if not candidates:
        return

    lines = ["<b>📡 CAF-Terminal | Emerging Radar (Топ-Недели)</b>\n"]
    lines.append(f"Топ-{top_n} проектов по скорингу и ончейн-динамике:\n")

    for i, c in enumerate(candidates[:top_n], 1):
        tvl = f"${c.get('tvl', 0):,.0f}" if c.get("tvl") else "N/A"
        c7d = c.get('change_7d', 0)
        c7d_str = f"+{c7d:.1f}%" if c7d > 0 else f"{c7d:.1f}%"
        score = c.get("radar_score", 0)
        lines.append(
            f"{i}. <b>{c.get('symbol', '?')}</b> {c.get('name', '')} "
            f"({c.get('category', 'DeFi')})\n"
            f"   TVL: {tvl} (7d: {c7d_str}) | Score: <b>{score}</b>"
        )

    lines.append(f"\n<i>Полный отчёт сохранён в reports/</i>")
    notify("\n".join(lines))


def notify_daily_flash(anomalies: List[Dict[str, Any]]) -> None:
    """Sends immediate alert if daily flash anomalies are detected."""
    if not anomalies:
        return

    lines = ["<b>⚡ CAF-Terminal | Дневной сенсор: Обнаружены аномалии!</b>\n"]
    for a in anomalies[:5]:
        reason = a.get("reason", "Всплеск метрик")
        metric = a.get("metric_str", "")
        lines.append(f"• <b>{a.get('name')}</b> ({a.get('symbol')}) — {reason}: <code>{metric}</code>")

    lines.append("\n<i>Запустите 'python main.py --committee' для вынесения вердикта.</i>")
    notify("\n".join(lines))


def notify_audit_results(audit_summary: Dict[str, Any]) -> None:
    """Sends monthly portfolio audit results to Telegram."""
    total = audit_summary.get("total_assets", 0)
    promotions = audit_summary.get("promotions", [])
    demotions = audit_summary.get("demotions", [])
    active_dev = audit_summary.get("active_dev_count", 0)

    lines = ["<b>🔍 CAF-Terminal | Ежемесячный Аудит Портфеля</b>\n"]
    lines.append(f"• Проверено активов в базе: <b>{total}</b>")
    lines.append(f"• Активная разработка (GitHub): <b>{active_dev}</b> проектов\n")

    if promotions:
        lines.append("📈 <b>Повышение статуса / Переход в Core:</b>")
        for p in promotions:
            lines.append(f"  • <b>{p['symbol']}</b>: {p['old_tier']} ➔ <b>{p['new_tier']}</b> (Score: {p['score']})")

    if demotions:
        lines.append("\n📉 <b>Предупреждение / Снижение тира:</b>")
        for d in demotions:
            lines.append(f"  • <b>{d['symbol']}</b>: {d['old_tier']} ➔ <b>{d['new_tier']}</b> ({d.get('reason', '')})")

    if not promotions and not demotions:
        lines.append("✅ <i>Все фундаментальные тезисы подтверждены. Изменений в структуре тиров нет.</i>")

    lines.append("\n<i>Полный аудит сохранён в reports/</i>")
    notify("\n".join(lines))


def notify_rebalance_results(rebalance_summary: Dict[str, Any]) -> None:
    """Sends quarterly rebalancing recommendations to Telegram."""
    avg_pnl = rebalance_summary.get("avg_pnl", 0.0)
    targets_hit = rebalance_summary.get("targets_hit", [])
    drawdowns = rebalance_summary.get("drawdowns", [])

    lines = ["<b>⚖️ CAF-Terminal | Квартальная Ребалансировка и PnL</b>\n"]
    sign = "+" if avg_pnl > 0 else ""
    lines.append(f"• Средняя доходность портфеля: <b>{sign}{avg_pnl:.1f}%</b>\n")

    if targets_hit:
        lines.append("🎯 <b>Целевая цена достигнута (Take Profit):</b>")
        for t in targets_hit:
            lines.append(f"  • <b>{t['symbol']}</b>: PnL <b>+{t['pnl']:.1f}%</b> (Текущая: ${t['current']:.2f} / Цель: ${t['target']:.2f})")

    if drawdowns:
        lines.append("\n⚠️ <b>Глубокая просадка (Проверить тезис):</b>")
        for d in drawdowns:
            lines.append(f"  • <b>{d['symbol']}</b>: PnL <b>{d['pnl']:.1f}%</b>")

    lines.append("\n<b>Рекомендуемое распределение капитала:</b>")
    lines.append("• Core: <b>55%</b> | High Conviction: <b>30%</b> | Incubator: <b>15%</b>")
    lines.append("\n<i>Полный отчёт: reports/</i>")
    notify("\n".join(lines))


def notify_portfolio_registry(active_portfolio: List[Dict[str, Any]], watchlist_count: int) -> None:
    """Sends current active portfolio card to Telegram."""
    lines = ["<b>💼 CAF-Terminal | Институциональный Портфель (20 активов)</b>\n"]

    core = [a for a in active_portfolio if a['tier'] in ('Core', 'Core Candidate')]
    high_conv = [a for a in active_portfolio if a['tier'] == 'High Conviction']
    incubator = [a for a in active_portfolio if a['tier'] in ('Invest', 'Incubator')]

    total_weight = sum(a.get("target_weight", 0) or 0 for a in active_portfolio)
    cash_reserve = max(0.0, round(100.0 - total_weight, 1))

    if core:
        core_sum = sum(a.get("target_weight", 0) or 0 for a in core)
        lines.append(f"🟢 <b>Core ({core_sum:.1f}% пула):</b>")
        for a in core:
            w = f"{a['target_weight']:.1f}%" if a.get('target_weight') else "—"
            c = f"[{a.get('cluster', '')}]" if a.get('cluster') else ""
            lines.append(f"  • <b>{a['symbol']}</b> — <b>{w}</b> | Score: {a['score']:.1f} <i>{c}</i>")

    if high_conv:
        hc_sum = sum(a.get("target_weight", 0) or 0 for a in high_conv)
        lines.append(f"\n🔵 <b>High Conviction ({hc_sum:.1f}% пула):</b>")
        for a in high_conv:
            w = f"{a['target_weight']:.1f}%" if a.get('target_weight') else "—"
            c = f"[{a.get('cluster', '')}]" if a.get('cluster') else ""
            lines.append(f"  • <b>{a['symbol']}</b> — <b>{w}</b> | Score: {a['score']:.1f} <i>{c}</i>")

    if incubator:
        inc_sum = sum(a.get("target_weight", 0) or 0 for a in incubator)
        lines.append(f"\n🟡 <b>Incubator ({inc_sum:.1f}% пула):</b>")
        for a in incubator:
            w = f"{a['target_weight']:.1f}%" if a.get('target_weight') else "—"
            c = f"[{a.get('cluster', '')}]" if a.get('cluster') else ""
            lines.append(f"  • <b>{a['symbol']}</b> — <b>{w}</b> | Score: {a['score']:.1f} <i>{c}</i>")

    lines.append(f"\n🛡️ <b>USDC Cash Buffer:</b> <b>{cash_reserve:.1f}%</b>")
    lines.append(f"• Активов в портфеле: <b>{len(active_portfolio)} / 20</b> | Watchlist: <b>{watchlist_count}</b>")
    lines.append("\n<i>Полный отчет: reports/caf_portfolio_registry.md</i>")
    notify("\n".join(lines))


def notify_pnl_summary(pnl_data: List[Dict[str, Any]]) -> None:
    """Sends PnL performance table to Telegram."""
    if not pnl_data:
        return
    lines = ["<b>📊 CAF-Terminal | Доходность Портфеля (PnL)</b>\n"]
    for p in pnl_data:
        pnl = p.get('pnl_pct')
        sign = "+" if pnl and pnl > 0 else ""
        pnl_str = f"{sign}{pnl:.1f}%" if pnl is not None else "—"
        cur_str = f"${p['current_price']:.3f}" if p.get('current_price') else "—"
        e_str = f"${p['entry_price']:.3f}" if p.get('entry_price') else "—"
        lines.append(f"• <b>{p['symbol']}</b> ({p['tier']}): <b>{pnl_str}</b> (Вход: {e_str} / Текущая: {cur_str})")
    notify("\n".join(lines))

