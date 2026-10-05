"""
Multi-Agent Investment Committee for CAF-Terminal.

Architecture:
  SignalScout  → detects strong signals from data sources
  Analyst      → builds investment thesis for a candidate
  Skeptic      → systematically attacks that thesis
  CFO          → hears both sides and makes the final call

Decision flow:
  SignalScout fires → Analyst drafts thesis → Skeptic tears it apart
  → CFO renders verdict: INCUBATOR | FULL_CAF | PASS
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_MODEL


# ── Setup ─────────────────────────────────────────────────────────────────────

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def _make_model() -> Optional[genai.GenerativeModel]:
    if not GEMINI_API_KEY:
        return None
    return genai.GenerativeModel(GEMINI_MODEL)


# ── Domain types ──────────────────────────────────────────────────────────────

class Verdict(str, Enum):
    INCUBATOR  = "INCUBATOR"    # Add to watch-list, quick 15-min CAF screen
    FULL_CAF   = "FULL_CAF"     # Go deep — full 5-pillar analysis now
    PASS       = "PASS"         # Not worth the time this month


@dataclass
class Signal:
    """A detected market signal that triggers the committee."""
    name: str
    symbol: str
    category: str
    signal_type: str          # e.g. "TVL_SPIKE", "REVENUE_SURGE", "NEW_SECTOR", "DEV_ACTIVITY"
    signal_strength: float    # 0-100
    tvl: Optional[float] = None
    change_7d: Optional[float] = None
    daily_fees: Optional[float] = None
    daily_revenue: Optional[float] = None
    mcap: Optional[float] = None
    fdv_mcap_ratio: Optional[float] = None
    chains: List[str] = field(default_factory=list)
    notes: str = ""           # Free-form extra context


@dataclass
class CommitteeReport:
    """Full deliberation output from the 3-agent committee."""
    signal: Signal
    analyst_thesis: str
    skeptic_critique: str
    cfo_reasoning: str
    verdict: Verdict
    conviction_score: float   # 0-100, CFO's confidence in the verdict
    follow_up_actions: List[str] = field(default_factory=list)


# ── Signal Detector ────────────────────────────────────────────────────────────

class SignalDetector:
    """
    Filters raw protocol data to find strong signals.
    Philosophy: we don't scan 500 coins — we look for signals that tell us
    something UNUSUAL is happening. Only those trigger the committee.

    Signal types:
    - TVL_SPIKE:       7d TVL growth > threshold
    - REVENUE_SURGE:   daily revenue > threshold relative to TVL
    - CAPITAL_EFFICIENCY: very high fees/TVL ratio (hidden gem)
    - NEW_SECTOR:      category not seen before in our universe
    - UNLOCK_RISK:     FDV/MCap ratio extremely high — mark as danger signal
    """

    TVL_SPIKE_THRESHOLD   = 20.0    # % 7d TVL growth
    REVENUE_SURGE_MIN     = 5_000   # USD daily fees/revenue
    FEE_TVL_RATIO_MIN     = 0.01    # 1% daily fees/TVL → high capital efficiency
    UNLOCK_RISK_RATIO     = 5.0     # FDV/MCap above this → dilution danger

    def detect(
        self,
        protocols: List[Dict[str, Any]],
        known_categories: Optional[set] = None,
        min_tvl: float = 500_000,
        max_mcap: float = 2_000_000_000,
    ) -> List[Signal]:
        """
        Scans protocol list and returns only those that trigger a strong signal.
        Crucially: a project with NO signal gets ignored completely.
        """
        signals: List[Signal] = []
        known_categories = known_categories or set()

        for p in protocols:
            tvl      = p.get("tvl") or 0
            mcap     = p.get("mcap") or 0
            change7d = p.get("change_7d") or 0
            fees     = p.get("daily_fees") or 0
            revenue  = p.get("daily_revenue") or 0
            fdv_mcap = p.get("fdv_mcap_ratio")
            category = (p.get("category") or "Unknown").strip()
            name     = p.get("name", "")
            symbol   = (p.get("symbol") or "").upper()

            # Hard gates: too small or too big to be "emerging"
            if tvl < min_tvl:
                continue
            if mcap > max_mcap and mcap > 0:
                continue

            triggered_signals = []

            # 1. TVL Spike
            if change7d >= self.TVL_SPIKE_THRESHOLD:
                strength = min(100.0, 50 + change7d * 0.8)
                triggered_signals.append(("TVL_SPIKE", round(strength, 1)))

            # 2. Revenue / Fee Surge
            if fees >= self.REVENUE_SURGE_MIN or revenue >= self.REVENUE_SURGE_MIN:
                best_rev = max(fees, revenue)
                strength = min(100.0, 40 + best_rev / 1000)
                triggered_signals.append(("REVENUE_SURGE", round(strength, 1)))

            # 3. Capital Efficiency
            if tvl > 0 and fees > 0:
                fee_tvl = fees / tvl
                if fee_tvl >= self.FEE_TVL_RATIO_MIN:
                    strength = min(100.0, fee_tvl * 5000)
                    triggered_signals.append(("CAPITAL_EFFICIENCY", round(strength, 1)))

            # 4. New Sector (not in our tracked universe)
            if category and category not in known_categories and category != "Unknown":
                triggered_signals.append(("NEW_SECTOR", 60.0))

            if not triggered_signals:
                continue

            # Pick the strongest signal as primary
            primary_type, primary_strength = max(triggered_signals, key=lambda x: x[1])
            all_types = ", ".join(t for t, _ in triggered_signals)

            signals.append(Signal(
                name=name,
                symbol=symbol,
                category=category,
                signal_type=primary_type,
                signal_strength=primary_strength,
                tvl=tvl,
                change_7d=change7d,
                daily_fees=fees if fees else None,
                daily_revenue=revenue if revenue else None,
                mcap=mcap if mcap else None,
                fdv_mcap_ratio=fdv_mcap,
                chains=p.get("chains", []),
                notes=f"All triggered signals: {all_types}",
            ))

        # Sort by signal strength descending
        signals.sort(key=lambda s: s.signal_strength, reverse=True)
        return signals


# ── Agent Base ─────────────────────────────────────────────────────────────────

class _BaseAgent:
    ROLE: str = "Agent"
    SYSTEM_PROMPT: str = ""

    def __init__(self):
        self.model = _make_model()

    def _call(self, user_message: str) -> str:
        if not self.model:
            return f"[{self.ROLE}] API key not configured."
        try:
            full_prompt = f"{self.SYSTEM_PROMPT}\n\n{user_message}"
            response = self.model.generate_content(full_prompt)
            return response.text.strip()
        except Exception as e:
            return f"[{self.ROLE}] Error: {e}"

    @staticmethod
    def _format_signal(s: Signal) -> str:
        tvl_str   = f"${s.tvl:,.0f}"   if s.tvl   else "N/A"
        mcap_str  = f"${s.mcap:,.0f}"  if s.mcap  else "N/A"
        fees_str  = f"${s.daily_fees:,.0f}" if s.daily_fees else "N/A"
        rev_str   = f"${s.daily_revenue:,.0f}" if s.daily_revenue else "N/A"
        fdv_str   = f"{s.fdv_mcap_ratio:.2f}x" if s.fdv_mcap_ratio else "N/A"
        c7d_str   = f"+{s.change_7d:.1f}%" if s.change_7d and s.change_7d > 0 else (f"{s.change_7d:.1f}%" if s.change_7d else "N/A")
        return (
            f"Project: {s.name} ({s.symbol})\n"
            f"Sector: {s.category}\n"
            f"Signal: {s.signal_type} (strength {s.signal_strength}/100)\n"
            f"TVL: {tvl_str} | 7d TVL: {c7d_str}\n"
            f"Daily Fees: {fees_str} | Daily Revenue: {rev_str}\n"
            f"MCap: {mcap_str} | FDV/MCap: {fdv_str}\n"
            f"Chains: {', '.join(s.chains[:4]) or 'Unknown'}\n"
            f"Notes: {s.notes}"
        )


# ── Analyst Agent ──────────────────────────────────────────────────────────────

class AnalystAgent(_BaseAgent):
    """
    Role: builds an investment thesis.
    Asks: "Why SHOULD we look at this?"
    """
    ROLE = "Analyst"
    SYSTEM_PROMPT = """Ты — криптовалютный аналитик с опытом работы в венчурном фонде.
Твоя задача: для каждого проекта сформулировать ИНВЕСТИЦИОННЫЙ ТЕЗИС по методологии CAF/CVE.
Структура ответа всегда строго такая:

**ТЕЗИС:** Одно предложение — почему этот проект заслуживает внимания.

**СИГНАЛЫ В ПОЛЬЗУ:**
- Business Quality: что создаёт ров (реальный продукт, сеть, IP)?
- Value Capture: как токен захватывает ценность (buyback, fees, governance)?
- Momentum: что говорят данные (TVL, fees, пользователи)?

**КЛЮЧЕВЫЕ ВОПРОСЫ ДЛЯ ГЛУБОКОГО АНАЛИЗА:**
- 3 вопроса, которые НУЖНО проверить перед входом.

Лаконично, конкретно, только факты и логика. Без воды. На русском языке."""

    def build_thesis(self, signal: Signal) -> str:
        prompt = f"Построй инвестиционный тезис для следующего проекта:\n\n{self._format_signal(signal)}"
        return self._call(prompt)


# ── Skeptic Agent ──────────────────────────────────────────────────────────────

class SkepticAgent(_BaseAgent):
    """
    Role: systematically attacks the analyst's thesis.
    Asks: "Why SHOULDN'T we touch this?"
    """
    ROLE = "Skeptic"
    SYSTEM_PROMPT = """Ты — жёсткий риск-менеджер и скептик криптовалютных инвестиций.
Твоя задача: разобрать инвестиционный тезис аналитика и найти всё, что могло пойти не так.
Ты НЕ должен быть вежливым. Ты должен быть честным.

Структура ответа всегда такая:

**КОНТРТЕЗИС:** Одно предложение — главная причина НЕ инвестировать.

**РИСКИ И СЛАБЫЕ МЕСТА:**
- Value Capture риск: действительно ли токен захватывает ценность, или это иллюзия?
- Токеномика: навес предложения, инфляция, разлоки — что разрушит цену?
- Конкуренция: кто сделает это лучше и дешевле?
- Execution risk: команда, продукт, рынок — что может провалиться?

**КРАСНЫЕ ФЛАГИ:**
- Конкретные цифры или факты из данных, которые вызывают сомнение.

**ВЕРДИКТ СКЕПТИКА:** ПРОПУСТИТЬ / СМОТРЕТЬ С ОСТОРОЖНОСТЬЮ / ТЕРПИМО

Только конкретика. Ни слова лести. На русском языке."""

    def critique(self, signal: Signal, analyst_thesis: str) -> str:
        prompt = (
            f"Тезис аналитика по проекту {signal.name} ({signal.symbol}):\n\n"
            f"{analyst_thesis}\n\n"
            f"Данные проекта:\n{self._format_signal(signal)}\n\n"
            "Разбери этот тезис. Найди всё слабое. Не жалей."
        )
        return self._call(prompt)


# ── CFO Agent ──────────────────────────────────────────────────────────────────

class CFOAgent(_BaseAgent):
    """
    Role: hears analyst + skeptic, makes the final capital allocation decision.
    Asks: "Given both views, where does the risk/reward land?"
    Outputs: Verdict + conviction + follow-up actions.
    """
    ROLE = "CFO"
    SYSTEM_PROMPT = """Ты — финансовый директор крипто-инвестиционного фонда.
Ты только что выслушал аналитика (тезис) и скептика (критику) по одному проекту.
Твоя задача: принять ОКОНЧАТЕЛЬНОЕ РЕШЕНИЕ по методологии CAF.

Три возможных решения:
- **FULL_CAF**: Немедленно начать полный 5-столповый CAF-анализ. Только если сигналы очень сильные и риски управляемы.
- **INCUBATOR**: Добавить в список наблюдения. Сделать быстрый 15-минутный CAF-скрининг через месяц при подтверждении данных.
- **PASS**: Игнорировать полностью. Не тратить больше времени.

Структура ответа:

**РЕШЕНИЕ: [FULL_CAF / INCUBATOR / PASS]**

**УВЕРЕННОСТЬ: [0-100]%**

**ОБОСНОВАНИЕ:**
Почему именно это решение — 3-5 предложений. Взвесь аналитика против скептика.

**СЛЕДУЮЩИЕ ШАГИ:**
- Конкретные действия (что проверить, когда, какие метрики отслеживать).

Будь решительным. Нет — значит нет. Да — значит да. На русском языке."""

    def decide(self, signal: Signal, analyst_thesis: str, skeptic_critique: str) -> CommitteeReport:
        prompt = (
            f"ПРОЕКТ: {signal.name} ({signal.symbol})\n\n"
            f"=== ТЕЗИС АНАЛИТИКА ===\n{analyst_thesis}\n\n"
            f"=== КРИТИКА СКЕПТИКА ===\n{skeptic_critique}\n\n"
            f"=== ДАННЫЕ ===\n{self._format_signal(signal)}\n\n"
            "Вынеси решение."
        )
        raw = self._call(prompt)

        # Parse verdict from response
        verdict = Verdict.PASS
        if "FULL_CAF" in raw:
            verdict = Verdict.FULL_CAF
        elif "INCUBATOR" in raw:
            verdict = Verdict.INCUBATOR

        # Parse conviction score
        conviction = 50.0
        for line in raw.splitlines():
            if "УВЕРЕННОСТЬ" in line or "уверенность" in line:
                import re
                match = re.search(r"(\d+)", line)
                if match:
                    conviction = float(match.group(1))
                break

        # Extract follow-up actions (lines starting with -)
        actions = []
        in_actions = False
        for line in raw.splitlines():
            if "СЛЕДУЮЩИЕ ШАГИ" in line or "следующие шаги" in line.lower():
                in_actions = True
                continue
            if in_actions and line.strip().startswith("-"):
                actions.append(line.strip().lstrip("- "))

        return CommitteeReport(
            signal=signal,
            analyst_thesis=analyst_thesis,
            skeptic_critique=skeptic_critique,
            cfo_reasoning=raw,
            verdict=verdict,
            conviction_score=conviction,
            follow_up_actions=actions,
        )


# ── Investment Committee ────────────────────────────────────────────────────────

class InvestmentCommittee:
    """
    Orchestrates the 3-agent deliberation for a single signal.
    """

    def __init__(self):
        self.analyst = AnalystAgent()
        self.skeptic = SkepticAgent()
        self.cfo     = CFOAgent()

    def deliberate(self, signal: Signal) -> CommitteeReport:
        print(f"\n{'─'*60}")
        print(f"[COMMITTEE] Рассматривается: {signal.name} ({signal.symbol})")
        print(f"  Сигнал: {signal.signal_type} | Сила: {signal.signal_strength}/100")
        print(f"{'─'*60}")

        print("[ANALYST]  Формирую тезис...")
        thesis = self.analyst.build_thesis(signal)

        print("[SKEPTIC]  Атакую тезис...")
        critique = self.skeptic.critique(signal, thesis)

        print("[CFO]      Принимаю решение...")
        report = self.cfo.decide(signal, thesis, critique)

        verdict_display = {
            Verdict.FULL_CAF:  "FULL CAF - СРОЧНЫЙ АНАЛИЗ",
            Verdict.INCUBATOR: "INCUBATOR - ДОБАВИТЬ В НАБЛЮДЕНИЕ",
            Verdict.PASS:      "PASS - ПРОПУСТИТЬ",
        }

        print(f"\n  ВЕРДИКТ: {verdict_display[report.verdict]} (уверенность {report.conviction_score:.0f}%)")
        return report

    def run_monthly_scan(
        self,
        protocols: List[Dict[str, Any]],
        known_categories: Optional[set] = None,
        max_candidates: int = 5,
    ) -> List[CommitteeReport]:
        """
        Monthly radar run. Only processes top signals — not the whole market.
        Returns committee reports sorted by verdict priority (FULL_CAF first).
        """
        print("\n" + "="*60)
        print("[COMMITTEE] ЕЖЕМЕСЯЧНЫЙ СКАН: ПОИСК СИГНАЛОВ")
        print("="*60)

        detector = SignalDetector()
        signals = detector.detect(
            protocols,
            known_categories=known_categories,
        )

        if not signals:
            print("[!] Нет сильных сигналов в этом месяце. Пропускаем.")
            return []

        # Only deliberate on top N signals to avoid cost/time overload
        top_signals = signals[:max_candidates]
        print(f"[+] Обнаружено {len(signals)} сигналов. Комитет рассматривает топ-{len(top_signals)}.\n")

        reports: List[CommitteeReport] = []
        for s in top_signals:
            report = self.deliberate(s)
            reports.append(report)

        # Sort: FULL_CAF first, then INCUBATOR, then PASS
        priority = {Verdict.FULL_CAF: 0, Verdict.INCUBATOR: 1, Verdict.PASS: 2}
        reports.sort(key=lambda r: priority[r.verdict])
        return reports
