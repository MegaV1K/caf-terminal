"""
Derivatives & Options Risk Engine for CAF-Terminal.

Implements institutional rules derived from crypto options and derivatives trading:
1. Expiration Margin Cliff Guard (Защита от экспирационной маржинальной ямы).
2. Notional Fee Drag Calculator (Учёт комиссий от базового актива / Notional Fee Trap).
3. Bid-Ask Spread & Liquidity Guard (Защита от спредовой ловушки в ITM/OTM).
4. Open Interest (OI) Pinning & Institutional Delta-Hedge Break-Even Zones.
"""

from typing import Any, Dict, List, Optional


class DerivativesRiskEngine:
    """Specialized engine for quantifying derivatives, options, and cross-margin risks."""

    # Default thresholds
    CRITICAL_HOURS_TO_EXPIRY = 48.0   # Window where margin collateral haircut accelerates
    MAX_ACCEPTABLE_FEE_DRAG  = 0.15   # Max 15% of expected trade profit consumed by fees
    MAX_SPREAD_TO_PROFIT     = 0.20   # If bid-ask spread > 20% of profit, market close is blocked
    MIN_OI_CLUSTER_SIZE_ETH  = 2_500  # Minimum ETH open interest to qualify as institutional wall
    MIN_OI_CLUSTER_SIZE_BTC  = 500    # Minimum BTC open interest to qualify as institutional wall

    @classmethod
    def evaluate_expiration_margin_cliff(
        cls,
        account_equity: float,
        maintenance_margin: float,
        options_collateral_value: float,
        hours_to_expiry: float,
    ) -> Dict[str, Any]:
        """
        Calculates post-expiration margin deficit.
        Prevents instant liquidation when options vanish upon expiration while
        unhedged futures positions remain open on cross-margin.
        """
        # Haircut multiplier: options collateral value decays to 0 at expiry
        if hours_to_expiry <= 0:
            haircut = 1.0
        elif hours_to_expiry <= cls.CRITICAL_HOURS_TO_EXPIRY:
            # Linear decay from 0.0 at 48h to 1.0 at 0h
            haircut = 1.0 - (hours_to_expiry / cls.CRITICAL_HOURS_TO_EXPIRY)
        else:
            haircut = 0.0

        effective_options_collateral = options_collateral_value * (1.0 - haircut)
        post_expiry_equity = (account_equity - options_collateral_value) + effective_options_collateral

        is_critical = post_expiry_equity < maintenance_margin
        margin_cushion_pct = (
            ((post_expiry_equity - maintenance_margin) / maintenance_margin * 100)
            if maintenance_margin > 0
            else 100.0
        )

        return {
            "hours_to_expiry": hours_to_expiry,
            "haircut_applied_pct": round(haircut * 100, 1),
            "current_equity": account_equity,
            "projected_post_expiry_equity": round(post_expiry_equity, 2),
            "maintenance_margin": maintenance_margin,
            "margin_cushion_pct": round(margin_cushion_pct, 1),
            "is_liquidation_hazard": is_critical,
            "recommended_action": (
                "EMERGENCY: Immediate futures deleveraging or synchronized expiry matching required!"
                if is_critical
                else ("WARNING: Tight margin cushion under 15% approaching expiry" if margin_cushion_pct < 15.0 else "SAFE")
            ),
        }

    @classmethod
    def calculate_notional_fee_drag(
        cls,
        symbol: str,
        contracts: float,
        underlying_price: float,
        option_premium_usd: float,
        expected_profit_usd: float,
        fee_rate_bps: float = 3.0,  # 3 bps (0.03%) standard Deribit taker fee
        has_referral_discount: bool = True,
    ) -> Dict[str, Any]:
        """
        Calculates true transaction fee calculated against full NOTIONAL VALUE
        (contracts * underlying_price) rather than the nominal option premium.
        """
        effective_rate = (fee_rate_bps * 0.8) if has_referral_discount else fee_rate_bps
        notional_value = contracts * underlying_price

        # Fee is calculated on notional, but capped at 12.5% of option premium on major exchanges
        notional_fee = notional_value * (effective_rate / 10_000.0)
        max_fee_cap = option_premium_usd * contracts * 0.125
        actual_one_way_fee = min(notional_fee, max_fee_cap) if max_fee_cap > 0 else notional_fee
        round_trip_fee = actual_one_way_fee * 2.0  # Open + Close

        fee_drag_pct = (round_trip_fee / expected_profit_usd) if expected_profit_usd > 0 else 1.0

        is_fee_trap = fee_drag_pct > cls.MAX_ACCEPTABLE_FEE_DRAG

        return {
            "symbol": symbol.upper(),
            "contracts": contracts,
            "notional_value_usd": round(notional_value, 2),
            "round_trip_fee_usd": round(round_trip_fee, 2),
            "expected_profit_usd": expected_profit_usd,
            "fee_drag_pct": round(fee_drag_pct * 100, 2),
            "is_fee_trap": is_fee_trap,
            "verdict": (
                f"FEE_TRAP: Fees consume {fee_drag_pct*100:.1f}% of projected profit (max allowed: {cls.MAX_ACCEPTABLE_FEE_DRAG*100:.0f}%)"
                if is_fee_trap
                else "ACCEPTABLE_FEE_DRAG"
            ),
        }

    @classmethod
    def validate_liquidity_and_spread(
        cls,
        symbol: str,
        bid_price: float,
        ask_price: float,
        projected_profit_usd: float,
        contracts: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Protects against the Liquidity Trap in Deep ITM or Far OTM positions.
        If bid-ask spread consumes > 20% of profit, market liquidation is blocked
        and synthetic futures lock is recommended.
        """
        if bid_price <= 0 or ask_price <= 0:
            return {
                "status": "BLOCKED",
                "reason": "Illiquid orderbook (zero bid or ask)",
                "recommended_action": "SYNTHETIC_DELTA_LOCK",
            }

        mid_price = (bid_price + ask_price) / 2.0
        spread = ask_price - bid_price
        spread_pct = (spread / mid_price) * 100.0
        slippage_cost_usd = (spread / 2.0) * contracts

        spread_to_profit_ratio = (
            (slippage_cost_usd / projected_profit_usd) if projected_profit_usd > 0 else 1.0
        )

        is_liquidity_trap = spread_to_profit_ratio > cls.MAX_SPREAD_TO_PROFIT

        return {
            "symbol": symbol.upper(),
            "bid": bid_price,
            "ask": ask_price,
            "spread_usd": round(spread, 4),
            "spread_pct": round(spread_pct, 2),
            "slippage_cost_usd": round(slippage_cost_usd, 2),
            "spread_to_profit_pct": round(spread_to_profit_ratio * 100, 2),
            "is_liquidity_trap": is_liquidity_trap,
            "execution_mode": (
                "SYNTHETIC_FUTURES_DELTA_HEDGE"
                if is_liquidity_trap
                else "MARKET_OR_LIMIT_ORDER"
            ),
            "advisory": (
                f"Market sell will lose ${slippage_cost_usd:.2f} ({spread_to_profit_ratio*100:.1f}% of profit) to wide spread. "
                f"Lock profit synthetically via futures hedge instead of dumping into illiquid book."
                if is_liquidity_trap
                else "Orderbook liquidity is sufficient for direct execution."
            ),
        }

    @classmethod
    def calculate_oi_pinning_zones(
        cls,
        clusters: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Calculates institutional delta-hedging reaction boundaries (OI Pinning).
        When price approaches Strike +/- Premium of large OI, market makers are
        mechanically forced to hedge with futures, causing sharp reactions (especially on ETH).
        """
        results = []
        for c in clusters:
            asset = (c.get("asset") or "ETH").upper()
            strike = float(c.get("strike", 0))
            premium = float(c.get("premium", 0))
            oi = float(c.get("open_interest", 0))
            opt_type = (c.get("type") or "CALL").upper()

            threshold = cls.MIN_OI_CLUSTER_SIZE_BTC if asset == "BTC" else cls.MIN_OI_CLUSTER_SIZE_ETH
            is_institutional_wall = oi >= threshold

            if opt_type == "CALL":
                break_even = strike + premium
                hedge_direction = "SHORT_FUTURES_DELTA_HEDGE"
            else:
                break_even = strike - premium
                hedge_direction = "LONG_FUTURES_DELTA_HEDGE"

            results.append({
                "asset": asset,
                "strike": strike,
                "premium": premium,
                "open_interest": oi,
                "option_type": opt_type,
                "is_institutional_wall": is_institutional_wall,
                "break_even_pinning_level": round(break_even, 2),
                "forced_market_maker_flow": hedge_direction,
                "expected_market_reaction": (
                    f"Strong Resistance / Selling Pressure at ${break_even:,.2f}"
                    if opt_type == "CALL"
                    else f"Strong Support / Buying Pressure at ${break_even:,.2f}"
                ),
            })

        return results
