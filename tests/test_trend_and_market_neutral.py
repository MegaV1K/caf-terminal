"""
Tests for PriceTrendGate, HardInflationGate, and MarketNeutralEngine.
"""

import sys
from pathlib import Path
import pytest

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.risk.trend_gate import PriceTrendGate
from src.risk.inflation_gate import HardInflationGate
from src.risk.market_neutral import MarketNeutralEngine
from src.risk.risk_manager import InstitutionalRiskManager


def test_trend_gate_blocks_downtrend_assets():
    gate = PriceTrendGate(ema_period=200)

    # Asset below 200 EMA
    res_down = gate.evaluate_trend(
        symbol="JUP",
        current_price=0.80,
        ema_200=1.10,
    )
    assert not res_down["is_uptrend"]
    assert res_down["action"] == "DEFENSIVE_USDC_PRESERVATION"
    assert res_down["effective_multiplier"] == 0.0
    assert "USDC_YIELD_RESERVE" in res_down["capital_destination"]

    # Asset above 200 EMA
    res_up = gate.evaluate_trend(
        symbol="SOL",
        current_price=180.0,
        ema_200=150.0,
    )
    assert res_up["is_uptrend"]
    assert res_up["action"] == "ALLOCATE_TARGET_WEIGHT"
    assert res_up["effective_multiplier"] == 1.0


def test_trend_gate_portfolio_filtering_redirects_to_usdc():
    gate = PriceTrendGate(ema_period=200)
    target_weights = {"JUP": 7.5, "PENDLE": 5.0, "SOL": 6.0}
    market_data = {
        "JUP": {"price": 0.80, "ema_200": 1.10},       # Downtrend -> 0.0%
        "PENDLE": {"price": 2.20, "ema_200": 3.00},    # Downtrend -> 0.0%
        "SOL": {"price": 180.0, "ema_200": 140.0},     # Uptrend -> 6.0%
    }

    filtered = gate.filter_portfolio_allocations(target_weights, market_data)
    assert filtered["adjusted_weights"]["JUP"] == 0.0
    assert filtered["adjusted_weights"]["PENDLE"] == 0.0
    assert filtered["adjusted_weights"]["SOL"] == 6.0
    assert filtered["usdc_cash_buffer_pct"] == 12.5  # 7.5 + 5.0 preserved in USDC


def test_hard_inflation_gate_disqualifies_akt_and_render():
    gate = HardInflationGate()

    # AKT: emissions $33.5M vs fees $2.7M -> Disqualified
    akt_audit = gate.audit_asset_inflation(
        symbol="AKT",
        name="Akash Network",
        annual_emissions_usd=33_500_000,
        annual_fees_burned_usd=2_700_000,
        circulating_pct=77.0,
    )
    assert not akt_audit["is_qualified_for_long"]
    assert akt_audit["tier_action"] == "DISQUALIFY_TO_SHORT_RADAR"
    assert akt_audit["dilution_ratio"] > 10.0

    # RENDER: emissions $20M vs fees $4.5M -> Disqualified
    render_audit = gate.audit_asset_inflation(
        symbol="RENDER",
        name="Render Network",
        annual_emissions_usd=20_000_000,
        annual_fees_burned_usd=4_500_000,
        circulating_pct=72.0,
    )
    assert not render_audit["is_qualified_for_long"]
    assert render_audit["tier_action"] == "DISQUALIFY_TO_SHORT_RADAR"

    # JUP: emissions 0, fees $210M -> Qualified
    jup_audit = gate.audit_asset_inflation(
        symbol="JUP",
        name="Jupiter",
        annual_emissions_usd=0,
        annual_fees_burned_usd=210_000_000,
        circulating_pct=50.0,
    )
    assert jup_audit["is_qualified_for_long"]
    assert jup_audit["tier_action"] == "QUALIFIED_FOR_LONG"


def test_market_neutral_pair_trade_construction():
    engine = MarketNeutralEngine()
    pair = engine.construct_pair_trade(
        long_benchmark="BTC",
        short_basket=["AKT", "RENDER"],
        total_notional_usd=100_000,
        benchmark_weight_pct=50.0,
    )

    assert pair["strategy"] == "RELATIVE_VALUE_BETA_NEUTRAL"
    assert pair["long_leg"]["capital_usd"] == 50_000
    assert len(pair["short_leg"]) == 2
    assert pair["short_leg"][0]["capital_usd"] == 25_000
    assert pair["short_leg"][1]["capital_usd"] == 25_000


def test_market_neutral_funding_arbitrage():
    engine = MarketNeutralEngine()
    arb = engine.evaluate_funding_arbitrage(
        symbol="ETH",
        spot_price=2250.0,
        perp_price=2251.0,
        funding_rate_8h_pct=0.03,  # 0.03% every 8h = ~32.85% APR
        notional_size_usd=50_000,
    )

    assert arb["is_viable"]
    assert arb["annualized_funding_apr_pct"] > 30.0
    assert arb["recommended_trade"] == "LONG_SPOT_SHORT_PERP"


def test_market_neutral_pendle_pt_fixed_yield():
    engine = MarketNeutralEngine()
    pt = engine.evaluate_fixed_yield_stripping(
        base_asset="USDe",
        maturity_date="2027-03-25",
        pt_discount_price=0.93,  # 7% discount
        days_to_maturity=180,
    )

    assert pt["strategy"] == "PENDLE_PT_FIXED_DOLLAR_YIELD"
    assert pt["discount_captured_pct"] == 7.0
    assert pt["guaranteed_fixed_apy_pct"] > 14.0
    assert "0.0%" in pt["directional_crypto_risk"]


def test_risk_manager_flags_inflation_disqualifications():
    rm = InstitutionalRiskManager()
    audit = rm.audit_portfolio_risk()

    assert "disqualified_for_long" in audit
    disqualified_syms = [d["symbol"] for d in audit["disqualified_for_long"]]
    assert "AKT" in disqualified_syms
    assert "RENDER" in disqualified_syms
