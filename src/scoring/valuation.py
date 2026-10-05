"""
CAF / CVE Valuation & Tactical Entry Engine (5-Layer Architecture)

Implements:
Layer 1: Fundamental CVE Score (What to own)
Layer 2: Valuation Multiples & Distance from ATH
Layer 3: Risk/Reward Scenarios & Expected Value (Bear / Base / Bull Payoff)
Layer 4: CAF Entry Rating & Action Signals (AGGRESSIVE_BUY, BUY, ACCUMULATE, WAIT_PULLBACK, WAIT)
Layer 5: Position Sizing & Dry Powder Management (Target Allocation vs Deployed Weight vs Buy Zones)
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple


@dataclass
class ScenarioPayoff:
    bear_price: float
    base_price: float
    bull_price: float
    bear_prob: float = 0.35
    base_prob: float = 0.45
    bull_prob: float = 0.20


@dataclass
class ValuationRating:
    symbol: str
    name: str
    tier: str
    cluster: str
    fundamental_score: float
    current_price: float
    ath_price: float
    ath_drawdown_pct: float
    expected_value: float
    ev_return_pct: float
    downside_pct: float
    asymmetry_ratio: float
    entry_score: float
    entry_signal: str  # AGGRESSIVE_BUY, BUY, ACCUMULATE, WAIT_PULLBACK, WAIT
    target_weight: float
    deployment_ratio: float  # Fraction of target weight deployed today (0.0 to 1.0)
    deployed_weight: float   # Actual capital deployed at current price
    dry_powder_weight: float # Remaining capital held in USDC reserve for buy zones
    buy_zones: List[str]


class ValuationEngine:
    """Engine for pricing and risk-adjusted tactical execution in CAF-Terminal."""

    # Benchmark scenario library for October 2026 pricing environment
    ASSET_PRICE_SCENARIOS: Dict[str, Dict[str, Any]] = {
        "BTC": {
            "current": 86600.0,
            "ath": 126198.0,
            "bear": 55000.0,
            "base": 115000.0,
            "bull": 160000.0,
            "zones": ["$75k–$85k (DCA Starter)", "$65k–$75k (Core Accumulation)", "$55k–$65k (Aggressive Value)"],
        },
        "ETH": {
            "current": 2950.0,
            "ath": 4878.0,
            "bear": 1850.0,
            "base": 4200.0,
            "bull": 6000.0,
            "zones": ["$2.6k–$2.9k (Starter)", "$2.2k–$2.6k (Accumulate)", "$1.8k–$2.2k (Deep Value)"],
        },
        "HYPE": {
            "current": 90.70,
            "ath": 97.98,
            "bear": 45.0,
            "base": 120.0,
            "bull": 180.0,
            "zones": ["$75–$85 (Starter DCA)", "$60–$75 (Core Value)", "$45–$60 (Aggressive Buy)"],
        },
        "AAVE": {
            "current": 188.0,
            "ath": 666.0,
            "bear": 110.0,
            "base": 320.0,
            "bull": 550.0,
            "zones": ["$170–$195 (Current Buy)", "$130–$160 (Value Accumulation)", "$100–$130 (Deep Value)"],
        },
        "TAO": {
            "current": 505.0,
            "ath": 758.0,
            "bear": 280.0,
            "base": 750.0,
            "bull": 1250.0,
            "zones": ["$450–$510 (Starter DCA)", "$350–$450 (Value Accumulation)", "$250–$350 (Aggressive)"],
        },
        "AKT": {
            "current": 3.35,
            "ath": 8.07,
            "bear": 1.80,
            "base": 6.00,
            "bull": 11.00,
            "zones": ["$3.0–$3.4 (Current Buy)", "$2.3–$3.0 (Value Accumulate)", "$1.6–$2.3 (Deep Value)"],
        },
        "RAY": {
            "current": 2.95,
            "ath": 16.90,
            "bear": 1.30,
            "base": 4.50,
            "bull": 8.50,
            "zones": ["$2.4–$3.0 (Starter)", "$1.8–$2.4 (Accumulate)", "$1.2–$1.8 (Deep Value)"],
        },
        "JUP": {
            "current": 1.02,
            "ath": 2.04,
            "bear": 0.55,
            "base": 1.65,
            "bull": 2.80,
            "zones": ["$0.90–$1.05 (Starter)", "$0.70–$0.90 (Accumulate)", "$0.50–$0.70 (Deep Value)"],
        },
        "SUI": {
            "current": 2.18,
            "ath": 3.93,
            "bear": 1.15,
            "base": 3.60,
            "bull": 6.50,
            "zones": ["$1.90–$2.25 (Starter DCA)", "$1.45–$1.90 (Accumulate)", "$1.05–$1.45 (Deep Value)"],
        },
        "TRAC": {
            "current": 0.40,
            "ath": 3.86,
            "bear": 0.22,
            "base": 1.10,
            "bull": 2.50,
            "zones": ["$0.36–$0.42 (Aggressive Buy)", "$0.26–$0.36 (Deep Accumulate)"],
        },
        "PENDLE": {
            "current": 4.35,
            "ath": 7.52,
            "bear": 2.40,
            "base": 7.00,
            "bull": 12.00,
            "zones": ["$3.8–$4.4 (Starter Accumulate)", "$2.8–$3.8 (Value Buy)", "$2.0–$2.8 (Deep Value)"],
        },
        "GEOD": {
            "current": 0.22,
            "ath": 0.35,
            "bear": 0.12,
            "base": 0.42,
            "bull": 0.85,
            "zones": ["$0.19–$0.23 (Accumulate)", "$0.14–$0.19 (Aggressive Buy)"],
        },
        "ONDO": {
            "current": 0.78,
            "ath": 1.48,
            "bear": 0.42,
            "base": 1.35,
            "bull": 2.40,
            "zones": ["$0.70–$0.80 (Starter DCA)", "$0.50–$0.70 (Value Accumulate)"],
        },
        "FLUID": {
            "current": 4.10,
            "ath": 6.50,
            "bear": 2.20,
            "base": 7.50,
            "bull": 14.00,
            "zones": ["$3.7–$4.2 (Starter Accumulate)", "$2.8–$3.7 (Value Buy)"],
        },
        "ENA": {
            "current": 0.45,
            "ath": 1.52,
            "bear": 0.22,
            "base": 0.85,
            "bull": 1.60,
            "zones": ["$0.38–$0.46 (Starter)", "$0.26–$0.38 (Accumulate)", "$0.18–$0.26 (Deep Value)"],
        },
        "RENDER": {
            "current": 5.40,
            "ath": 13.53,
            "bear": 2.80,
            "base": 9.50,
            "bull": 18.00,
            "zones": ["$4.8–$5.5 (Starter Accumulate)", "$3.5–$4.8 (Value Buy)"],
        },
        "GRASS": {
            "current": 1.85,
            "ath": 3.89,
            "bear": 0.75,
            "base": 2.80,
            "bull": 5.20,
            "zones": ["$1.4–$1.8 (Starter DCA only)", "$0.9–$1.4 (Wait for unlock absorption)"],
        },
        "INJ": {
            "current": 19.20,
            "ath": 52.75,
            "bear": 9.50,
            "base": 36.00,
            "bull": 65.00,
            "zones": ["$17.0–$20.0 (Current Buy)", "$12.0–$17.0 (Value Buy)"],
        },
        "DEEP": {
            "current": 0.082,
            "ath": 0.125,
            "bear": 0.038,
            "base": 0.145,
            "bull": 0.260,
            "zones": ["$0.065–$0.085 (Starter)", "$0.045–$0.065 (Accumulate)"],
        },
        "DRIFT": {
            "current": 0.72,
            "ath": 1.45,
            "bear": 0.35,
            "base": 1.30,
            "bull": 2.40,
            "zones": ["$0.60–$0.75 (Starter)", "$0.42–$0.60 (Value Accumulate)"],
        },
        "ATH": {
            "current": 0.062,
            "ath": 0.118,
            "bear": 0.026,
            "base": 0.095,
            "bull": 0.170,
            "zones": ["$0.045–$0.060 (Small starter only)"],
        },
        "KMNO": {
            "current": 0.095,
            "ath": 0.185,
            "bear": 0.045,
            "base": 0.160,
            "bull": 0.290,
            "zones": ["$0.075–$0.095 (Starter DCA)", "$0.050–$0.075 (Accumulate)"],
        },
    }

    @classmethod
    def evaluate_entry(
        cls,
        symbol: str,
        name: str,
        tier: str,
        cluster: str,
        fundamental_score: float,
        target_weight: float,
        override_scenario: Optional[Dict[str, Any]] = None,
    ) -> ValuationRating:
        """
        Computes Layer 2-5 Valuation, Expected Return, Entry Rating and Tactical Deployment.
        """
        symbol_u = symbol.upper()
        data = override_scenario or cls.ASSET_PRICE_SCENARIOS.get(symbol_u)

        if not data:
            # Fallback for unbenchmarked asset: default conservative assumptions
            curr = 1.0
            ath = 2.0
            bear = 0.5
            base = 1.5
            bull = 2.5
            zones = ["Wait for confirmed valuation metrics"]
        else:
            curr = float(data["current"])
            ath = float(data["ath"])
            bear = float(data["bear"])
            base = float(data["base"])
            bull = float(data["bull"])
            zones = data.get("zones", ["Accumulate on dips"])

        # Layer 2: Distance from ATH
        ath_dd_pct = round(((curr - ath) / ath) * 100.0, 1)

        # Layer 3: Probability-weighted scenario payoffs
        p_bear = 0.35
        p_base = 0.45
        p_bull = 0.20

        # Adjust probabilities if asset is extremely near ATH (> -10%)
        if ath_dd_pct > -10.0:
            p_bear = 0.40
            p_base = 0.45
            p_bull = 0.15

        ev_price = (bear * p_bear) + (base * p_base) + (bull * p_bull)
        ev_return_pct = round(((ev_price - curr) / curr) * 100.0, 1)
        downside_pct = round(((bear - curr) / curr) * 100.0, 1)
        upside_base_pct = round(((base - curr) / curr) * 100.0, 1)

        # Asymmetry Ratio: Base Upside / Downside Risk (higher = better asymmetry)
        abs_downside = abs(downside_pct) if abs(downside_pct) > 0 else 1.0
        asymmetry_ratio = round(upside_base_pct / abs_downside, 2)

        # Layer 4: Composite Entry Score (0 - 100)
        # 1. Fundamental Quality Anchor: 50%
        # 2. Risk/Reward & Expected Value: 30%
        # 3. Margin of Safety & ATH Discount: 20%
        fund_component = fundamental_score * 0.50

        # EV and Asymmetry combined into Payoff Quality (0 - 100)
        # Asymmetry 0.6 -> 40 pts, 1.0 -> 60 pts, 2.0 -> 85 pts, 3.0+ -> 100 pts
        asym_pts = min(100.0, max(15.0, asymmetry_ratio * 35.0 + 25.0))
        ev_pts = min(100.0, max(15.0, 50.0 + (ev_return_pct * 0.5)))
        payoff_component = ((asym_pts * 0.6) + (ev_pts * 0.4)) * 0.30

        # Margin of safety: Discount from ATH
        # 0-10% -> 20 pts, 30% -> 55 pts, 70%+ -> 95 pts
        abs_discount = abs(ath_dd_pct)
        discount_pts = min(100.0, max(15.0, abs_discount * 1.1 + 18.0))
        safety_component = discount_pts * 0.20

        # Proximity penalty if trading within 10% of ATH in price discovery
        proximity_penalty = 5.0 if ath_dd_pct > -10.0 else (2.0 if ath_dd_pct > -20.0 else 0.0)

        raw_entry_score = fund_component + payoff_component + safety_component - proximity_penalty
        entry_score = round(min(98.0, max(45.0, raw_entry_score)), 1)

        # Action Signals & Deployment Ratio (% of Target Weight deployed today)
        if entry_score >= 84.0:
            entry_signal = "AGGRESSIVE_BUY"
            deployment_ratio = 1.00  # 100% of target deployed
        elif entry_score >= 78.0:
            entry_signal = "BUY"
            deployment_ratio = 0.75  # 75% deployed, 25% DCA reserve
        elif entry_score >= 70.0:
            entry_signal = "ACCUMULATE"
            deployment_ratio = 0.50  # 50% deployed, 50% DCA reserve
        elif entry_score >= 60.0:
            entry_signal = "WAIT_PULLBACK"
            deployment_ratio = 0.25  # 25% starter tranche, 75% in dry powder
        else:
            entry_signal = "WAIT"
            deployment_ratio = 0.00  # 0% deployed, 100% dry powder

        deployed_weight = round(target_weight * deployment_ratio, 2)
        dry_powder_weight = round(target_weight - deployed_weight, 2)

        return ValuationRating(
            symbol=symbol_u,
            name=name,
            tier=tier,
            cluster=cluster,
            fundamental_score=fundamental_score,
            current_price=curr,
            ath_price=ath,
            ath_drawdown_pct=ath_dd_pct,
            expected_value=round(ev_price, 2),
            ev_return_pct=ev_return_pct,
            downside_pct=downside_pct,
            asymmetry_ratio=asymmetry_ratio,
            entry_score=entry_score,
            entry_signal=entry_signal,
            target_weight=target_weight,
            deployment_ratio=deployment_ratio,
            deployed_weight=deployed_weight,
            dry_powder_weight=dry_powder_weight,
            buy_zones=zones,
        )
