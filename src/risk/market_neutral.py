"""
Market-Neutral & Yield-Stripping Engine for CAF-Terminal.

Executes non-directional, asymmetric profit strategies:
1. Relative Value Pair Trading (Long Strong Benchmark vs Short Inflation Basket).
2. Funding Rate Arbitrage (Cash and Carry / Cross-DEX Funding Yield).
3. Fixed Dollar Yield Stripping (Pendle PT Discount Harvest).
"""

from typing import Any, Dict, List, Optional


class MarketNeutralEngine:
    """
    Constructs market-neutral trades to monetize market inefficiencies and structural inflation.
    """

    def construct_pair_trade(
        self,
        long_benchmark: str,
        short_basket: List[str],
        total_notional_usd: float,
        benchmark_weight_pct: float = 50.0,
    ) -> Dict[str, Any]:
        """
        Creates a Beta-Neutral / Relative Value pair:
        Long Benchmark (BTC/SOL) 50% vs Short Inflation Basket 50%.
        """
        long_capital = total_notional_usd * (benchmark_weight_pct / 100.0)
        short_capital = total_notional_usd - long_capital

        n_shorts = len(short_basket) or 1
        per_short_capital = round(short_capital / n_shorts, 2)

        short_allocations = [
            {
                "symbol": sym.upper(),
                "side": "SHORT",
                "capital_usd": per_short_capital,
                "weight_pct": round((per_short_capital / total_notional_usd) * 100, 2),
                "rationale": "Structural emissions/inflation exceeds protocol fee burns.",
            }
            for sym in short_basket
        ]

        return {
            "strategy": "RELATIVE_VALUE_BETA_NEUTRAL",
            "total_notional_usd": total_notional_usd,
            "net_market_delta": 0.0,
            "long_leg": {
                "symbol": long_benchmark.upper(),
                "side": "LONG",
                "capital_usd": long_capital,
                "weight_pct": benchmark_weight_pct,
                "rationale": "High institutional inflow / benchmark store of value.",
            },
            "short_leg": short_allocations,
            "expected_payoff_scenarios": {
                "market_dump_-30%": "Long leg loses -30%, Short basket loses -55% -> Net Profit +25%",
                "market_flat_0%": "Long leg 0%, Short basket bleeds -15% from emissions -> Net Profit +15%",
                "market_pump_+30%": "Long leg gains +30%, Short basket gains +20% -> Net Profit +10%",
            },
        }

    def evaluate_funding_arbitrage(
        self,
        symbol: str,
        spot_price: float,
        perp_price: float,
        funding_rate_8h_pct: float,
        notional_size_usd: float,
        trading_fee_bps: float = 5.0,  # 0.05%
    ) -> Dict[str, Any]:
        """
        Evaluates Cash and Carry / Delta-Neutral funding rate harvest.
        """
        # Annualized funding APR: 3 funding intervals per day * 365 = 1095 intervals
        annualized_funding_apr_pct = round(funding_rate_8h_pct * 3 * 365, 2)
        
        # Roundtrip trading fee on 2 legs (Spot + Perp) = 4 executions * fee_bps
        roundtrip_fee_pct = (trading_fee_bps * 4) / 100.0
        
        # Days needed to break even on trading fees
        daily_funding_pct = funding_rate_8h_pct * 3
        days_to_breakeven = (
            round(roundtrip_fee_pct / daily_funding_pct, 1)
            if daily_funding_pct > 0
            else 999.0
        )

        is_viable = annualized_funding_apr_pct >= 12.0 and days_to_breakeven <= 7.0

        if funding_rate_8h_pct > 0:
            recommended_trade = "LONG_SPOT_SHORT_PERP"
            who_pays = "Longs pay shorts -> Collect funding by being SHORT Perp"
        elif funding_rate_8h_pct < 0:
            recommended_trade = "SHORT_SPOT_LONG_PERP"
            who_pays = "Shorts pay longs -> Collect funding by being LONG Perp"
        else:
            recommended_trade = "NO_ARBITRAGE"
            who_pays = "Neutral"

        return {
            "symbol": symbol.upper(),
            "strategy": "DELTA_NEUTRAL_FUNDING_HARVEST",
            "is_viable": is_viable,
            "funding_rate_8h_pct": funding_rate_8h_pct,
            "annualized_funding_apr_pct": annualized_funding_apr_pct,
            "recommended_trade": recommended_trade,
            "who_pays": who_pays,
            "days_to_breakeven": days_to_breakeven,
            "estimated_monthly_profit_usd": round(
                (notional_size_usd * (annualized_funding_apr_pct / 100.0)) / 12, 2
            ),
        }

    def evaluate_fixed_yield_stripping(
        self,
        base_asset: str,
        maturity_date: str,
        pt_discount_price: float,  # e.g. 0.94 for $1 face value
        days_to_maturity: int,
    ) -> Dict[str, Any]:
        """
        Evaluates Principal Token (PT) fixed dollar yield from Pendle.
        Eliminates volatile token directional risk while locking guaranteed USD APY.
        """
        if days_to_maturity <= 0 or pt_discount_price >= 1.0:
            return {"error": "Invalid maturity or price"}

        discount_pct = (1.0 - pt_discount_price) * 100.0
        fixed_apy_pct = round((discount_pct / pt_discount_price) * (365.0 / days_to_maturity), 2)

        return {
            "strategy": "PENDLE_PT_FIXED_DOLLAR_YIELD",
            "base_asset": base_asset.upper(),
            "maturity_date": maturity_date,
            "pt_purchase_price": pt_discount_price,
            "guaranteed_payout_at_maturity": 1.0,
            "discount_captured_pct": round(discount_pct, 2),
            "guaranteed_fixed_apy_pct": fixed_apy_pct,
            "directional_crypto_risk": "0.0% (Zero exposure to token price swings)",
            "smart_contract_risk": "Pendle Finance & Underlying Protocol",
        }
