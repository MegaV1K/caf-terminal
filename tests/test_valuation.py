import pytest
from src.scoring.valuation import ValuationEngine, ValuationRating
from src.database.registry import CAFRegistry


def test_hype_valuation_pullback_signal():
    """HYPE at $90.7 (7.4% from ATH) has high quality but low entry score -> WAIT_PULLBACK."""
    vr = ValuationEngine.evaluate_entry(
        symbol="HYPE",
        name="Hyperliquid",
        tier="Core",
        cluster="Sovereign L1 / CLOB",
        fundamental_score=89.5,
        target_weight=10.5,
    )
    assert vr.entry_signal == "WAIT_PULLBACK"
    assert vr.deployment_ratio == 0.25
    assert vr.deployed_weight == 2.62
    assert vr.dry_powder_weight == 7.88
    assert vr.asymmetry_ratio < 1.0  # Asymmetry is low near ATH


def test_deep_value_aggressive_buy_signals():
    """AAVE and TRAC at deep discounts from ATH have high asymmetry -> AGGRESSIVE_BUY."""
    aave_vr = ValuationEngine.evaluate_entry(
        symbol="AAVE",
        name="Aave",
        tier="Core",
        cluster="Ethereum DeFi / Lending",
        fundamental_score=88.5,
        target_weight=10.0,
    )
    assert aave_vr.entry_signal == "AGGRESSIVE_BUY"
    assert aave_vr.deployment_ratio == 1.00
    assert aave_vr.deployed_weight == 10.0

    trac_vr = ValuationEngine.evaluate_entry(
        symbol="TRAC",
        name="OriginTrail",
        tier="High Conviction",
        cluster="Knowledge / AI Data",
        fundamental_score=84.0,
        target_weight=4.5,
    )
    assert trac_vr.entry_signal == "AGGRESSIVE_BUY"
    assert trac_vr.deployment_ratio == 1.00
    assert trac_vr.asymmetry_ratio > 3.0  # Extraordinary asymmetry


def test_macro_btc_valuation():
    """BTC at $86.6k (-31% from ATH) receives ACCUMULATE signal."""
    btc_vr = ValuationEngine.evaluate_entry(
        symbol="BTC",
        name="Bitcoin",
        tier="Macro Core",
        cluster="Monetary Anchor",
        fundamental_score=98.0,
        target_weight=35.0,
    )
    assert btc_vr.entry_signal == "ACCUMULATE"
    assert btc_vr.deployment_ratio == 0.50
    assert btc_vr.deployed_weight == 17.5
    assert btc_vr.dry_powder_weight == 17.5


def test_registry_markdown_contains_valuation_matrix():
    """Verifies that generated registry markdown contains the 5-layer valuation section."""
    reg = CAFRegistry()
    md_path = reg.generate_registry_markdown()
    assert md_path.exists()
    content = md_path.read_text(encoding="utf-8")
    assert "Матрица Оценки и Сценарного Анализа (5-Layer Valuation Engine)" in content
    assert "WAIT PULLBACK" in content
    assert "AGGRESSIVE BUY" in content
    assert "USDC_DCA" in content
