"""
Tests for 4-Tier Investment Cadence: Daily Sensor, Monthly Audit, and Quarterly Rebalancing.
Run: pytest tests/test_cadence.py -v
"""
import sys
import tempfile
from pathlib import Path
from pathlib import Path as PathlibPath

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.registry import CAFRegistry
from src.scoring.portfolio_audit import MonthlyAuditor, QuarterlyRebalancer
from src.scouts.daily_sensor import DailySensor


def test_daily_sensor_filters():
    """DailySensor should enforce flash TVL thresholds and format anomaly objects."""
    sensor = DailySensor()
    # Mock protocol data
    mock_protocols = [
        {"name": "TinySpike", "symbol": "TINY", "tvl": 500_000, "change_1d": 50.0},     # TVL < $2M -> skip
        {"name": "GiantNormal", "symbol": "NORM", "tvl": 100_000_000, "change_1d": 2.0},  # c1d < 25% -> skip
        {"name": "FlashWinner", "symbol": "FLASH", "tvl": 5_000_000, "change_1d": 45.0, "category": "DePIN"}, # pass
    ]
    sensor.llama.fetch_protocols = lambda force_refresh=False: mock_protocols
    sensor.llama.fetch_fees_and_revenue = lambda force_refresh=False: {}
    sensor.coingecko.fetch_markets = lambda pages=2, force_refresh=False: []

    anomalies = sensor.scan()
    assert len(anomalies) == 1
    assert anomalies[0]["symbol"] == "FLASH"
    assert anomalies[0]["reason"] == "Суточный взлёт TVL"


def test_quarterly_rebalance_take_profit_and_drawdown():
    """QuarterlyRebalancer should detect take-profit (>100% or target hit) and drawdown (<-25%)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = PathlibPath(tmpdir) / "test_rebalance.db"
        reg = CAFRegistry(db_path=db_path)

        # Asset 1: Take profit hit (entry $1.0, current $2.5, target $2.0 -> +150%)
        reg.upsert_asset(symbol="PROFIT", name="Profit Coin", tier="Core Candidate")
        reg.update_price(symbol="PROFIT", entry_price=1.0, current_price=2.5, target_price=2.0)

        # Asset 2: Drawdown (entry $10.0, current $6.0 -> -40%)
        reg.upsert_asset(symbol="DRAW", name="Draw Coin", tier="Watch")
        reg.update_price(symbol="DRAW", entry_price=10.0, current_price=6.0, target_price=25.0)

        # Asset 3: Normal performer (entry $2.0, current $2.2 -> +10%)
        reg.upsert_asset(symbol="NORM", name="Normal Coin", tier="High Conviction")
        reg.update_price(symbol="NORM", entry_price=2.0, current_price=2.2, target_price=5.0)

        rebalancer = QuarterlyRebalancer()
        rebalancer.reg = reg
        rebalancer.cg.fetch_markets = lambda pages=3, force_refresh=False: []

        summary = rebalancer.rebalance()
        assert not summary.get("empty")
        assert summary["total_positions"] == 3

        # Check take profit
        tp_symbols = [t["symbol"] for t in summary["targets_hit"]]
        assert "PROFIT" in tp_symbols

        # Check drawdowns
        dd_symbols = [d["symbol"] for d in summary["drawdowns"]]
        assert "DRAW" in dd_symbols


def test_quarterly_rebalance_empty():
    """QuarterlyRebalancer on empty portfolio should report empty."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = PathlibPath(tmpdir) / "test_empty.db"
        reg = CAFRegistry(db_path=db_path)

        rebalancer = QuarterlyRebalancer()
        rebalancer.reg = reg

        summary = rebalancer.rebalance()
        assert summary.get("empty") is True
