"""
Hard Inflation & Net-Emissions Gate for CAF-Terminal.

Audits whether an asset suffers from structural orderbook bleed.
Rule: If Annual Emissions (Validator/Node/VC Dilution) > Annual Real Fees Burned/Distributed,
the asset is STRICTLY DISQUALIFIED from all LONG holding tiers (Core, High Conviction, Invest).
Such assets are reclassified into SHORT_RADAR or WATCHLIST_ONLY.
"""

from typing import Any, Dict, List, Optional


class HardInflationGate:
    """
    Enforces a strict mathematical ban on holding structurally inflationary assets.
    """

    def __init__(self, max_allowed_dilution_ratio: float = 1.0):
        # 1.0 means emissions cannot exceed 100% of fees burned (Net-Neutral or Deflationary)
        self.max_allowed_dilution_ratio = max_allowed_dilution_ratio

    def audit_asset_inflation(
        self,
        symbol: str,
        name: str,
        annual_emissions_usd: float,
        annual_fees_burned_usd: float,
        circulating_pct: float = 100.0,
    ) -> Dict[str, Any]:
        """
        Audits single asset inflation vs fee capture.

        Returns:
            - is_qualified_for_long: bool
            - dilution_ratio: float (Emissions / Fees)
            - tier_action: "MAINTAIN_LONG" | "DISQUALIFY_TO_SHORT_RADAR"
        """
        sym = symbol.upper()
        fees = max(annual_fees_burned_usd, 0.0001)
        dilution_ratio = round(annual_emissions_usd / fees, 2)

        # Disqualification conditions:
        # 1. Dilution ratio > 1.0 (Emissions outpace burns/cashflow)
        # 2. Low float with high FDV overhang (circulating < 40%)
        is_net_dilution = annual_emissions_usd > annual_fees_burned_usd
        is_low_float_trap = circulating_pct < 40.0 and annual_emissions_usd > 10_000_000

        is_disqualified = is_net_dilution or is_low_float_trap

        if is_disqualified:
            tier_action = "DISQUALIFY_TO_SHORT_RADAR"
            if is_net_dilution and dilution_ratio >= 3.0:
                severity = "CRITICAL_STRUCTURAL_BLEED"
                reason = (
                    f"Emissions (${annual_emissions_usd:,.0f}/yr) exceed real burns/fees "
                    f"(${annual_fees_burned_usd:,.0f}/yr) by {dilution_ratio}x. Guaranteed orderbook bleed."
                )
            elif is_low_float_trap:
                severity = "LOW_FLOAT_VC_OVERHANG"
                reason = f"Only {circulating_pct:.1f}% circulating supply. Massive future unlocks."
            else:
                severity = "MILD_INFLATION_DRAG"
                reason = f"Net-inflationary tokenomics (Emissions/Fees ratio: {dilution_ratio}x)."
        else:
            tier_action = "QUALIFIED_FOR_LONG"
            severity = "HEALTHY_OR_DEFLATIONARY"
            burn_coverage = round(annual_fees_burned_usd / max(annual_emissions_usd, 1.0), 2)
            reason = (
                f"Sustainable Tokenomics: Fees burned/buyback (${annual_fees_burned_usd:,.0f}/yr) "
                f"cover emissions (${annual_emissions_usd:,.0f}/yr) by {burn_coverage}x."
            )

        return {
            "symbol": sym,
            "name": name,
            "annual_emissions_usd": annual_emissions_usd,
            "annual_fees_burned_usd": annual_fees_burned_usd,
            "dilution_ratio": dilution_ratio,
            "is_qualified_for_long": not is_disqualified,
            "tier_action": tier_action,
            "severity": severity,
            "diagnostic_reason": reason,
            "recommended_strategy": "LONG_CANDIDATE" if not is_disqualified else "RELATIVE_VALUE_SHORT",
        }

    def audit_portfolio_emissions(
        self,
        assets: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Audits all assets in the registry and identifies assets that must be purged from LONG tiers.
        """
        qualified_longs = []
        disqualified_shorts = []

        for asset in assets:
            sym = asset.get("symbol", "").upper()
            name = asset.get("name", sym)
            emissions = float(asset.get("annual_emissions_usd", 0.0))
            fees_burned = float(asset.get("annual_fees_burned_usd", 0.0))
            circulating_pct = float(asset.get("circulating_pct", 100.0))

            res = self.audit_asset_inflation(
                symbol=sym,
                name=name,
                annual_emissions_usd=emissions,
                annual_fees_burned_usd=fees_burned,
                circulating_pct=circulating_pct,
            )

            if res["is_qualified_for_long"]:
                qualified_longs.append(res)
            else:
                disqualified_shorts.append(res)

        return {
            "total_assets_audited": len(assets),
            "qualified_long_count": len(qualified_longs),
            "disqualified_short_count": len(disqualified_shorts),
            "qualified_longs": qualified_longs,
            "disqualified_shorts": disqualified_shorts,
        }
