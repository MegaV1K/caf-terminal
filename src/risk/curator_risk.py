"""
Curator, Collateral & Oracle Risk Gate for CAF-Terminal.

Derived from institutional empirical findings in 'DeFi [L]Earn. Strategies.':
1. False Diversification Trap: Top 5 curators control >69% of vault TVL,
   and distinct vaults frequently concentrate in the exact same underlying loan market (e.g. cbBTC/USDC).
2. Leverage Loop Contagion: Looped debt mechanisms (e.g. sUSDe loops on Aave/Morpho)
   unwind violently when yields compress.
3. Single Oracle Failure: Catastrophic bad-debt risks from unverified or single-oracle pricing.
"""

from typing import Any, Dict, List, Optional


class CuratorRiskGate:
    """
    Evaluates institutional risk in DeFi lending pools, vaults, and yield positions.
    """

    def __init__(
        self,
        max_collateral_concentration_pct: float = 40.0,
        max_single_curator_share_pct: float = 35.0,
    ):
        self.max_collateral_concentration_pct = max_collateral_concentration_pct
        self.max_single_curator_share_pct = max_single_curator_share_pct

    def audit_vault_risk(
        self,
        vault_name: str,
        protocol: str,
        collateral_asset: str,
        total_vault_tvl_usd: float,
        underlying_market_tvl_usd: float,
        top_collateral_share_pct: float,
        curator_name: str,
        oracle_type: str = "Chainlink_Dual_Feed",
        is_leveraged_loop: bool = False,
        timelock_hours: int = 24,
    ) -> Dict[str, Any]:
        """
        Audits a curated vault or lending market against systemic failure modes.
        """
        critical_flags = []
        risk_score = 100.0  # Starts at 100 (Safe), decreases with risks

        # 1. Collateral Concentration Check
        if top_collateral_share_pct > self.max_collateral_concentration_pct:
            critical_flags.append(
                f"COLLATERAL_CONCENTRATION: Single collateral ({collateral_asset}) represents "
                f"{top_collateral_share_pct:.1f}% of market (limit: {self.max_collateral_concentration_pct}%)."
            )
            risk_score -= 30.0

        # 2. Leverage Loop / Unwind Risk
        if is_leveraged_loop:
            critical_flags.append(
                "LEVERAGE_LOOP_RISK: Position utilizes recursive looping (e.g. sUSDe/Morpho loop). "
                "High liquidation cascade hazard upon yield compression."
            )
            risk_score -= 25.0

        # 3. Oracle Hygiene Check (Lessons from Bonzo Finance $9M exploit via unverified oracle)
        untrusted_oracles = ["SINGLE_UNVERIFIED", "CUSTOM_SPOT_DEX", "ORACLE_LESS"]
        if oracle_type.upper() in untrusted_oracles:
            critical_flags.append(
                f"ORACLE_EXPLOIT_HAZARD: Oracle type '{oracle_type}' lacks dual-feed verification. "
                "Vulnerable to flash loan or signing manipulation."
            )
            risk_score -= 40.0

        # 4. Manager Discretion vs Timelock (Lessons from Xerberus 104-vault audit)
        if timelock_hours < 12:
            critical_flags.append(
                f"GOVERNANCE_DISCRETION_RISK: Vault timelock is only {timelock_hours}h (< 12h). "
                "Manager can shift strategy or restrict withdrawals without notice."
            )
            risk_score -= 15.0

        has_critical_block = (
            top_collateral_share_pct > self.max_collateral_concentration_pct
            or oracle_type.upper() in untrusted_oracles
        )
        is_approved = (risk_score >= 65.0) and (not has_critical_block)

        verdict = "APPROVED" if is_approved else "REJECTED_OR_BLOCKED"
        action = "ALLOCATE_CAPITAL" if is_approved else "AVOID_FALSE_DIVERSIFICATION_TRAP"

        return {
            "vault_name": vault_name,
            "protocol": protocol,
            "curator": curator_name,
            "risk_score": round(max(risk_score, 0.0), 1),
            "verdict": verdict,
            "action": action,
            "is_approved": is_approved,
            "critical_flags": critical_flags,
            "collateral_asset": collateral_asset,
            "top_collateral_share_pct": top_collateral_share_pct,
            "oracle_type": oracle_type,
            "timelock_hours": timelock_hours,
        }

    def audit_rwa_cash_reserve_split(
        self,
        total_reserve_usd: float,
        rwa_allocations: Dict[str, float],
        synthetic_delta_allocations: Dict[str, float],
        macro_funding_rate_annual_pct: float,
    ) -> Dict[str, Any]:
        """
        Determines the optimal institutional distribution of USDC_YIELD_RESERVE.
        Enforces shift from synthetic delta-neutral (sUSDe) to RWA (sUSDS, USDY, BUIDL)
        when funding rates drop below 8% (Lesson from DeFi Learn Q2 2026 rotation).
        """
        # When funding rate is low (< 8%), cap synthetic delta-neutral yield to max 20%
        if macro_funding_rate_annual_pct < 8.0:
            target_rwa_ratio = 0.85  # 85% RWA / 15% Synthetic
            regime = "LOW_FUNDING_RWA_DOMINANCE"
            rationale = (
                f"Perp funding is only {macro_funding_rate_annual_pct:.1f}% APR. "
                "Delta-neutral yields compressed to Treasury levels. "
                "85% allocated to RWA (sUSDS/USDY) to eliminate leverage unwind risk."
            )
        else:
            target_rwa_ratio = 0.50
            regime = "HIGH_FUNDING_BALANCED"
            rationale = (
                f"Perp funding is buoyant ({macro_funding_rate_annual_pct:.1f}% APR). "
                "Balanced 50/50 RWA and delta-neutral yield capture."
            )

        rwa_target_usd = round(total_reserve_usd * target_rwa_ratio, 2)
        synthetic_target_usd = round(total_reserve_usd * (1.0 - target_rwa_ratio), 2)

        return {
            "total_reserve_usd": total_reserve_usd,
            "macro_funding_annual_pct": macro_funding_rate_annual_pct,
            "regime": regime,
            "target_rwa_ratio_pct": target_rwa_ratio * 100.0,
            "target_synthetic_ratio_pct": (1.0 - target_rwa_ratio) * 100.0,
            "rwa_allocation_usd": rwa_target_usd,
            "synthetic_allocation_usd": synthetic_target_usd,
            "recommended_rwa_instruments": ["sUSDS (Sky/Maker)", "USDY (Ondo RWA)", "BUIDL (BlackRock/Securitize)"],
            "rationale": rationale,
        }
