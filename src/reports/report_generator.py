import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from config import REPORTS_DIR


class ReportGenerator:
    """Generates Markdown and CSV reports for CAF radar and screening."""

    def __init__(self, output_dir: Path = REPORTS_DIR):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_emerging_radar_report(
        self,
        candidates: List[Dict[str, Any]],
        top_n: int = 15,
        ai_summary: str = "",
    ) -> Path:
        """Saves emerging incubator radar candidates to Markdown & CSV."""
        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H%M")
        date_display = datetime.now().strftime("%Y-%m-%d %H:%M")

        md_path = self.output_dir / f"radar_emerging_{timestamp_str}.md"
        csv_path = self.output_dir / f"radar_emerging_{timestamp_str}.csv"

        # 1. Write CSV
        fieldnames = [
            "symbol",
            "name",
            "radar_score",
            "category",
            "tvl",
            "change_7d",
            "change_1m",
            "mcap",
            "mcap_tvl_ratio",
            "daily_fees",
            "daily_revenue",
            "url",
        ]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for c in candidates[:top_n]:
                writer.writerow(c)

        # 2. Write Markdown
        md_lines = [
            f"# CAF Radar: Emerging / Incubator Projects",
            f"**Дата отчёта:** {date_display}  ",
            f"**Критерии отбора:** TVL > $1M, 7d/30d динамика, генерация комиссий, капитализация вне топ-гигантов.  ",
            "",
            "| # | Проект | Тикер | Сектор | TVL | 7d TVL | 1m TVL | MCap / TVL | 24h Fees | Radar Score |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]

        for i, c in enumerate(candidates[:top_n], start=1):
            tvl_str = f"${c.get('tvl', 0):,.0f}" if c.get('tvl') else "—"
            c7d = c.get('change_7d', 0)
            c7d_str = f"+{c7d:.1f}%" if c7d > 0 else f"{c7d:.1f}%"
            c1m = c.get('change_1m', 0)
            c1m_str = f"+{c1m:.1f}%" if c1m > 0 else f"{c1m:.1f}%"
            ratio_str = f"{c.get('mcap_tvl_ratio'):.2f}x" if c.get('mcap_tvl_ratio') else "—"
            fees_val = c.get('daily_fees')
            fees_str = f"${fees_val:,.0f}" if fees_val else "—"
            score = c.get('radar_score', 0)

            md_lines.append(
                f"| {i} | **{c.get('name')}** | `{c.get('symbol')}` | {c.get('category')} | {tvl_str} | {c7d_str} | {c1m_str} | {ratio_str} | {fees_str} | **{score}** |"
            )

        if ai_summary:
            md_lines.extend([
                "",
                "---",
                "## 🤖 Аналитика от AI (LLM Agent)",
                ai_summary,
            ])

        md_lines.extend([
            "",
            "---",
            "### Рекомендации по дальнейшему анализу:",
            "1. Проверить экономический захват ценности токена (Economic Value Capture).",
            "2. Оценить график разлоков и соотношение FDV / MCap (Tokenomics).",
            "3. Изучить команду, аудит смарт-контрактов и зависимость от базовой сети (Fragility).",
        ])

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        return md_path

    def generate_cve_scoring_report(
        self,
        scores: List[Dict[str, Any]],
        title: str = "CAF / CVE Portfolio & Radar Scoring",
    ) -> Path:
        """Saves full 5-pillar CVE scoring report to Markdown."""
        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H%M")
        date_display = datetime.now().strftime("%Y-%m-%d %H:%M")
        md_path = self.output_dir / f"cve_scores_{timestamp_str}.md"

        md_lines = [
            f"# {title}",
            f"**Дата отчёта:** {date_display}  ",
            f"**Методология:** CVE 5-Pillars (Business Quality, Value Capture, Tokenomics, Resilience, Anti-Fragility)  ",
            "",
            "| # | Проект | Тикер | Уровень CVE | Composite Score | BQ (25%) | EVC (25%) | Tokenomics (20%) | Resilience (15%) | Safety (15%) |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]

        for i, s in enumerate(scores, start=1):
            p = s["pillars"]
            tier_badge = f"**{s['tier']}**"
            md_lines.append(
                f"| {i} | **{s['name']}** | `{s['symbol']}` | {tier_badge} | **{s['composite_score']}** | {p['business_quality']} | {p['value_capture']} | {p['tokenomics']} | {p['resilience']} | {p['safety_anti_fragility']} |"
            )

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        return md_path

    def generate_asymmetric_report(
        self,
        scored_candidates: List[Dict[str, Any]],
        basket_result: Dict[str, Any],
        top_n: int = 15,
    ) -> Path:
        """Saves Asymmetric 50x Alpha screening report to Markdown."""
        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H%M")
        date_display = datetime.now().strftime("%Y-%m-%d %H:%M")
        md_path = self.output_dir / f"asymmetric_50x_radar_{timestamp_str}.md"

        md_lines = [
            "# 🚀 CAF-Terminal: Asymmetric 50x–100x Alpha Screener",
            f"**Дата отчёта:** {date_display}  ",
            "**Эмпирический базис:** Архитектура SOL, TAO, HYPE, KAS, PENDLE, RUNE, INJ до фазы консенсуса.",
            "**Ключевые критерии:** FDV <= $300M, Float >= 60%, Friction Index (<= 1 Tier-1 CEX), Fees/TVL >= 1.5%.",
            "",
            "## 🎯 Топ кандидатов по шкале Asymmetric Alpha",
            "| # | Проект | Тикер | Alpha Score | Классификация | FDV ($) | Float | 24h Fees | TVL | Вердикт |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]

        for i, c in enumerate(scored_candidates[:top_n], start=1):
            fdv_val = c.get("metrics", {}).get("fdv", 0)
            fdv_str = f"${fdv_val:,.0f}" if fdv_val else "—"
            fl_val = c.get("metrics", {}).get("float_ratio")
            fl_str = f"{fl_val * 100:.0f}%" if fl_val is not None else "Fair/DEX"
            fees_val = c.get("metrics", {}).get("daily_fees", 0)
            fees_str = f"${fees_val:,.0f}" if fees_val else "—"
            tvl_val = c.get("metrics", {}).get("tvl", 0)
            tvl_str = f"${tvl_val:,.0f}" if tvl_val else "—"

            md_lines.append(
                f"| {i} | **{c.get('name')}** | `{c.get('symbol')}` | **{c.get('asymmetric_score')}** | {c.get('classification')} | {fdv_str} | {fl_str} | {fees_str} | {tvl_str} | `{c.get('verdict')}` |"
            )

        md_lines.extend([
            "",
            "---",
            "## 💼 Рекомендуемая корзина инкубатора (Лимит риска: 10.0%)",
            f"**Совокупная аллокация:** {basket_result.get('total_allocation_pct', 0)}%  ",
            f"**Буфер кэша инкубатора:** {basket_result.get('risk_cushion_unallocated_pct', 0)}%  ",
            "",
            "| Тикер | Проект | Score | Вес в портфеле (%) | Макс. убыток (%) | Выплата при 50x (%) |",
            "|---|---|---|---|---|---|",
        ])

        for b in basket_result.get("basket", []):
            md_lines.append(
                f"| `{b.get('symbol')}` | **{b.get('name')}** | {b.get('score')} | **{b.get('target_weight_pct')}%** | -{b.get('max_downside_pct')}% | **+{b.get('upside_50x_pct')}%** |"
            )

        model = basket_result.get("mathematical_model", {})
        if model:
            md_lines.extend([
                "",
                "### Математическая асимметрия корзины:",
                f"- **Худший сценарий (все позиции в ноль):** {model.get('base_downside_max')}",
                f"- **Сценарий 1 попадания в 50x (4 в ноль):** {model.get('payout_scenario_1_hit_50x')}",
                f"- **Сценарий 1 попадания в 20x (4 в ноль):** {model.get('payout_scenario_1_hit_20x')}",
            ])

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        return md_path
