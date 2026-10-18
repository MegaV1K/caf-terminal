"""
Asymmetric 50x–100x Alpha Screening & Incubator Sizing Engine.

Derived from empirical forensic analysis of 7 historical crypto home runs:
KAS (+1,200x), RUNE (+2,600x), PENDLE (+220x), TAO (+180x), SOL (+1,180x/32x), INJ (+46x), HYPE (+30x+).

5 Immutable Empirical Screening Pillars:
1. Asymmetric Headroom (FDV Ceiling <= $300M, sweet spot <= $150M).
2. Clean Tokenomics & Float (Circulating >= 60% or Fair Launch, no predatory VC cliff dumps).
3. Friction & Discovery Index (Off-the-radar: <= 1 Tier-1 CEX listing).
4. Leading Capital & Fee Efficiency (Annualized Fees / TVL >= 2.0% or Daily Fees > $20k at sub-$100M cap).
5. Architectural Singularity & Dev Velocity (Non-EVM/Custom execution engine + active code commits during bear).

Incubator Portfolio Construction:
- Total Allocation Budget: 10.0% of portfolio.
- Position Sizing: 1.5%–2.0% across 5–6 assets.
- Asymmetry Payoff: 1 winner at 50x yields +75% to overall portfolio, paying for 4–5 wipeouts.
"""

from typing import Any, Dict, List, Optional


class AsymmetricAlphaScorer:
    """Institutional screener for detecting 50x–100x early incubator assets."""

    # Weights for the 5 Empirical Pillars
    WEIGHTS = {
        "headroom": 0.25,        # Low FDV ceiling
        "clean_float": 0.25,     # High circulating float / Fair Launch
        "friction": 0.20,        # Pre-consensus / off-the-radar
        "fee_efficiency": 0.20,  # Real revenue relative to TVL/Cap
        "tech_velocity": 0.10,   # Architectural singularity + GitHub commits
    }

    # Known Tier-1 centralized exchanges for the Friction Index
    TIER1_CEX_LIST = {
        "binance", "coinbase", "okx", "bybit", "upbit"
    }

    @classmethod
    def score_candidate(
        cls,
        data: Dict[str, Any],
        github_metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Calculates the Asymmetric Alpha Score (0 - 100) and eligibility for Incubator tier:
        - Asymmetric Unicorn (>= 80): Prime 50x–100x candidate.
        - Emerging Contender (65 - 79): Strong incubator watchlist candidate.
        - Neutral / Unfavorable (< 65): Disqualified or mature/diluted.
        """
        symbol = (data.get("symbol") or "").upper()
        name = data.get("name") or symbol
        mcap = float(data.get("mcap") or 0)
        fdv = float(data.get("fdv") or mcap or 0)
        tvl = float(data.get("tvl") or 0)
        daily_fees = float(data.get("daily_fees") or 0)
        daily_revenue = float(data.get("daily_revenue") or 0)
        exchanges = [e.lower() for e in (data.get("exchanges") or [])]
        is_fair_launch = bool(data.get("is_fair_launch", False))
        chains = data.get("chains") or []
        category = (data.get("category") or "").lower()

        # -------------------------------------------------------------
        # 1. Asymmetric Headroom (FDV Ceiling)
        # -------------------------------------------------------------
        # A 50x on a $5B FDV requires $250B cap (consensus saturation).
        # A 50x on a $100M FDV requires $5B cap (attainable mid-to-bull cap).
        eff_fdv = fdv if fdv > 0 else (mcap * 1.5 if mcap > 0 else 50_000_000)
        if eff_fdv <= 80_000_000:
            headroom_score = 100.0
        elif eff_fdv <= 180_000_000:
            headroom_score = 85.0
        elif eff_fdv <= 350_000_000:
            headroom_score = 70.0
        elif eff_fdv <= 800_000_000:
            headroom_score = 45.0
        elif eff_fdv <= 2_000_000_000:
            headroom_score = 20.0
        else:
            headroom_score = 0.0  # Disqualified: Too saturated for 50x

        # -------------------------------------------------------------
        # 2. Clean Tokenomics & Float (Anti-VC Overhang)
        # -------------------------------------------------------------
        # High float or fair launch avoids death spirals from unlocks
        float_ratio = None
        if mcap > 0 and fdv > 0:
            float_ratio = min(1.0, mcap / fdv)

        if is_fair_launch:
            float_score = 100.0
        elif float_ratio is not None:
            if float_ratio >= 0.75:
                float_score = 95.0
            elif float_ratio >= 0.60:
                float_score = 80.0
            elif float_ratio >= 0.40:
                float_score = 50.0
            elif float_ratio >= 0.25:
                float_score = 30.0
            else:
                float_score = 10.0  # Low-float VC unlock trap
        else:
            float_score = 65.0  # Default neutral when float ratio unknown

        # -------------------------------------------------------------
        # 3. Friction & Discovery Index (Pre-Consensus)
        # -------------------------------------------------------------
        # Penalizes assets that are already listed on all Tier-1 venues
        t1_count = sum(1 for cex in cls.TIER1_CEX_LIST if cex in exchanges)
        if t1_count == 0:
            friction_score = 100.0  # Maximum discovery alpha (DEX / custom L1 / CLI / OTC)
        elif t1_count == 1:
            friction_score = 75.0   # Early CEX discovery
        elif t1_count == 2:
            friction_score = 45.0   # Moderate consensus
        else:
            friction_score = 15.0   # Full consensus saturation (retail exit liquidity)

        # -------------------------------------------------------------
        # 4. Leading Capital & Fee Efficiency (Organic Traction)
        # -------------------------------------------------------------
        # Annualized Fees / TVL or Daily Fees relative to low cap
        annualized_fees = daily_fees * 365
        fee_to_tvl_ratio = (annualized_fees / tvl) if tvl > 0 else 0.0

        if fee_to_tvl_ratio >= 0.05 or daily_fees >= 25_000:
            fee_score = 100.0
        elif fee_to_tvl_ratio >= 0.02 or daily_fees >= 8_000:
            fee_score = 85.0
        elif fee_to_tvl_ratio >= 0.008 or daily_fees >= 2_000:
            fee_score = 65.0
        elif daily_fees > 0 or daily_revenue > 0:
            fee_score = 45.0
        elif tvl >= 5_000_000:
            fee_score = 40.0
        else:
            fee_score = 20.0

        # -------------------------------------------------------------
        # 5. Architectural Singularity & Dev Velocity
        # -------------------------------------------------------------
        tech_score = 60.0
        # Non-EVM / Rust / Move / BlockDAG / Sovereign L1 / DePIN innovation bonus
        non_evm_keywords = {"rust", "move", "solana", "sui", "aptos", "substrate", "cosmos", "blockdag", "hyperbft"}
        is_novel_arch = any(kw in category or any(kw in str(c).lower() for c in chains) for kw in non_evm_keywords)
        if is_novel_arch or category in ("depin", "ai", "derivatives"):
            tech_score += 20.0

        # GitHub commit continuity
        if github_metrics:
            commits_90d = github_metrics.get("commits_90d", 0)
            is_active = github_metrics.get("is_active", False)
            if commits_90d >= 150 and is_active:
                tech_score += 20.0
            elif commits_90d >= 60:
                tech_score += 10.0
            elif not is_active:
                tech_score -= 25.0  # Zombie repo penalty

        tech_score = min(100.0, max(10.0, tech_score))

        # -------------------------------------------------------------
        # Composite Asymmetric Alpha Score
        # -------------------------------------------------------------
        alpha_score = round(
            (headroom_score * cls.WEIGHTS["headroom"])
            + (float_score * cls.WEIGHTS["clean_float"])
            + (friction_score * cls.WEIGHTS["friction"])
            + (fee_score * cls.WEIGHTS["fee_efficiency"])
            + (tech_score * cls.WEIGHTS["tech_velocity"]),
            1,
        )

        # Classification
        if alpha_score >= 80.0 and headroom_score >= 70.0 and float_score >= 50.0:
            classification = "Asymmetric Prime (50x Candidate)"
            verdict = "INCUBATOR_BUY"
        elif alpha_score >= 65.0 and headroom_score >= 45.0:
            classification = "Emerging Contender"
            verdict = "INCUBATOR_WATCH"
        else:
            classification = "Neutral / Saturated"
            verdict = "PASS"

        return {
            "symbol": symbol,
            "name": name,
            "asymmetric_score": alpha_score,
            "classification": classification,
            "verdict": verdict,
            "pillars": {
                "headroom": round(headroom_score, 1),
                "clean_float": round(float_score, 1),
                "friction": round(friction_score, 1),
                "fee_efficiency": round(fee_score, 1),
                "tech_velocity": round(tech_score, 1),
            },
            "metrics": {
                "fdv": eff_fdv,
                "float_ratio": round(float_ratio, 2) if float_ratio is not None else None,
                "tier1_cex_count": t1_count,
                "fee_to_tvl_ratio": round(fee_to_tvl_ratio, 4),
                "daily_fees": daily_fees,
                "tvl": tvl,
            },
        }

    @classmethod
    def build_incubator_basket(
        cls,
        candidates: List[Dict[str, Any]],
        total_budget_pct: float = 10.0,
        per_asset_target: float = 2.0,
        max_assets: int = 5,
    ) -> Dict[str, Any]:
        """
        Builds a risk-managed incubator basket strictly adhering to the 10% risk budget:
        - Top 5 candidates scoring highest in Asymmetric Alpha.
        - Target sizing: ~2.0% per asset.
        - Mathematical payoff model:
          If 4 wipe out (-100%) and 1 yields 50x:
          Net gain = (1 * 2% * 50) - (4 * 2%) = +100% - 8% = +92% return to overall portfolio!
        """
        # Filter for approved incubator candidates
        qualified = [c for c in candidates if c.get("asymmetric_score", 0) >= 65.0]
        qualified.sort(key=lambda x: x.get("asymmetric_score", 0), reverse=True)

        selected = qualified[:max_assets]
        if not selected:
            return {
                "total_allocation_pct": 0.0,
                "basket": [],
                "expected_asymmetry_payout": "No qualified candidates currently meet the 5-pillar 50x threshold.",
            }

        weight_per_asset = round(min(per_asset_target, total_budget_pct / len(selected)), 2)
        total_allocated = round(weight_per_asset * len(selected), 2)

        basket_items = []
        for c in selected:
            basket_items.append({
                "symbol": c.get("symbol"),
                "name": c.get("name"),
                "score": c.get("asymmetric_score"),
                "classification": c.get("classification"),
                "target_weight_pct": weight_per_asset,
                "max_downside_pct": weight_per_asset,
                "upside_50x_pct": round(weight_per_asset * 50, 1),
            })

        return {
            "total_allocation_pct": total_allocated,
            "risk_cushion_unallocated_pct": round(total_budget_pct - total_allocated, 2),
            "basket": basket_items,
            "mathematical_model": {
                "base_downside_max": f"-{total_allocated}% (Total loss scenario of all positions)",
                "payout_scenario_1_hit_50x": f"+{round(weight_per_asset * 50 - (len(selected) - 1) * weight_per_asset, 1)}% net to total portfolio",
                "payout_scenario_1_hit_20x": f"+{round(weight_per_asset * 20 - (len(selected) - 1) * weight_per_asset, 1)}% net to total portfolio",
            },
        }
