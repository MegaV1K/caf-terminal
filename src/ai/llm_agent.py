"""LLM Agent for emerging radar summaries — uses new google.genai SDK."""

from typing import Any, Dict, List
from src.ai.gemini_client import generate


class LLMAgent:
    """Agent that analyzes project metrics using Gemini."""

    SYSTEM_PROMPT = (
        "Ты — опытный аналитик крипторынка (CAF / CVE методология). "
        "Твой стиль: лаконично, конкретно, без маркетинга. Отвечаешь на русском языке."
    )

    def summarize_candidates(self, candidates: List[Dict[str, Any]]) -> str:
        """Generates a short summary for the top radar candidates."""
        prompt = (
            "Тебе передан список топ-проектов с радара 'Emerging / Incubator' "
            "(высокий рост TVL, комиссии, хорошая эффективность капитала).\n"
            "Напиши короткое, емкое саммари для инвестора. Отметь 2-3 самых интересных "
            "и почему, а какие можно пропустить из-за сомнительной токеномики или "
            "отсутствия реального захвата ценности (Value Capture).\n\n"
            "Кандидаты:\n"
        )

        for c in candidates:
            tvl_str = f"${c.get('tvl', 0):,.0f}" if c.get("tvl") else "N/A"
            c7d = f"+{c.get('change_7d', 0)}%"
            fees = f"${c.get('daily_fees', 0):,.0f}" if c.get("daily_fees") else "N/A"
            prompt += (
                f"- {c.get('name')} ({c.get('symbol')}): Сектор {c.get('category')}, "
                f"TVL: {tvl_str} ({c7d}), 24h Fees: {fees}, Score: {c.get('radar_score')}\n"
            )

        prompt += "\nДай ответ структурно и без лишней воды."

        print("[AI] Запрашиваем саммари у Gemini...")
        return generate(prompt, system_instruction=self.SYSTEM_PROMPT)
