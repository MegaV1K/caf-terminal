import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from config import REPORTS_DIR
from src.ai.committee import CommitteeReport, Verdict


class CommitteeReportGenerator:
    """Generates Markdown reports from Investment Committee deliberations."""

    VERDICT_BADGE = {
        Verdict.FULL_CAF:  "🔴 FULL CAF",
        Verdict.INCUBATOR: "🟡 INCUBATOR",
        Verdict.PASS:      "⚪ PASS",
    }

    def __init__(self, output_dir: Path = REPORTS_DIR):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, reports: List[CommitteeReport]) -> Path:
        timestamp_str  = datetime.now().strftime("%Y-%m-%d_%H%M")
        date_display   = datetime.now().strftime("%Y-%m-%d %H:%M")
        md_path        = self.output_dir / f"committee_report_{timestamp_str}.md"

        lines = [
            "# CAF Investment Committee Report",
            f"**Дата:** {date_display}  ",
            f"**Методология:** 3-агентный комитет (Analyst → Skeptic → CFO)  ",
            f"**Рассмотрено сигналов:** {len(reports)}",
            "",
        ]

        # Summary table
        lines += [
            "## Сводная таблица решений",
            "",
            "| # | Проект | Тикер | Сектор | Сигнал | Вердикт | Уверенность |",
            "|---|---|---|---|---|---|---|",
        ]
        for i, r in enumerate(reports, 1):
            s = r.signal
            badge = self.VERDICT_BADGE[r.verdict]
            lines.append(
                f"| {i} | **{s.name}** | `{s.symbol}` | {s.category} | "
                f"{s.signal_type} ({s.signal_strength:.0f}) | {badge} | {r.conviction_score:.0f}% |"
            )

        # Detailed section per report
        for i, r in enumerate(reports, 1):
            s = r.signal
            badge = self.VERDICT_BADGE[r.verdict]

            lines += [
                "",
                "---",
                f"## {i}. {s.name} ({s.symbol}) — {badge}",
                "",
                f"**Сектор:** {s.category} | **Сигнал:** {s.signal_type} | **Сила сигнала:** {s.signal_strength:.0f}/100  ",
                f"**TVL:** {'${:,.0f}'.format(s.tvl) if s.tvl else 'N/A'} | "
                f"**7d TVL:** {('+' if (s.change_7d or 0) > 0 else '')+str(round(s.change_7d or 0, 1))+'%'} | "
                f"**24h Fees:** {'${:,.0f}'.format(s.daily_fees) if s.daily_fees else 'N/A'}  ",
                "",
                "### Тезис аналитика",
                r.analyst_thesis,
                "",
                "### Критика скептика",
                r.skeptic_critique,
                "",
                "### Решение CFO",
                r.cfo_reasoning,
            ]

            if r.follow_up_actions:
                lines += ["", "**Следующие шаги:**"]
                for action in r.follow_up_actions:
                    lines.append(f"- {action}")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return md_path
