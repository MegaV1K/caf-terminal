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
    Only sends if at least one FULL_CAF or INCUBATOR verdict was found.
    """
    if not reports:
        return

    full_cafs  = [r for r in reports if r.verdict.value == "FULL_CAF"]
    incubators = [r for r in reports if r.verdict.value == "INCUBATOR"]
    passes     = [r for r in reports if r.verdict.value == "PASS"]

    # Only notify if there's something actionable
    if not full_cafs and not incubators:
        return

    lines = ["<b>CAF-Terminal | Investment Committee Results</b>\n"]

    if full_cafs:
        lines.append("🔴 <b>FULL CAF — Срочный анализ:</b>")
        for r in full_cafs:
            lines.append(
                f"  • <b>{r.signal.symbol}</b> ({r.signal.name}) "
                f"— {r.signal.signal_type} | Уверенность: {r.conviction_score:.0f}%"
            )

    if incubators:
        lines.append("\n📋 <b>INCUBATOR — Добавить в наблюдение:</b>")
        for r in incubators:
            lines.append(
                f"  • <b>{r.signal.symbol}</b> ({r.signal.name}) "
                f"— {r.signal.signal_type} | Уверенность: {r.conviction_score:.0f}%"
            )

    if passes:
        lines.append(f"\n⚪ Пропущено: {', '.join(r.signal.symbol for r in passes)}")

    lines.append(f"\n<i>Всего сигналов: {len(reports)}</i>")
    message = "\n".join(lines)
    sent = notify(message)
    if sent:
        print("[Telegram] Уведомление отправлено.")


def notify_radar_results(candidates: List[Dict[str, Any]], top_n: int = 5) -> None:
    """Sends top radar findings as a Telegram notification."""
    if not candidates:
        return

    lines = ["<b>CAF-Terminal | Emerging Radar</b>\n"]
    lines.append(f"Топ-{top_n} сигналов этой недели:\n")

    for i, c in enumerate(candidates[:top_n], 1):
        tvl = f"${c.get('tvl', 0):,.0f}" if c.get("tvl") else "N/A"
        score = c.get("radar_score", 0)
        lines.append(
            f"{i}. <b>{c.get('symbol', '?')}</b> {c.get('name', '')} "
            f"— TVL: {tvl} | Score: {score}"
        )

    notify("\n".join(lines))
