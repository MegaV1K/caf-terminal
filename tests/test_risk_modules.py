"""
Unit tests for Institutional Risk & Derivatives Modules (DerivativesRiskEngine, TiltGuard, RiskManager).
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.risk.derivatives_risk import DerivativesRiskEngine
from src.risk.tilt_guard import TiltGuard
from src.risk.risk_manager import InstitutionalRiskManager
from src.ai.committee import CFOAgent, Signal, Verdict


def test_expiration_margin_cliff_detection():
    """Identifies liquidation hazard when options collateral disappears upon expiry."""
    # Account has $10k equity, but $7k of it is in options expiring in 12 hours.
    # Maintenance margin on open futures is $5k.
    res = DerivativesRiskEngine.evaluate_expiration_margin_cliff(
        account_equity=10_000,
        maintenance_margin=5_000,
        options_collateral_value=7_000,
        hours_to_expiry=12.0,
    )

    assert res["hours_to_expiry"] == 12.0
    assert res["is_liquidation_hazard"] is True
    assert "EMERGENCY" in res["recommended_action"]


def test_notional_fee_drag_calculation():
    """Computes fee against underlying notional and flags fee trap when > 15% of profit."""
    # 1 BTC option at $67,000 spot with $300 expected profit.
    # Round-trip fee on 1 BTC notional: ~0.048% of $67,000 = ~$32.
    res_normal = DerivativesRiskEngine.calculate_notional_fee_drag(
        symbol="BTC",
        contracts=1.0,
        underlying_price=67_000,
        option_premium_usd=500,
        expected_profit_usd=1_000,
    )
    assert res_normal["is_fee_trap"] is False

    # Tiny expected profit ($100), fee eats > 30% of profit -> FEE_TRAP
    res_trap = DerivativesRiskEngine.calculate_notional_fee_drag(
        symbol="BTC",
        contracts=1.0,
        underlying_price=67_000,
        option_premium_usd=500,
        expected_profit_usd=80,
    )
    assert res_trap["is_fee_trap"] is True
    assert "FEE_TRAP" in res_trap["verdict"]


def test_liquidity_and_spread_guard():
    """Blocks market sell and recommends synthetic delta lock when spread is excessive."""
    # Deep ITM ETH option: Bid $280, Ask $320 (Spread $40). Expected profit $100.
    # Slippage cost = $20, which is 20% of profit.
    res = DerivativesRiskEngine.validate_liquidity_and_spread(
        symbol="ETH",
        bid_price=280.0,
        ask_price=330.0,
        projected_profit_usd=100.0,
        contracts=1.0,
    )
    assert res["is_liquidity_trap"] is True
    assert res["execution_mode"] == "SYNTHETIC_FUTURES_DELTA_HEDGE"


def test_oi_pinning_zones_calculation():
    """Calculates institutional delta-hedging break-even levels for ETH & BTC."""
    clusters = [
        {"asset": "ETH", "strike": 2600, "premium": 10, "open_interest": 15000, "type": "CALL"},
        {"asset": "ETH", "strike": 2500, "premium": 15, "open_interest": 8000, "type": "PUT"},
    ]
    zones = DerivativesRiskEngine.calculate_oi_pinning_zones(clusters)
    assert len(zones) == 2

    call_zone = zones[0]
    assert call_zone["break_even_pinning_level"] == 2610.0
    assert call_zone["forced_market_maker_flow"] == "SHORT_FUTURES_DELTA_HEDGE"
    assert call_zone["is_institutional_wall"] is True

    put_zone = zones[1]
    assert put_zone["break_even_pinning_level"] == 2485.0
    assert put_zone["forced_market_maker_flow"] == "LONG_FUTURES_DELTA_HEDGE"


def test_tilt_guard_limits():
    """Enforces position sizing, cluster limits, and anti-revenge tilt locks."""
    # 1. Single asset breach
    res_size = TiltGuard.audit_trade_risk(
        symbol="ABC",
        requested_weight_pct=3.5,
        cluster_name="DeFi",
        current_cluster_weight_pct=2.0,
    )
    assert res_size["is_approved"] is False
    assert any("POSITION_SIZE_BREACH" in v for v in res_size["violations"])

    # 2. Cluster breach (> 10%)
    res_cluster = TiltGuard.audit_trade_risk(
        symbol="DEF",
        requested_weight_pct=2.0,
        cluster_name="Perps DEX",
        current_cluster_weight_pct=9.0,
    )
    assert res_cluster["is_approved"] is False
    assert any("CLUSTER_LIMIT_BREACH" in v for v in res_cluster["violations"])

    # 3. Anti-Gemini Revenge Tilt Guard (drawdown > 15% and doubling down)
    res_tilt = TiltGuard.audit_trade_risk(
        symbol="SOL_BULL",
        requested_weight_pct=2.0,
        cluster_name="Solana",
        current_cluster_weight_pct=3.0,
        asset_drawdown_pct=20.0,
        is_averaging_down=True,
    )
    assert res_tilt["is_approved"] is False
    assert any("TILT_LOCK_ACTIVATED" in v for v in res_tilt["violations"])

    # 4. Anti-Herding Filter
    res_herd = TiltGuard.audit_trade_risk(
        symbol="HYPE_COIN",
        requested_weight_pct=1.5,
        cluster_name="Meme",
        current_cluster_weight_pct=1.0,
        thesis_source="COPYCAT",
    )
    assert res_herd["is_approved"] is False
    assert any("HERD_BEHAVIOR_BLOCKED" in v for v in res_herd["violations"])


def test_cfo_cluster_risk_veto():
    """Verifies that CFOAgent downgrades FULL_CAF to INCUBATOR if cluster limit is breached."""
    cfo = CFOAgent()
    signal = Signal(
        name="HyperPerp",
        symbol="HPERP",
        category="Perps DEX",
        signal_type="REVENUE_SURGE",
        signal_strength=92.0,
    )

    mock_cfo_json = {
        "verdict": "FULL_CAF",
        "conviction": 90.0,
        "reasoning": "Outstanding economics, must analyze now.",
        "next_steps": ["Deep dive"],
    }

    # Perps DEX is already at 9.5% (allocating 2.0% pushes it to 11.5% > 10% limit)
    cluster_exposure = {"Perps DEX": 9.5}

    with patch("src.ai.committee.generate_json", return_value=mock_cfo_json):
        report = cfo.decide(
            signal=signal,
            analyst_thesis="Bullish thesis",
            skeptic_critique="Some risks",
            cluster_exposure=cluster_exposure,
        )

        assert report.verdict == Verdict.INCUBATOR
        assert "[TILT_GUARD_VETO" in report.cfo_reasoning
        assert "Лимит кластера 'Perps DEX' исчерпан" in report.follow_up_actions[0]
