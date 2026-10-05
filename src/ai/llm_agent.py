import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_MODEL
from typing import List, Dict, Any

class LLMAgent:
    """Agent that analyzes project metrics using Gemini."""

    def __init__(self):
        self.api_key = GEMINI_API_KEY
        self.model_name = GEMINI_MODEL
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(self.model_name)
        else:
            self.model = None

    def summarize_candidates(self, candidates: List[Dict[str, Any]]) -> str:
        """Generates a short summary for the top radar candidates."""
        if not self.model:
            return "⚠️ GEMINI_API_KEY не установлен. Саммари от AI недоступно."

        prompt = (
            "Ты — опытный аналитик крипторынка (CAF / CVE методология).\n"
            "Тебе передан список топ-проектов с радара 'Emerging / Incubator' "
            "(высокий рост TVL, комиссии, хорошая эффективность капитала).\n"
            "Напиши короткое, емкое саммари для инвестора. Отметь 2-3 самых интересных проекта из списка "
            "и почему на них стоит обратить внимание, а какие можно пропустить из-за сомнительной токеномики "
            "или отсутствия реального захвата ценности (Value Capture).\n\n"
            "Кандидаты:\n"
        )

        for c in candidates:
            tvl_str = f"${c.get('tvl', 0):,.0f}" if c.get('tvl') else "N/A"
            c7d = f"+{c.get('change_7d', 0)}%"
            fees = f"${c.get('daily_fees', 0):,.0f}" if c.get('daily_fees') else "N/A"
            prompt += f"- {c.get('name')} ({c.get('symbol')}): Сектор {c.get('category')}, TVL: {tvl_str} ({c7d}), 24h Fees: {fees}, Score: {c.get('radar_score')}\n"

        prompt += "\nДай ответ на русском языке, структурно и без лишней воды."

        try:
            print("[AI] Запрашиваем саммари у Gemini...")
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"❌ Ошибка при генерации саммари: {str(e)}"
