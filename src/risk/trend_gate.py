"""
Price Trend and Momentum Gate for CAF-Terminal.

Eliminates the 'falling knife' / 'value trap' problem.
Even if an asset passes fundamental screening, capital is NEVER allocated
to an asset in an active price downtrend (below 200 EMA or underperforming BTC).
Instead, capital is automatically preserved in 100% USDC/Cash buffer.
"""

from typing import Any, Dict, Optional


class PriceTrendGate:
    """
    Enforces institutional trend-following discipline before capital deployment.
    """

    def __init__(self, ema_period: int = 200):
        self.ema_period = ema_period

    def evaluate_trend(
        self,
        symbol: str,
        current_price: float,
        ema_200: float,
        alt_btc_ratio: Optional[float] = None,
        alt_btc_50_sma: Optional[float] = None,
        manual_override: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Evaluates whether an asset qualifies for LONG allocation based on Price Action.

        Rules:
        1. If price < ema_200: DOWNTREND -> Target weight forced to 0.0% (USDC Buffer).
        2. If ALT/BTC < 50 SMA: RELATIVE WEAKNESS -> Target weight forced to 0.0%.
        3. If price >= ema_200 and ALT/BTC healthy: UPTREND -> Allocation Approved.
        """
        symbol_upper = symbol.upper()

        if manual_override is not None:
            is_uptrend = manual_override
            reason = "MANUAL_TREND_OVERRIDE"
        else:
            is_below_ema = current_price < ema_200 if ema_200 > 0 else False
            is_relative_weak = (
                alt_btc_ratio < alt_btc_50_sma
                if (alt_btc_ratio and alt_btc_50_sma and alt_btc_50_sma > 0)
                else False
            )

            if is_below_ema or is_relative_weak:
                is_uptrend = False
                reasons = []
                if is_below_ema:
                    diff_pct = round(((current_price - ema_200) / ema_200) * 100, 1)
                    reasons.append(f"Price (${current_price}) < 200 EMA (${ema_200}) [{diff_pct}%]")
                if is_relative_weak:
                    reasons.append(f"ALT/BTC ratio ({alt_btc_ratio:.6f}) < 50 SMA ({alt_btc_50_sma:.6f})")
                reason = " | ".join(reasons)
            else:
                is_uptrend = True
                diff_pct = round(((current_price - ema_200) / ema_200) * 100, 1) if ema_200 > 0 else 0.0
                reason = f"Confirmed Uptrend: Price above 200 EMA (+{diff_pct}%)"

        action = "ALLOCATE_TARGET_WEIGHT" if is_uptrend else "DEFENSIVE_USDC_PRESERVATION"
        effective_allocation_multiplier = 1.0 if is_uptrend else 0.0

        return {
            "symbol": symbol_upper,
            "is_uptrend": is_uptrend,
            "current_price": current_price,
            "ema_200": ema_200,
            "action": action,
            "effective_multiplier": effective_allocation_multiplier,
            "diagnostic_reason": reason,
            "capital_destination": symbol_upper if is_uptrend else "USDC_YIELD_RESERVE",
        }

    def filter_portfolio_allocations(
        self,
        target_weights: Dict[str, float],
        market_data: Dict[str, Dict[str, float]],
    ) -> Dict[str, Any]:
        """
        Filters a full portfolio target allocation map through the Price Trend Gate.
        Redirects capital from falling assets into USDC_RESERVE.
        """
        adjusted_weights: Dict[str, float] = {}
        usdc_reserve_weight = 0.0
        blocked_assets = []
        approved_assets = []

        for symbol, target_weight in target_weights.items():
            sym = symbol.upper()
            data = market_data.get(sym, {})
            price = data.get("price", 0.0)
            ema = data.get("ema_200", 0.0)
            alt_btc = data.get("alt_btc", None)
            alt_btc_sma = data.get("alt_btc_sma", None)

            # If no price data, default to conservative block if specified
            if price <= 0 or ema <= 0:
                adjusted_weights[sym] = target_weight
                approved_assets.append(sym)
                continue

            gate_result = self.evaluate_trend(
                symbol=sym,
                current_price=price,
                ema_200=ema,
                alt_btc_ratio=alt_btc,
                alt_btc_50_sma=alt_btc_sma,
            )

            if gate_result["is_uptrend"]:
                adjusted_weights[sym] = target_weight
                approved_assets.append(sym)
            else:
                adjusted_weights[sym] = 0.0
                usdc_reserve_weight += target_weight
                blocked_assets.append({
                    "symbol": sym,
                    "target_weight_cut": target_weight,
                    "reason": gate_result["diagnostic_reason"],
                })

        adjusted_weights["USDC_RESERVE"] = round(
            adjusted_weights.get("USDC_RESERVE", 0.0) + usdc_reserve_weight, 2
        )

        return {
            "approved_assets": approved_assets,
            "blocked_assets": blocked_assets,
            "adjusted_weights": adjusted_weights,
            "usdc_cash_buffer_pct": round(adjusted_weights["USDC_RESERVE"], 2),
        }
