"""
TiltGuard: Anti-Tilt, Anti-Revenge Trading & Anti-Herding Engine.

Derived from forensic analysis of LLM trading behavior (e.g., Gemini -55% tilt,
ChatGPT/Perplexity blind copycat behavior on 3x leveraged SOXL):
1. Hard Position & Cluster Sizing Limits (Max 2.5% per asset, Max 10% per cluster).
2. Revenge Trading / Sunk Cost Blocker (Anti-Gemini Tilt Guard).
3. Max Leverage Ceiling & Volatility Decay Filter.
4. Independent Thesis Verification (Anti-Herding Filter).
"""

from typing import Any, Dict, List, Optional


class TiltGuard:
    """Institutional gatekeeper preventing psychological/algorithmic tilt and herd trades."""

    MAX_SINGLE_ASSET_WEIGHT_PCT = 2.5   # Max 2.5% of total portfolio in one position
    MAX_CLUSTER_WEIGHT_PCT      = 10.0  # Max 10.0% in one correlated risk cluster
    MAX_UNHEDGED_LEVERAGE       = 1.5   # Maximum allowed unhedged leverage
    MAX_CONSECUTIVE_DRAWDOWN    = 15.0  # % drawdown threshold triggering tilt lock

    @classmethod
    def audit_trade_risk(
        cls,
        symbol: str,
        requested_weight_pct: float,
        cluster_name: str,
        current_cluster_weight_pct: float,
        leverage: float = 1.0,
        asset_drawdown_pct: float = 0.0,
        is_averaging_down: bool = False,
        thesis_source: str = "INDEPENDENT_CVE",
    ) -> Dict[str, Any]:
        """
        Performs a pre-execution safety check to block tilt, excessive leverage,
        and unverified copycat positions.
        """
        symbol_upper = symbol.upper()
        violations = []
        warnings = []

        # 1. Single Asset Allocation Ceiling
        if requested_weight_pct > cls.MAX_SINGLE_ASSET_WEIGHT_PCT:
            violations.append(
                f"POSITION_SIZE_BREACH: Requested {requested_weight_pct:.1f}% exceeds max {cls.MAX_SINGLE_ASSET_WEIGHT_PCT:.1f}% limit."
            )

        # 2. Risk Cluster Ceiling
        new_cluster_total = current_cluster_weight_pct + requested_weight_pct
        if new_cluster_total > cls.MAX_CLUSTER_WEIGHT_PCT:
            violations.append(
                f"CLUSTER_LIMIT_BREACH: Cluster '{cluster_name}' would reach {new_cluster_total:.1f}% (cap: {cls.MAX_CLUSTER_WEIGHT_PCT:.1f}%)."
            )

        # 3. Leverage and Beta Cap (Anti-SOXL/TQQQ Trap)
        if leverage > cls.MAX_UNHEDGED_LEVERAGE:
            violations.append(
                f"EXCESSIVE_LEVERAGE: Leverage {leverage:.1f}x exceeds hard ceiling {cls.MAX_UNHEDGED_LEVERAGE:.1f}x without structural hedge."
            )

        # 4. Anti-Gemini Revenge Trading / Sunk Cost Blocker
        if is_averaging_down or asset_drawdown_pct > cls.MAX_CONSECUTIVE_DRAWDOWN:
            if requested_weight_pct > 1.0 or leverage > 1.0:
                violations.append(
                    f"TILT_LOCK_ACTIVATED: Asset {symbol_upper} is down -{asset_drawdown_pct:.1f}%. "
                    "Doubling down or adding leverage after steep drawdown is forbidden. Execute thesis invalidation review instead."
                )
            else:
                warnings.append(
                    f"CAUTION: Asset {symbol_upper} has drawdown -{asset_drawdown_pct:.1f}%. Keep sizing minimal."
                )

        # 5. Anti-Herding Filter (Blind Copycat Blocker)
        if thesis_source.upper() in {"COPYCAT", "LEADER_FOLLOW", "HERD"}:
            violations.append(
                f"HERD_BEHAVIOR_BLOCKED: Trade based on copying another agent/leader without independent CVE valuation."
            )

        is_approved = len(violations) == 0

        return {
            "symbol": symbol_upper,
            "is_approved": is_approved,
            "status": "APPROVED" if is_approved else "VETOED",
            "violations": violations,
            "warnings": warnings,
            "recommended_weight_pct": min(requested_weight_pct, cls.MAX_SINGLE_ASSET_WEIGHT_PCT) if not is_approved else requested_weight_pct,
            "action_required": (
                "PASS_TO_EXECUTION"
                if is_approved
                else "MANDATORY_REVISE_OR_ABORT"
            ),
        }
