"""
Unit tests for Curator, Collateral and Oracle Risk Gate (DeFi Learn Framework).
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.risk.curator_risk import CuratorRiskGate
from src.risk.risk_manager import InstitutionalRiskManager


def test_curator_gate_rejects_concentrated_collateral():
    gate = CuratorRiskGate(max_collateral_concentration_pct=40.0)

    # 52% cbBTC concentration (Morpho trap)
    audit = gate.audit_vault_risk(
        vault_name="Morpho Steakhouse cbBTC Core",
        protocol="Morpho",
        collateral_asset="cbBTC",
        total_vault_tvl_usd=100_000_000,
        underlying_market_tvl_usd=1_330_000_000,
        top_collateral_share_pct=52.0,
        curator_name="Steakhouse",
        oracle_type="Chainlink_Dual_Feed",
        timelock_hours=24,
    )

    assert not audit["is_approved"]
    assert audit["verdict"] == "REJECTED_OR_BLOCKED"
    assert any("COLLATERAL_CONCENTRATION" in f for f in audit["critical_flags"])


def test_curator_gate_rejects_untrusted_oracle():
    gate = CuratorRiskGate()

    # Bonzo Finance style unverified oracle
    audit = gate.audit_vault_risk(
        vault_name="Bonzo Lending Pool SAUCE",
        protocol="Bonzo",
        collateral_asset="SAUCE",
        total_vault_tvl_usd=10_000_000,
        underlying_market_tvl_usd=15_000_000,
        top_collateral_share_pct=25.0,
        curator_name="Internal",
        oracle_type="SINGLE_UNVERIFIED",
        timelock_hours=24,
    )

    assert not audit["is_approved"]
    assert any("ORACLE_EXPLOIT_HAZARD" in f for f in audit["critical_flags"])


def test_curator_gate_approves_balanced_vault():
    gate = CuratorRiskGate()

    # Balanced institutional vault with dual-feed oracle and 24h timelock
    audit = gate.audit_vault_risk(
        vault_name="Aave v3 Core USDC",
        protocol="Aave v3",
        collateral_asset="ETH",
        total_vault_tvl_usd=500_000_000,
        underlying_market_tvl_usd=2_000_000_000,
        top_collateral_share_pct=30.0,
        curator_name="Aave Risk DAO",
        oracle_type="Chainlink_Dual_Feed",
        is_leveraged_loop=False,
        timelock_hours=48,
    )

    assert audit["is_approved"]
    assert audit["verdict"] == "APPROVED"
    assert audit["risk_score"] >= 80.0


def test_rwa_cash_split_low_funding_regime():
    gate = CuratorRiskGate()

    # Low funding regime (3.5% APR) -> 85% RWA / 15% Synthetic
    split = gate.audit_rwa_cash_reserve_split(
        total_reserve_usd=100_000.0,
        rwa_allocations={},
        synthetic_delta_allocations={},
        macro_funding_rate_annual_pct=3.5,
    )

    assert split["regime"] == "LOW_FUNDING_RWA_DOMINANCE"
    assert split["target_rwa_ratio_pct"] == 85.0
    assert split["rwa_allocation_usd"] == 85_000.0
    assert split["synthetic_allocation_usd"] == 15_000.0
    assert "sUSDS (Sky/Maker)" in split["recommended_rwa_instruments"]


def test_risk_manager_has_curator_gate():
    rm = InstitutionalRiskManager()
    assert hasattr(rm, "curator_risk")
    assert isinstance(rm.curator_risk, CuratorRiskGate)
