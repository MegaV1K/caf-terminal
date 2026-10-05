"""
Multi-Agent Investment Committee for CAF-Terminal.

Architecture:
  SignalDetector → detects strong signals from data sources
  AnalystAgent   → builds investment thesis for a candidate
  SkepticAgent   → systematically attacks that thesis
  CFOAgent       → hears both sides and makes the final call (JSON output)

Decision flow:
  SignalDetector fires → Analyst drafts thesis → Skeptic tears it apart
  → CFO renders verdict: INCUBATOR | FULL_CAF | PASS

v2 Improvements:
  - Fixed MCap filter: protocols with mcap=0 are now filtered by TVL proxy ($50M cap)
  - CFO uses structured JSON output instead of regex parsing
  - Migrated to google.genai SDK (no more FutureWarning)
  - Model cascade via shared gemini_client module
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from src.ai.gemini_client import generate, generate_json


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
    signal_type: str          # e.g. "TVL_SPIKE", "REVENUE_SURGE", "DEV_ACTIVITY_SURGE"
    signal_strength: float    # 0-100
    tvl: Optional[float] = None
    change_7d: Optional[float] = None
    daily_fees: Optional[float] = None
    daily_revenue: Optional[float] = None
    mcap: Optional[float] = None
    fdv_mcap_ratio: Optional[float] = None
    vol_mcap_ratio: Optional[float] = None
    dev_score: Optional[float] = None
    commits_30d: Optional[int] = None
    github_repo: Optional[str] = None
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

    Filters applied in order:
    1. TVL must be > min_tvl ($2M) — proof of real capital
    2. MCap filter (v2 fix):
       - If mcap is known and > $300M → skip (not emerging)
       - If mcap is unknown (0/null) AND tvl > $50M → skip (large protocol, just no data)
    3. At least ONE strong signal must fire:
       - TVL_SPIKE:          7d TVL growth > 30%
       - REVENUE_SURGE:      daily fees > $10k AND fees/TVL > 0.5%
       - CAPITAL_EFFICIENCY: fees/TVL > 2% (hidden gem economics)
       - NEW_SECTOR:         category we haven't tracked before
       - DEV_ACTIVITY_SURGE: GitHub commits/score above threshold
    """

    TVL_SPIKE_THRESHOLD    = 30.0      # % 7d TVL growth
    REVENUE_SURGE_MIN      = 10_000    # USD daily fees
    FEE_TVL_RATIO_MIN      = 0.005     # 0.5% daily fees/TVL
    CAPITAL_EFF_THRESHOLD  = 0.02      # 2% daily fees/TVL = ultra-efficient
    UNLOCK_RISK_RATIO      = 5.0       # FDV/MCap above this → dilution danger

    # v2: If mcap is unknown (0), cap TVL at this value to avoid passing giants
    MAX_TVL_WHEN_MCAP_UNKNOWN = 50_000_000  # $50M TVL proxy for "unknown mcap but large"

    def detect(
        self,
        protocols: List[Dict[str, Any]],
        known_categories: Optional[set] = None,
        volume_anomalies: Optional[List[Dict[str, Any]]] = None,
        trending_coins: Optional[List[Dict[str, Any]]] = None,
        github_scout: Optional[Any] = None,
        min_tvl: float = 2_000_000,
        max_mcap: float = 300_000_000,
    ) -> List[Signal]:
        """
        Scans multi-source data: DefiLlama (TVL/fees), CoinGecko (volume/trending),
        and GitHub (developer activity).
        Only coins triggering strong signals are returned.
        """
        signals: List[Signal] = []
        known_categories = known_categories or set()
        seen_symbols: set = set()

        # 1. Process On-Chain Protocols (DefiLlama + GitHub)
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

            # Gate 1: minimum TVL (real capital at risk)
            if tvl < min_tvl:
                continue

            # Gate 2 (v2 fix): MCap filter that handles unknown MCap correctly
            if mcap > 0 and mcap > max_mcap:
                # Known large-cap → skip, not emerging
                continue
            elif mcap == 0 and tvl > self.MAX_TVL_WHEN_MCAP_UNKNOWN:
                # Unknown MCap + very large TVL → probably a giant (Lido, AAVE, etc.)
                # with missing data; skip to avoid false positives
                continue

            triggered_signals = []

            # Signal 1: TVL Spike
            if change7d >= self.TVL_SPIKE_THRESHOLD:
                strength = min(100.0, 50 + change7d * 0.6)
                triggered_signals.append(("TVL_SPIKE", round(strength, 1)))

            # Signal 2: Revenue Surge
            if fees >= self.REVENUE_SURGE_MIN and tvl > 0:
                fee_tvl = fees / tvl
                if fee_tvl >= self.FEE_TVL_RATIO_MIN:
                    strength = min(100.0, 40 + fee_tvl * 8000)
                    triggered_signals.append(("REVENUE_SURGE", round(strength, 1)))

            # Signal 3: Capital Efficiency
            if tvl > 0 and fees > 0:
                fee_tvl = fees / tvl
                if fee_tvl >= self.CAPITAL_EFF_THRESHOLD:
                    strength = min(100.0, fee_tvl * 3000)
                    triggered_signals.append(("CAPITAL_EFFICIENCY", round(strength, 1)))

            # Signal 4: New Sector
            if category and category not in known_categories and category != "Unknown":
                triggered_signals.append(("NEW_SECTOR", 55.0))

            # Signal 5: GitHub Developer Momentum (fast O(1) in-memory check for known repos)
            dev_metrics = {}
            if github_scout and symbol:
                repo_name = github_scout.get_repo_for_symbol(symbol)
                if repo_name:
                    dev_metrics = github_scout.fetch_repo_metrics(repo_name)
                    commits = dev_metrics.get("commits_30d", 0)
                    dev_score = dev_metrics.get("dev_score", 0)
                    if commits >= 20 or dev_score >= 70:
                        triggered_signals.append(("DEV_ACTIVITY_SURGE", round(dev_score, 1)))

            if not triggered_signals:
                continue

            primary_type, primary_strength = max(triggered_signals, key=lambda x: x[1])
            all_types = ", ".join(t for t, _ in triggered_signals)
            seen_symbols.add(symbol)

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
                dev_score=dev_metrics.get("dev_score"),
                commits_30d=dev_metrics.get("commits_30d"),
                github_repo=dev_metrics.get("repo"),
                chains=p.get("chains", []),
                notes=f"All triggered signals: {all_types}",
            ))

        # 2. Process Market Volume Anomalies (CoinGecko)
        if volume_anomalies:
            for va in volume_anomalies:
                sym = va.get("symbol", "").upper()
                if sym in seen_symbols:
                    continue  # already evaluated with on-chain data

                ratio = va.get("vol_mcap_ratio", 0)
                if ratio >= 0.35:  # high turnover signal
                    strength = min(100.0, 45.0 + ratio * 40.0)
                    seen_symbols.add(sym)

                    dev_metrics = {}
                    if github_scout:
                        repo = github_scout.get_repo_for_symbol(sym)
                        if repo:
                            dev_metrics = github_scout.fetch_repo_metrics(repo)

                    signals.append(Signal(
                        name=va.get("name", sym),
                        symbol=sym,
                        category="Market Mover / Emerging",
                        signal_type="VOLUME_ANOMALY",
                        signal_strength=round(strength, 1),
                        mcap=va.get("mcap"),
                        fdv_mcap_ratio=va.get("fdv_mcap_ratio"),
                        vol_mcap_ratio=ratio,
                        dev_score=dev_metrics.get("dev_score"),
                        commits_30d=dev_metrics.get("commits_30d"),
                        github_repo=dev_metrics.get("repo"),
                        notes=f"Turnover: {ratio}x volume/mcap. 7d change: {va.get('change_7d')}%",
                    ))

        # 3. Process Trending Coins (CoinGecko Trending)
        if trending_coins:
            for tc in trending_coins[:5]:
                sym = tc.get("symbol", "").upper()
                if sym in seen_symbols:
                    continue
                seen_symbols.add(sym)
                signals.append(Signal(
                    name=tc.get("name", sym),
                    symbol=sym,
                    category="Trending Search Narrative",
                    signal_type="TRENDING_ATTENTION",
                    signal_strength=72.0,
                    notes=f"Top search attention rank: {tc.get('score', 0) + 1}",
                ))

        # Sort all signals by strength descending
        signals.sort(key=lambda s: s.signal_strength, reverse=True)

        # Enrich ONLY top candidates with dynamic GitHub repo search (max 5 queries)
        if github_scout and not getattr(github_scout, "_search_rate_limited", False):
            for s in signals[:5]:
                if s.dev_score is None:
                    discovered = github_scout.search_repo(s.name)
                    if discovered:
                        m = github_scout.fetch_repo_metrics(discovered)
                        s.dev_score = m.get("dev_score")
                        s.commits_30d = m.get("commits_30d")
                        s.github_repo = m.get("repo")

        return signals


# ── Shared formatting ──────────────────────────────────────────────────────────

def _format_signal(s: Signal) -> str:
    tvl_str  = f"${s.tvl:,.0f}"   if s.tvl   else "N/A"
    mcap_str = f"${s.mcap:,.0f}"  if s.mcap  else "N/A"
    fees_str = f"${s.daily_fees:,.0f}" if s.daily_fees else "N/A"
    rev_str  = f"${s.daily_revenue:,.0f}" if s.daily_revenue else "N/A"
    fdv_str  = f"{s.fdv_mcap_ratio:.2f}x" if s.fdv_mcap_ratio else "N/A"
    c7d_str  = (f"+{s.change_7d:.1f}%" if (s.change_7d or 0) > 0
                else (f"{s.change_7d:.1f}%" if s.change_7d else "N/A"))
    vol_str  = f"{s.vol_mcap_ratio:.2f}x" if s.vol_mcap_ratio else "N/A"
    dev_str  = (
        f"{s.dev_score:.0f}/100 (Commits 30d: {s.commits_30d or 0}, repo: {s.github_repo})"
        if s.dev_score is not None else "N/A"
    )
    return (
        f"Project: {s.name} ({s.symbol})\n"
        f"Sector: {s.category}\n"
        f"Signal: {s.signal_type} (strength {s.signal_strength}/100)\n"
        f"TVL: {tvl_str} | 7d TVL: {c7d_str}\n"
        f"Daily Fees: {fees_str} | Daily Revenue: {rev_str}\n"
        f"MCap: {mcap_str} | FDV/MCap: {fdv_str} | Volume/MCap: {vol_str}\n"
        f"Developer Health (GitHub): {dev_str}\n"
        f"Chains: {', '.join(s.chains[:4]) or 'Unknown'}\n"
        f"Notes: {s.notes}"
    )


# ── Analyst Agent ──────────────────────────────────────────────────────────────

class AnalystAgent:
    """Role: builds an investment thesis. Asks: 'Why SHOULD we look at this?'"""

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
        prompt = f"Построй инвестиционный тезис для следующего проекта:\n\n{_format_signal(signal)}"
        return generate(prompt, system_instruction=self.SYSTEM_PROMPT)


# ── Skeptic Agent ──────────────────────────────────────────────────────────────

class SkepticAgent:
    """Role: systematically attacks the analyst's thesis. Asks: 'Why SHOULDN'T we touch this?'"""

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
            f"Данные проекта:\n{_format_signal(signal)}\n\n"
            "Разбери этот тезис. Найди всё слабое. Не жалей."
        )
        return generate(prompt, system_instruction=self.SYSTEM_PROMPT)


# ── CFO Agent ──────────────────────────────────────────────────────────────────

class CFOAgent:
    """
    Role: hears analyst + skeptic, makes the final capital allocation decision.
    v2: Uses structured JSON output for reliable verdict parsing.
    """

    SYSTEM_PROMPT = """Ты — финансовый директор крипто-инвестиционного фонда.
Ты только что выслушал аналитика (тезис) и скептика (критику) по одному проекту.
Твоя задача: принять ОКОНЧАТЕЛЬНОЕ РЕШЕНИЕ по методологии CAF.

Три возможных решения:
- FULL_CAF: Немедленно начать полный 5-столповый CAF-анализ. Только если сигналы очень сильные и риски управляемы.
- INCUBATOR: Добавить в список наблюдения. Сделать быстрый 15-минутный CAF-скрининг через месяц.
- PASS: Игнорировать полностью. Не тратить больше времени.

Отвечай СТРОГО в формате JSON (никакого текста вне JSON):
{
  "verdict": "FULL_CAF | INCUBATOR | PASS",
  "conviction": <число от 0 до 100>,
  "reasoning": "<3-5 предложений почему именно это решение>",
  "next_steps": ["<действие 1>", "<действие 2>", "<действие 3>"]
}

Будь решительным. На русском языке."""

    def decide(self, signal: Signal, analyst_thesis: str, skeptic_critique: str) -> CommitteeReport:
        prompt = (
            f"ПРОЕКТ: {signal.name} ({signal.symbol})\n\n"
            f"=== ТЕЗИС АНАЛИТИКА ===\n{analyst_thesis}\n\n"
            f"=== КРИТИКА СКЕПТИКА ===\n{skeptic_critique}\n\n"
            f"=== ДАННЫЕ ===\n{_format_signal(signal)}\n\n"
            "Вынеси решение в формате JSON."
        )

        data = generate_json(
            prompt,
            system_instruction=self.SYSTEM_PROMPT,
            fallback={"verdict": "PASS", "conviction": 50, "reasoning": "Parse error", "next_steps": []},
        )

        # Safe verdict parsing from structured JSON
        raw_verdict = str(data.get("verdict", "PASS")).upper().strip()
        if raw_verdict == "FULL_CAF":
            verdict = Verdict.FULL_CAF
        elif raw_verdict == "INCUBATOR":
            verdict = Verdict.INCUBATOR
        else:
            verdict = Verdict.PASS

        conviction = float(data.get("conviction", 50))
        conviction = max(0.0, min(100.0, conviction))  # clamp to [0, 100]
        reasoning = data.get("reasoning", "")
        next_steps = data.get("next_steps", [])
        if isinstance(next_steps, str):
            next_steps = [next_steps]

        return CommitteeReport(
            signal=signal,
            analyst_thesis=analyst_thesis,
            skeptic_critique=skeptic_critique,
            cfo_reasoning=reasoning,
            verdict=verdict,
            conviction_score=conviction,
            follow_up_actions=next_steps,
        )


# ── Investment Committee ────────────────────────────────────────────────────────

class InvestmentCommittee:
    """Orchestrates the 3-agent deliberation for a single signal."""

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

        print("[CFO]      Принимаю решение (JSON)...")
        report = self.cfo.decide(signal, thesis, critique)

        verdict_display = {
            Verdict.FULL_CAF:  "[!!!] FULL CAF - СРОЧНЫЙ АНАЛИЗ",
            Verdict.INCUBATOR: "[+]   INCUBATOR - ДОБАВИТЬ В НАБЛЮДЕНИЕ",
            Verdict.PASS:      "[-]   PASS - ПРОПУСТИТЬ",
        }
        print(f"\n  ВЕРДИКТ: {verdict_display[report.verdict]} (уверенность {report.conviction_score:.0f}%)")
        return report

    def run_monthly_scan(
        self,
        protocols: List[Dict[str, Any]],
        known_categories: Optional[set] = None,
        volume_anomalies: Optional[List[Dict[str, Any]]] = None,
        trending_coins: Optional[List[Dict[str, Any]]] = None,
        github_scout: Optional[Any] = None,
        max_candidates: int = 5,
    ) -> List[CommitteeReport]:
        """
        Monthly radar run across multi-source signals.
        Only processes top N signals — not the whole market.
        Returns committee reports sorted by verdict priority (FULL_CAF first).
        """
        print("\n" + "="*60)
        print("[COMMITTEE] ЕЖЕМЕСЯЧНЫЙ СКАН: ПОИСК СИГНАЛОВ")
        print("="*60)

        detector = SignalDetector()
        signals = detector.detect(
            protocols=protocols,
            known_categories=known_categories,
            volume_anomalies=volume_anomalies,
            trending_coins=trending_coins,
            github_scout=github_scout,
        )

        if not signals:
            print("[!] Нет сильных сигналов в этом цикле. Пропускаем.")
            return []

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
