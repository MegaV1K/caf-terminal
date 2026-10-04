"""
CAF / CVE Scoring Engine
Implements the 5-pillar CVE evaluation methodology:
1. Business Quality (BQ)
2. Economic Value Capture (EVC)
3. Tokenomics & Dilution Overhang (T)
4. Resilience & Lindy Effect (R)
5. Fragility & Risk Exposure (F)

Outputs:
- CVE Tier: Core, High Conviction, Invest, Watch
- Emerging Radar Score (for incubator discovery outside Top 100/200)
"""

from typing import Any, Dict, List, Optional


class CAFScorer:
    """Scorer implementing the CAF/CVE investment methodology."""

    # Category strategic weights for Business Quality
    CATEGORY_QUALITY_WEIGHTS = {
        "depin": 9.0,
        "rwa": 8.8,
        "layer 1": 8.5,
        "layer 2": 8.0,
        "ai": 8.2,
        "infrastructure": 8.5,
        "dex": 8.0,
        "derivatives": 8.2,
        "liquid staking": 8.0,
        "restaking": 8.2,
        "lending": 7.5,
        "yield": 7.0,
        "privacy": 8.0,
        "gaming": 6.5,
        "nft": 5.5,
        "metaverse": 5.0,
        "meme": 2.5,
    }

    @classmethod
    def calculate_cve_score(
        cls,
        metrics: Dict[str, Any],
        manual_override: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Calculates 5-pillar CVE score (0 - 100) and assigns classification tier:
        - Core (>= 85 and Value Capture >= 80)
        - High Conviction (>= 72)
        - Invest (50 - 71)
        - Watch (< 50 or High Fragility)
        """
        category = (metrics.get("category") or "").lower()
        mcap = metrics.get("mcap") or 0
        fdv = metrics.get("fdv") or mcap
        tvl = metrics.get("tvl") or 0
        fees_24h = metrics.get("daily_fees") or 0
        revenue_24h = metrics.get("daily_revenue") or 0
        rank = metrics.get("rank") or 999

        # 1. Business Quality (0-100)
        # Baseline from strategic sector significance + category
        base_bq = 60.0
        for cat_key, cat_val in cls.CATEGORY_QUALITY_WEIGHTS.items():
            if cat_key in category:
                base_bq = cat_val * 10
                break
        
        # Adjust for proven TVL and market presence
        if tvl > 100_000_000:
            base_bq += 10
        elif tvl > 10_000_000:
            base_bq += 5

        bq_score = min(100.0, max(20.0, base_bq))

        # 2. Economic Value Capture (EVC) (0-100)
        # Based on real fees/revenue generated relative to valuation
        evc_score = 50.0  # neutral default
        if revenue_24h > 0 or fees_24h > 0:
            annualized_rev = (revenue_24h or (fees_24h * 0.2)) * 365
            if mcap > 0 and annualized_rev > 0:
                ps_ratio = mcap / annualized_rev
                if ps_ratio < 15:
                    evc_score = 92.0
                elif ps_ratio < 40:
                    evc_score = 80.0
                elif ps_ratio < 100:
                    evc_score = 68.0
                else:
                    evc_score = 52.0
            else:
                evc_score = 65.0
        elif "meme" in category:
            evc_score = 15.0
        elif tvl > 50_000_000:
            evc_score = 60.0

        # 3. Tokenomics & Dilution Overhang (0-100)
        # Penalizes high FDV / Market Cap ratio
        fdv_mcap_ratio = metrics.get("fdv_mcap_ratio")
        if not fdv_mcap_ratio and mcap > 0 and fdv > 0:
            fdv_mcap_ratio = fdv / mcap

        if not fdv_mcap_ratio or fdv_mcap_ratio <= 1.15:
            tokenomics_score = 90.0  # Fully unlocked or minimal dilution
        elif fdv_mcap_ratio <= 1.5:
            tokenomics_score = 80.0
        elif fdv_mcap_ratio <= 2.5:
            tokenomics_score = 65.0
        elif fdv_mcap_ratio <= 4.0:
            tokenomics_score = 45.0  # Significant unlocks pending
        else:
            tokenomics_score = 25.0  # Extreme dilution overhang

        # 4. Resilience & Lindy Effect (0-100)
        # Market rank, liquidity, multi-chain deployment
        resilience_score = 50.0
        if rank <= 50:
            resilience_score = 88.0
        elif rank <= 150:
            resilience_score = 75.0
        elif rank <= 300:
            resilience_score = 60.0
        else:
            resilience_score = 45.0

        chains = metrics.get("chains") or []
        if len(chains) >= 3:
            resilience_score = min(100.0, resilience_score + 8.0)

        # 5. Fragility & Risk Exposure (0-100, where 100 = safest, lowest fragility)
        # Penalizes extreme volatility, meme status, hyper-concentration
        fragility_penalty = 0.0
        if "meme" in category:
            fragility_penalty += 45.0
        if fdv_mcap_ratio and fdv_mcap_ratio > 5.0:
            fragility_penalty += 20.0
        if rank > 400:
            fragility_penalty += 15.0

        safety_score = max(10.0, 85.0 - fragility_penalty)

        # Allow manual overrides from expert review
        if manual_override:
            bq_score = manual_override.get("bq", bq_score)
            evc_score = manual_override.get("evc", evc_score)
            tokenomics_score = manual_override.get("t", tokenomics_score)
            resilience_score = manual_override.get("r", resilience_score)
            safety_score = manual_override.get("safety", safety_score)

        # Weighted Composite CVE Score:
        # BQ: 25%, EVC: 25%, Tokenomics: 20%, Resilience: 15%, Safety: 15%
        composite_score = round(
            (bq_score * 0.25)
            + (evc_score * 0.25)
            + (tokenomics_score * 0.20)
            + (resilience_score * 0.15)
            + (safety_score * 0.15),
            1,
        )

        # Tier Assignment
        if composite_score >= 82 and evc_score >= 75 and safety_score >= 70:
            tier = "Core Candidate"
        elif composite_score >= 70 and safety_score >= 50:
            tier = "High Conviction"
        elif composite_score >= 48:
            tier = "Invest"
        else:
            tier = "Watch"

        return {
            "symbol": metrics.get("symbol", "").upper(),
            "name": metrics.get("name", ""),
            "composite_score": composite_score,
            "tier": tier,
            "pillars": {
                "business_quality": round(bq_score, 1),
                "value_capture": round(evc_score, 1),
                "tokenomics": round(tokenomics_score, 1),
                "resilience": round(resilience_score, 1),
                "safety_anti_fragility": round(safety_score, 1),
            },
            "signals": {
                "fdv_mcap_ratio": fdv_mcap_ratio,
                "tvl": tvl,
                "daily_fees": fees_24h,
                "daily_revenue": revenue_24h,
            },
        }

    @classmethod
    def score_emerging_candidate(cls, protocol: Dict[str, Any]) -> float:
        """
        Scores emerging incubator candidates outside Top 100/200.
        Emphasizes:
        - 7d / 30d TVL acceleration
        - Fee generation
        - Valuation efficiency (Mcap / TVL)
        """
        change_7d = protocol.get("change_7d") or 0
        change_1m = protocol.get("change_1m") or 0
        tvl = protocol.get("tvl") or 0
        mcap = protocol.get("mcap") or 0
        daily_fees = protocol.get("daily_fees") or 0

        score = 40.0

        # TVL Momentum (up to +30 pts)
        if change_7d > 50:
            score += 25
        elif change_7d > 20:
            score += 18
        elif change_7d > 10:
            score += 10

        if change_1m > 30:
            score += 10
        elif change_1m > 15:
            score += 5

        # Fee generation signal (up to +20 pts)
        if daily_fees > 10_000:
            score += 20
        elif daily_fees > 2_000:
            score += 12
        elif daily_fees > 500:
            score += 6

        # Capital efficiency: TVL backing vs Mcap (up to +15 pts)
        if mcap > 0 and tvl > 0:
            ratio = mcap / tvl
            if ratio < 0.8:
                score += 15
            elif ratio < 1.5:
                score += 10
            elif ratio < 3.0:
                score += 5

        return round(min(100.0, score), 1)
