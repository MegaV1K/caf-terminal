"""
Tests for 4-Agent Investment Committee (Orchestrator → Analyst → Skeptic → CFO).
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ai.committee import (
    CommitteeOrchestrator,
    InvestmentCommittee,
    Signal,
    Verdict,
)


def test_orchestrator_initialization_and_brief():
    """Orchestrator must produce a structured briefing given signal and cluster exposure."""
    orchestrator = CommitteeOrchestrator()
    signal = Signal(
        name="TestProtocol",
        symbol="TEST",
        category="Derivatives",
        signal_type="REVENUE_SURGE",
        signal_strength=85.0,
        tvl=10_000_000,
        daily_fees=25_000,
        mcap=15_000_000,
    )
    cluster_exposure = {"Ethereum DeFi / Lending": 25.0, "Solana Ecosystem": 22.0}

    mock_brief = "1. СТРАТЕГИЧЕСКИЙ ФОКУС: Высокая доходность\n2. ЗАДАНИЕ АНАЛИТИКУ: Проверить EVC\n3. ЗАДАНИЕ СКЕПТИКУ: Проверить разлоки"

    with patch("src.ai.committee.generate", return_value=mock_brief) as mock_gen:
        brief = orchestrator.prepare_brief(signal, cluster_exposure=cluster_exposure)
        assert "СТРАТЕГИЧЕСКИЙ ФОКУС" in brief
        assert mock_gen.called


def test_4_agent_deliberation_flow():
    """Verifies that deliberate() executes all 4 agents in sequence and populates orchestrator_brief."""
    committee = InvestmentCommittee()
    signal = Signal(
        name="AlphaFi",
        symbol="ALPH",
        category="Yield",
        signal_type="TVL_SPIKE",
        signal_strength=90.0,
        tvl=5_000_000,
        change_7d=65.0,
    )

    mock_brief = "Стратегический бриф от Оркестратора"
    mock_thesis = "Тезис аналитика"
    mock_critique = "Критика скептика"
    mock_cfo_json = {
        "verdict": "INCUBATOR",
        "conviction": 75.0,
        "reasoning": "Хорошая динамика, берем в наблюдение.",
        "next_steps": ["Проверить аудит", "Ждать 30 дней"],
    }

    with patch("src.ai.committee.generate", side_effect=[mock_brief, mock_thesis, mock_critique]), \
         patch("src.ai.committee.generate_json", return_value=mock_cfo_json):
        report = committee.deliberate(signal, cluster_exposure={"Yield": 5.0})

        assert report.signal.symbol == "ALPH"
        assert report.orchestrator_brief == mock_brief
        assert report.analyst_thesis == mock_thesis
        assert report.skeptic_critique == mock_critique
        assert report.verdict == Verdict.INCUBATOR
        assert report.conviction_score == 75.0
        assert len(report.follow_up_actions) == 2
