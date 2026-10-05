"""
Daily Anomaly Sensor for CAF-Terminal.
Lightweight, rapid signal scanner: 0 LLM calls, zero Gemini API usage.
Monitors 24h market dynamics: flash TVL spikes, volume turnover explosions,
and daily fee surges. Alerts via Telegram only when true anomalies occur.
"""

from typing import Any, Dict, List
from src.scouts.defillama import DefiLlamaScout
from src.scouts.coingecko import CoinGeckoScout
from src.notifications.telegram import notify_daily_flash


class DailySensor:
    """Scans on-chain and market data for 24h flash anomalies."""

    FLASH_TVL_1D_THRESHOLD = 25.0       # 25% 1-day TVL surge
    MIN_TVL = 2_000_000                 # Proof of real capital ($2M+)
    FLASH_TURNOVER_RATIO = 0.50         # 24h volume > 50% of market cap
    MIN_SURGE_FEES = 20_000             # $20k+ daily fees for small caps

    def __init__(self):
        self.llama = DefiLlamaScout()
        self.coingecko = CoinGeckoScout()

    def scan(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Executes daily fast scan.
        Returns list of detected 24h flash anomalies.
        """
        anomalies: List[Dict[str, Any]] = []
        seen_symbols = set()

        # 1. DefiLlama: 24h TVL spikes & 24h fee surges
        protocols = self.llama.fetch_protocols(force_refresh=force_refresh)
        fees_data = self.llama.fetch_fees_and_revenue(force_refresh=force_refresh)

        fees_by_id = {}
        for p in fees_data.get("protocols", []):
            if p.get("defillamaId"):
                fees_by_id[str(p["defillamaId"])] = p

        for p in protocols:
            tvl = p.get("tvl") or 0
            c1d = p.get("change_1d") or 0
            mcap = p.get("mcap") or 0
            symbol = (p.get("symbol") or "").upper()
            name = p.get("name", "")

            if tvl < self.MIN_TVL:
                continue

            # Check 1: 24h TVL Flash Spike (> +25% in 24 hours)
            if c1d >= self.FLASH_TVL_1D_THRESHOLD:
                seen_symbols.add(symbol)
                anomalies.append({
                    "name": name,
                    "symbol": symbol,
                    "category": p.get("category", "DeFi"),
                    "tvl": tvl,
                    "reason": "Суточный взлёт TVL",
                    "metric_str": f"+{c1d:.1f}% за 24ч (TVL: ${tvl:,.0f})",
                    "severity": "HIGH" if c1d > 50 else "MEDIUM",
                })
                continue

            # Check 2: 24h Revenue/Fee Flash Surge
            proto_id = str(p.get("id") or "")
            fee_info = fees_by_id.get(proto_id, {})
            fees_24h = fee_info.get("total24h") or 0
            if fees_24h >= self.MIN_SURGE_FEES and tvl > 0:
                fee_tvl = fees_24h / tvl
                if fee_tvl >= 0.01:  # 1%+ of total TVL generated in fees in a single day
                    seen_symbols.add(symbol)
                    anomalies.append({
                        "name": name,
                        "symbol": symbol,
                        "category": p.get("category", "DeFi"),
                        "tvl": tvl,
                        "reason": "Всплеск комиссий",
                        "metric_str": f"${fees_24h:,.0f}/день ({fee_tvl*100:.1f}% от TVL)",
                        "severity": "HIGH",
                    })

        # 2. CoinGecko: 24h Volume Turnover Anomalies
        markets = self.coingecko.fetch_markets(pages=2, force_refresh=force_refresh)
        for m in markets:
            sym = (m.get("symbol") or "").upper()
            if sym in seen_symbols:
                continue

            vol = m.get("total_volume") or 0
            mcap = m.get("market_cap") or 0
            if mcap > 0 and vol > 1_000_000:
                turnover = vol / mcap
                if turnover >= self.FLASH_TURNOVER_RATIO:
                    c24h = m.get("price_change_percentage_24h") or 0
                    sign = "+" if c24h > 0 else ""
                    anomalies.append({
                        "name": m.get("name", sym),
                        "symbol": sym,
                        "category": "Рыночный оборот",
                        "tvl": None,
                        "reason": "Аномальный оборот объёма",
                        "metric_str": f"{turnover:.2f}x от MCap (Цена: {sign}{c24h:.1f}%)",
                        "severity": "MEDIUM",
                    })

        return anomalies


def run_daily_sensor(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Runs daily sensor and outputs clean report with optional Telegram notification."""
    print("\n" + "=" * 65)
    print("⚡ ДНЕВНОЙ СЕНСОР: ЭКСПРЕСС-ПОИСК СУТОЧНЫХ АНОМАЛИЙ")
    print("=" * 65)
    print("Критерии: 24h TVL > +25%, аномальный оборот объёма > 0.5x, всплеск сборов")
    print("Затраты LLM / API Gemini: 0 (бесплатный сбор ончейн-данных)")
    print("-" * 65)

    sensor = DailySensor()
    anomalies = sensor.scan(force_refresh=force_refresh)

    if not anomalies:
        print("[OK] Рынок в нормальном диапазоне. Экстремальных аномалий не обнаружено.")
        print("     (Уведомление в Telegram не отправляется, чтобы не спамить).")
        print("=" * 65)
        return []

    print(f"[!] ОБНАРУЖЕНО {len(anomalies)} СУТОЧНЫХ АНОМАЛИЙ:\n")
    print(f"{'#':<3} {'Тикер':<8} {'Проект':<20} {'Тип аномалии':<24} {'Метрика'}")
    print("-" * 75)

    for i, a in enumerate(anomalies[:10], 1):
        name_short = (a['name'][:18] + "..") if len(a['name']) > 18 else a['name']
        print(f"{i:<3} {a['symbol']:<8} {name_short:<20} {a['reason']:<24} {a['metric_str']}")

    print("\n" + "=" * 65)
    print("[Telegram] Отправка flash-алерта...")
    try:
        notify_daily_flash(anomalies)
        print("[OK] Flash-алерт успешно доставлен в Telegram.")
    except Exception as e:
        print(f"[!] Ошибка отправки: {e}")
    print("=" * 65)

    return anomalies
