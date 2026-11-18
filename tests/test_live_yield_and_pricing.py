"""
Unit tests for LiveYieldScout and live registry pricing update.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import MagicMock, patch
from src.scouts.live_yield_scout import LiveYieldScout
from src.database.registry import CAFRegistry


def test_live_yield_scout_hyperliquid_filtering(tmp_path):
    scout = LiveYieldScout(cache_dir=tmp_path)
    mock_meta = {
        "universe": [{"name": "TESTCOIN"}],
    }
    mock_ctxs = [
        {"funding": "0.0001", "dayNtlVlm": "2000000", "oraclePrice": "10.0", "openInterest": "50000"}
    ]
    with patch("requests.post") as mock_post:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = [mock_meta, mock_ctxs]
        mock_post.return_value = resp

        opps = scout.fetch_hyperliquid_funding(min_apr_pct=8.0, min_24h_vol_usd=100_000, force_refresh=True)
        assert len(opps) == 1
        assert opps[0]["symbol"] == "TESTCOIN"
        assert opps[0]["current_apr_pct"] > 8.0
        assert opps[0]["venue"] == "Hyperliquid"


def test_live_yield_scout_pendle_pt(tmp_path):
    scout = LiveYieldScout(cache_dir=tmp_path)
    mock_pendle_res = {
        "results": [
            {
                "pt": {"symbol": "PT-sUSDe-25MAR2027"},
                "impliedApy": 0.125,
                "ptDiscount": 0.05,
                "liquidity": {"usd": 500000},
                "expiry": "2027-03-25T00:00:00Z",
                "accountingAsset": {"symbol": "USDe"},
                "protocol": "Ethena",
            }
        ]
    }
    with patch("requests.get") as mock_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = mock_pendle_res
        mock_get.return_value = resp

        pt_list = scout.fetch_pendle_pt_markets(min_apy_pct=5.0, chain_id=1, force_refresh=True)
        assert len(pt_list) == 1
        assert pt_list[0]["pt_symbol"] == "PT-sUSDe-25MAR2027"
        assert pt_list[0]["implied_fixed_apy_pct"] == 12.50
        assert pt_list[0]["discount_pct"] == 5.00


def test_registry_update_live_prices(tmp_path):
    db_file = tmp_path / "test_reg.db"
    reg = CAFRegistry(db_path=db_file)
    reg.upsert_asset(symbol="TEST", name="Test Asset", tier="Core", score=85.0)
    reg.update_price(symbol="TEST", entry_price=10.0, current_price=10.0)

    # Mock coingecko markets
    with patch("src.scouts.coingecko.CoinGeckoScout.fetch_markets") as mock_fetch:
        mock_fetch.return_value = [{"symbol": "TEST", "current_price": 15.0}]
        res = reg.update_live_prices(force_refresh=True)
        assert res["updated_count"] >= 1

        all_assets = reg.get_all_assets()
        test_asset = [a for a in all_assets if a["symbol"] == "TEST"][0]
        assert test_asset["current_price"] == 15.0
        assert test_asset["pnl_pct"] == 50.0
