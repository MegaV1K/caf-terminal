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
