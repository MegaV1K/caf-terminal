"""
Automated Periodic Scheduler for CAF-Terminal.
Supports multi-cadence operations:
- daily:   Fast 0-LLM flash anomaly sensor (runs every 24h)
- weekly:  Top-20 Emerging Radar + 3-Agent Investment Committee (runs every 7d)
- monthly: Deep 5-Pillar CVE Portfolio Audit & GitHub health check (runs every 30d)
"""

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import DATA_DIR, REPORTS_DIR
from main import run_emerging_radar, run_committee, run_weekly_cycle
from src.scouts.daily_sensor import run_daily_sensor
from src.scoring.portfolio_audit import run_monthly_audit
from src.database.registry import CAFRegistry

LOG_FILE = DATA_DIR / "scheduler.log"


def log_event(message: str) -> None:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{now_str}] {message}\n"
    print(entry, end="")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass


def execute_cycle(mode: str = "weekly") -> None:
    log_event(f"=== НАЧАЛО АВТОМАТИЧЕСКОГО ЦИКЛА CAF-TERMINAL (РЕЖИМ: {mode.upper()}) ===")
    start_time = time.time()

    try:
        if mode == "daily":
            log_event("[Daily] Запуск сенсора суточных аномалий...")
            anomalies = run_daily_sensor(force_refresh=True)
            log_event(f"[Daily] Найдено аномалий: {len(anomalies)}")

        elif mode == "monthly":
            log_event("[Monthly] Запуск глубокого аудита портфеля...")
            summary = run_monthly_audit(force_refresh=True)
            log_event(f"[Monthly] Проверено активов: {summary['total_assets']}")

        else:  # default: weekly
            log_event("[Weekly] 1/3 Запуск Emerging / Incubator Радара Топ-20...")
            run_emerging_radar(top_n=20, force_refresh=True)

            log_event("[Weekly] 2/3 Запуск 3-агентного Инвестиционного Комитета...")
            run_committee(max_candidates=5, force_refresh=True)

            log_event("[Weekly] 3/3 Актуализация реестра портфеля...")
            reg = CAFRegistry()
            reg_file = reg.generate_registry_markdown()
            log_event(f"Реестр портфеля обновлен: {reg_file}")

        elapsed = time.time() - start_time
        log_event(f"=== ЦИКЛ УСПЕШНО ЗАВЕРШЕН (время: {elapsed:.1f} сек) ===")

        # Optional Telegram notification
        try:
            from src.notifications.telegram import notify
            notify(f"<b>CAF-Terminal Scheduler</b>\nЦикл <code>{mode.upper()}</code> успешно завершён за {elapsed:.1f} сек.")
        except Exception:
            pass

    except Exception as e:
        log_event(f"[ОШИБКА В ЦИКЛЕ]: {e}")
        try:
            from src.notifications.telegram import notify
            notify(f"<b>CAF-Terminal Scheduler</b>\n❌ Ошибка в цикле {mode}: {e}")
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="CAF-Terminal Scheduled Automation")
    parser.add_argument("--mode", choices=["daily", "weekly", "monthly"], default="weekly", help="Режим работы: daily, weekly, monthly")
    parser.add_argument("--once", action="store_true", help="Запустить один цикл прямо сейчас и завершить")
    parser.add_argument("--interval-days", type=int, default=0, help="Интервал в днях между запусками")
    parser.add_argument("--interval-hours", type=int, default=0, help="Интервал в часах (для тестирования)")

    args = parser.parse_args()

    if args.once:
        execute_cycle(mode=args.mode)
        return

    # Default intervals based on mode if not specified
    if args.interval_days == 0 and args.interval_hours == 0:
        default_days = {"daily": 1, "weekly": 7, "monthly": 30}
        days = default_days.get(args.mode, 7)
        interval_sec = days * 86400
        interval_desc = f"{days} дн."
    else:
        interval_sec = (args.interval_hours * 3600) if args.interval_hours > 0 else (args.interval_days * 86400)
        interval_desc = f"{args.interval_hours} ч." if args.interval_hours > 0 else f"{args.interval_days} дн."

    log_event(f"Планировщик запущен в фоновом режиме [{args.mode.upper()}]. Интервал: {interval_desc}")

    while True:
        execute_cycle(mode=args.mode)
        log_event(f"Ожидание следующего цикла ({interval_desc})...")
        time.sleep(interval_sec)


if __name__ == "__main__":
    main()
