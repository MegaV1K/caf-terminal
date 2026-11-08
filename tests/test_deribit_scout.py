"""
Unit tests for DeribitScout (Public API connector, OI clusters, and pinning calculations).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scouts.deribit import DeribitScout


def test_deribit_scout_parse_clusters():
    """Verifies that book summary items are correctly parsed into strikes, OI, and pinning levels."""
    scout = DeribitScout()

    mock_summary = [
        {
            "instrument_name": "ETH-25DEC26-3000-C",
            "open_interest": 5000.0,
            "mark_price": 0.05,
            "bid_price": 0.048,
            "ask_price": 0.052,
            "underlying_price": 2200.0,
            "volume_usd": 150000.0,
            "mark_iv": 62.5,
        },
        {
            "instrument_name": "ETH-25DEC26-2000-P",
            "open_interest": 4000.0,
            "mark_price": 0.03,
            "bid_price": 0.029,
            "ask_price": 0.031,
            "underlying_price": 2200.0,
            "volume_usd": 120000.0,
            "mark_iv": 65.0,
        },
    ]

    with patch.object(scout, "fetch_book_summary", return_value=mock_summary), \
         patch.object(scout, "get_index_price", return_value=2200.0):

        clusters = scout.get_top_oi_clusters(currency="ETH", min_oi=100.0, top_n=5)

        assert len(clusters) == 2

        call_item = next(c for c in clusters if c["type"] == "CALL")
        assert call_item["strike"] == 3000.0
        assert call_item["open_interest"] == 5000.0
        # Premium USD = 0.05 * 2200 = $110. Pinning = 3000 + 110 = 3110
        assert call_item["break_even_pinning_level"] == 3110.0
        assert "Resistance" in call_item["expected_market_reaction"]

        put_item = next(c for c in clusters if c["type"] == "PUT")
        assert put_item["strike"] == 2000.0
        assert put_item["open_interest"] == 4000.0
        # Premium USD = 0.03 * 2200 = $66. Pinning = 2000 - 66 = 1934
        assert put_item["break_even_pinning_level"] == 1934.0
        assert "Support" in put_item["expected_market_reaction"]


def test_deribit_scout_market_analysis():
    """Verifies aggregate calculations: Put/Call ratio, sentiment, and total OI."""
    scout = DeribitScout()

    mock_summary = [
        {"instrument_name": "ETH-25DEC26-3000-C", "open_interest": 10000.0, "mark_iv": 60.0, "volume_usd": 1000.0},
        {"instrument_name": "ETH-25DEC26-2000-P", "open_interest": 5000.0, "mark_iv": 65.0, "volume_usd": 500.0},
    ]

    with patch.object(scout, "fetch_book_summary", return_value=mock_summary), \
         patch.object(scout, "get_index_price", return_value=2000.0), \
         patch.object(scout, "get_historical_volatility", return_value=45.0):

        analysis = scout.analyze_options_market("ETH")

        assert analysis["empty"] is False
        assert analysis["total_open_interest_coins"] == 15000.0
        assert analysis["call_open_interest"] == 10000.0
        assert analysis["put_open_interest"] == 5000.0
        # Put/Call ratio = 5000 / 10000 = 0.50 (< 0.65 -> BULLISH_SKEW)
        assert analysis["put_call_ratio"] == 0.5
        assert "BULLISH_SKEW" in analysis["sentiment"]
