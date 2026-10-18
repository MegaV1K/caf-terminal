"""
Tests for Asymmetric Alpha 50x–100x Screener and Incubator Sizing Engine.
"""
import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from src.scoring.asymmetric_screener import AsymmetricAlphaScorer
from src.scoring.caf_scorer import CAFScorer
from src.scouts.defillama import DefiLlamaScout


def test_asymmetric_scoring_fair_launch_unicorn():
    """Early Kaspa/Bittensor-like profile: Fair launch, sub-$50M FDV, 0 Tier-1 CEX, custom VM/arch."""
    candidate = {
        "symbol": "KAS-EARLY",
        "name": "Early BlockDAG",
        "category": "layer 1",
        "mcap": 15_000_000,
        "fdv": 15_000_000,
        "tvl": 2_000_000,
        "daily_fees": 8_000,
        "exchanges": ["tradeogre", "txbit"],  # 0 Tier-1 CEX
        "is_fair_launch": True,
        "chains": ["blockdag"],
    }
    result = AsymmetricAlphaScorer.score_candidate(candidate)
    assert result["asymmetric_score"] >= 80.0, f"Expected score >= 80, got {result['asymmetric_score']}"
    assert result["verdict"] == "INCUBATOR_BUY"
    assert result["classification"] == "Asymmetric Prime (50x Candidate)"
    assert result["pillars"]["headroom"] >= 85.0
    assert result["pillars"]["clean_float"] == 100.0
    assert result["pillars"]["friction"] == 100.0


def test_asymmetric_scoring_vc_unlock_trap():
    """Predatory VC low-float coin: $5B FDV, 10% float, listed on Binance & Coinbase, generic copy-paste."""
    candidate = {
        "symbol": "VC-DUMP",
        "name": "Generic Rollup",
        "category": "layer 2",
        "mcap": 500_000_000,
        "fdv": 5_000_000_000,  # $5B FDV!
        "tvl": 80_000_000,
        "daily_fees": 1_200,
        "exchanges": ["binance", "coinbase", "okx", "bybit"],  # Fully saturated CEXs
        "is_fair_launch": False,
        "chains": ["ethereum"],
    }
    result = AsymmetricAlphaScorer.score_candidate(candidate)
    assert result["asymmetric_score"] < 45.0, f"Expected score < 45, got {result['asymmetric_score']}"
    assert result["verdict"] == "PASS"
    assert result["pillars"]["headroom"] == 0.0  # Disqualified on FDV headroom
    assert result["pillars"]["friction"] <= 20.0 # Disqualified on friction


def test_asymmetric_scoring_pendle_v2_breakout():
    """Pendle V2 bottom profile: $30M FDV, 75% float, high fee/TVL, novel AMM."""
    candidate = {
        "symbol": "PENDLE-V2",
        "name": "Yield Split AMM",
        "category": "yield",
        "mcap": 25_000_000,
        "fdv": 32_000_000,
        "tvl": 12_000_000,
        "daily_fees": 15_000,  # Annualized fees $5.4M on $12M TVL -> 45% efficiency
        "exchanges": ["uniswap"],
        "is_fair_launch": False,
        "chains": ["ethereum", "arbitrum"],
    }
    result = CAFScorer.score_asymmetric_50x(candidate)
    assert result["asymmetric_score"] >= 80.0
    assert result["pillars"]["fee_efficiency"] == 100.0
    assert result["verdict"] == "INCUBATOR_BUY"


def test_incubator_basket_sizing_and_payoff():
    """Incubator basket must allocate exactly 10% total risk budget across top candidates."""
    candidates = [
        {"symbol": f"ALPHA{i}", "name": f"Project {i}", "asymmetric_score": 88.0 - i * 2, "classification": "Asymmetric Prime"}
        for i in range(7)
    ]
    basket_res = AsymmetricAlphaScorer.build_incubator_basket(candidates, total_budget_pct=10.0, per_asset_target=2.0, max_assets=5)
    
    assert basket_res["total_allocation_pct"] == 10.0
    assert len(basket_res["basket"]) == 5
    for item in basket_res["basket"]:
        assert item["target_weight_pct"] == 2.0
        assert item["max_downside_pct"] == 2.0
        assert item["upside_50x_pct"] == 100.0  # 2.0% * 50 = +100%

    assert "+92.0% net to total portfolio" in basket_res["mathematical_model"]["payout_scenario_1_hit_50x"]


def test_defillama_asymmetric_filter_filters_high_fdv():
    """Scout get_asymmetric_50x_candidates must exclude protocols exceeding $300M FDV."""
    scout = DefiLlamaScout()
    # Mock protocols
    mock_protocols = [
        {"id": "1", "name": "Tiny Gem", "symbol": "GEM", "tvl": 2_000_000, "mcap": 15_000_000, "fdv": 20_000_000},
        {"id": "2", "name": "Mega Giant", "symbol": "GIANT", "tvl": 500_000_000, "mcap": 8_000_000_000, "fdv": 12_000_000_000},
    ]
    mock_fees = {
        "protocols": [
            {"defillamaId": "1", "total24h": 5_000},
            {"defillamaId": "2", "total24h": 200_000},
        ]
    }
    scout.fetch_protocols = lambda force_refresh=False: mock_protocols
    scout.fetch_fees_and_revenue = lambda force_refresh=False: mock_fees

    filtered = scout.get_asymmetric_50x_candidates(min_tvl=500_000, max_fdv=300_000_000)
    assert len(filtered) == 1
    assert filtered[0]["symbol"] == "GEM"
    assert filtered[0]["daily_fees"] == 5_000
