"""
Tests for Deep-Dive Factsheet Generator and Corporate Pre-farm penalty.
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scoring.caf_scorer import CAFScorer
from src.reports.deep_dive import DeepDiveEngine


def test_corporate_prefarm_penalty_applied():
    """XCH or tokens with is_corporate_prefarm=True must receive safety penalty."""
    clean_payload = {
        "symbol": "CLEAN",
        "name": "Clean Network",
        "category": "layer 1",
        "mcap": 100_000_000,
        "fdv": 105_000_000,
        "rank": 80,
    }
    corp_payload = {
        "symbol": "XCH",
        "name": "Chia Network",
        "category": "layer 1",
        "mcap": 100_000_000,
        "fdv": 105_000_000,
        "rank": 80,
        "is_corporate_prefarm": True,
    }

    res_clean = CAFScorer.calculate_cve_score(clean_payload)
    res_corp = CAFScorer.calculate_cve_score(corp_payload)

    safety_clean = res_clean["pillars"]["safety_anti_fragility"]
    safety_corp = res_corp["pillars"]["safety_anti_fragility"]

    assert safety_clean > safety_corp, f"Expected {safety_clean} > {safety_corp}"
    assert (safety_clean - safety_corp) == 20.0, "Expected exactly 20.0 pts penalty for corporate pre-farm"


def test_deep_dive_generator_creates_file(tmp_path):
    """DeepDiveEngine must generate a 10-point markdown dossier report."""
    engine = DeepDiveEngine(output_dir=tmp_path)
    engine.cg.fetch_markets = MagicMock(return_value=[])
    engine.cg.get_token_metrics = MagicMock(return_value={"ARB": {"name": "Arbitrum", "mcap": 2_000_000_000, "rank": 40}})
    engine.llama.fetch_protocols = MagicMock(return_value=[{"symbol": "ARB", "name": "Arbitrum", "tvl": 3_000_000_000, "category": "layer 2"}])
    engine.llama.fetch_fees_and_revenue = MagicMock(return_value={"protocols": []})
    engine.github.get_repo_for_symbol = MagicMock(return_value=None)

    mock_dossier = "# 🧱 1. Founders\nOffchain Labs\n# 🪙 2. Tokenomics\n10B ARB\n# 🧾 10. Verdict\nPASS"

    with patch("src.reports.deep_dive.generate", return_value=mock_dossier):
        report_path = engine.generate_dossier("ARB")
        assert report_path.exists()
        content = report_path.read_text(encoding="utf-8")
        assert "Институциональное Досье CAF" in content
        assert "Founders" in content
        assert "Tokenomics" in content
