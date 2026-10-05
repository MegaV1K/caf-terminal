"""
Automated Periodic Scheduler for CAF-Terminal.
Runs the Emerging Radar and 3-Agent Investment Committee on a scheduled interval
(e.g., weekly or monthly) and persists reports and portfolio updates.
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
from main import run_emerging_radar, run_committee
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


def execute_cycle() -> None:
    log_event("=== НАЧАЛО АВТОМАТИЧЕСКОГО ЦИКЛА CAF-TERMINAL ===")
    start_time = time.time()

    try:
        # 1. Run Emerging Radar
        log_event("[1/3] Запуск Emerging / Incubator Радара...")
        run_emerging_radar(top_n=15, force_refresh=True)

        # 2. Run 3-Agent Investment Committee
        log_event("[2/3] Запуск 3-агентного Инвестиционного Комитета (топ-5 сигналов)...")
        run_committee(max_candidates=5, force_refresh=True)

        # 3. Update Registry Markdown
        log_event("[3/3] Актуализация реестра портфеля...")
        reg = CAFRegistry()
        reg_file = reg.generate_registry_markdown()
        log_event(f"Реестр портфеля обновлен: {reg_file}")

        elapsed = time.time() - start_time
        log_event(f"=== ЦИКЛ УСПЕШНО ЗАВЕРШЕН (время: {elapsed:.1f} сек) ===")

    except Exception as e:
        log_event(f"[ОШИБКА В ЦИКЛЕ]: {e}")


def main():
    parser = argparse.ArgumentParser(description="CAF-Terminal Scheduled Automation")
    parser.add_argument("--once", action="store_true", help="Запустить один цикл прямо сейчас и завершить")
    parser.add_argument("--interval-days", type=int, default=7, help="Интервал в днях между запусками (по умолчанию: 7)")
    parser.add_argument("--interval-hours", type=int, default=0, help="Интервал в часах (для тестирования)")

    args = parser.parse_args()

    if args.once:
        execute_cycle()
        return

    interval_sec = (args.interval_hours * 3600) if args.interval_hours > 0 else (args.interval_days * 86400)
    interval_desc = f"{args.interval_hours} ч." if args.interval_hours > 0 else f"{args.interval_days} дн."

    log_event(f"Планировщик запущен в фоновом режиме. Интервал повторения: {interval_desc}")

    while True:
        execute_cycle()
        log_event(f"Ожидание следующего цикла ({interval_desc})...")
        time.sleep(interval_sec)


if __name__ == "__main__":
    main()
