"""
Smoke tests for CAF-Terminal core modules.
Run: python -m pytest tests/ -v
"""
import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── 1. CVE Scorer Tests ────────────────────────────────────────────────────────

from src.scoring.caf_scorer import CAFScorer


def test_meme_gets_low_score():
    """Meme tokens must score low (high fragility, no value capture) and fall into Watch tier."""
    result = CAFScorer.calculate_cve_score({
        "symbol": "PEPE2",
        "name": "Pepe 2.0",
        "category": "meme",
        "mcap": 10_000_000,
        "fdv": 50_000_000,
        "rank": 500,
    })
    assert result["composite_score"] < 45, f"Expected meme score < 45, got {result['composite_score']}"
    assert result["tier"] == "Watch"


def test_depin_with_revenue_is_high():
    """DePIN with real fees and low P/S should be High Conviction or Core."""
    result = CAFScorer.calculate_cve_score({
        "symbol": "GEOD",
        "name": "GEODNET",
        "category": "depin",
        "mcap": 100_000_000,
        "fdv": 120_000_000,
        "daily_revenue": 50_000,   # $50k/day → $18M/yr → P/S ~5.5
        "rank": 200,
    })
    assert result["composite_score"] >= 70, f"Expected depin+fees score >= 70, got {result['composite_score']}"
    assert result["tier"] in ("High Conviction", "Core Candidate")


def test_fdv_mcap_ratio_penalizes():
    """High FDV/MCap ratio must reduce tokenomics pillar significantly."""
    result_clean = CAFScorer.calculate_cve_score({
        "symbol": "A",
        "name": "Clean",
        "category": "dex",
        "mcap": 100_000_000,
        "fdv": 105_000_000,   # ratio 1.05x → fully unlocked
    })
    result_diluted = CAFScorer.calculate_cve_score({
        "symbol": "B",
        "name": "Diluted",
        "category": "dex",
        "mcap": 100_000_000,
        "fdv": 800_000_000,   # ratio 8x → extreme dilution
    })
    t_clean = result_clean["pillars"]["tokenomics"]
    t_diluted = result_diluted["pillars"]["tokenomics"]
    assert t_clean > t_diluted, f"Expected clean tokenomics {t_clean} > diluted {t_diluted}"


def test_emerging_candidate_scorer():
    """Score for emerging candidate with TVL spike + fees should be > 70."""
    score = CAFScorer.score_emerging_candidate({
        "change_7d": 60,       # +60% TVL
        "change_1m": 40,
        "tvl": 5_000_000,
        "mcap": 3_000_000,
        "daily_fees": 15_000,  # $15k/day
    })
    assert score > 70, f"Expected emerging score > 70, got {score}"


# ── 2. Signal Detector Tests ───────────────────────────────────────────────────

from src.ai.committee import SignalDetector


def test_lido_filtered_out():
    """Lido (TVL > $50M, mcap=0 or > $300M) must NOT pass the signal detector."""
    lido = {
        "name": "Lido",
        "symbol": "LDO",
        "category": "Liquid Staking",
        "tvl": 15_000_000_000,  # $15B TVL
        "mcap": 0,              # Missing MCap in DefiLlama (but TVL > $50M proxy)
        "change_7d": 60,        # Large spike
        "daily_fees": 500_000,
        "daily_revenue": 100_000,
    }
    detector = SignalDetector()
    signals = detector.detect([lido])
    symbols = [s.symbol for s in signals]
    assert "LDO" not in symbols, f"Lido should be filtered out (TVL > $50M with unknown MCap)"


def test_small_defi_protocol_passes():
    """A small protocol with TVL $3M and 40% TVL spike must generate a signal."""
    proto = {
        "name": "SomeNewDEX",
        "symbol": "SNDX",
        "category": "DEX",
        "tvl": 3_000_000,       # $3M TVL
        "mcap": 0,              # No MCap data yet
        "change_7d": 40.0,      # +40% spike
        "daily_fees": None,
        "daily_revenue": None,
    }
    detector = SignalDetector()
    signals = detector.detect([proto])
    symbols = [s.symbol for s in signals]
    assert "SNDX" in symbols, "Small new DEX with TVL spike should generate a signal"


def test_large_mcap_filtered_out():
    """Protocol with known MCap > $300M must be skipped."""
    big = {
        "name": "BigProtocol",
        "symbol": "BIG",
        "category": "Lending",
        "tvl": 5_000_000,
        "mcap": 500_000_000,    # $500M MCap → too large
        "change_7d": 50.0,
        "daily_fees": 50_000,
    }
    detector = SignalDetector()
    signals = detector.detect([big])
    symbols = [s.symbol for s in signals]
    assert "BIG" not in symbols, "Protocol with MCap > $300M must be filtered"


def test_capital_efficiency_signal():
    """Protocol with fees/TVL > 2% must trigger CAPITAL_EFFICIENCY signal."""
    efficient = {
        "name": "EfficientSwap",
        "symbol": "EFF",
        "category": "DEX",
        "tvl": 2_500_000,
        "mcap": 0,
        "change_7d": 5.0,       # Below TVL spike threshold
        "daily_fees": 60_000,   # $60k / $2.5M = 2.4% fee/TVL → CAPITAL_EFFICIENCY
        "daily_revenue": 30_000,
    }
    detector = SignalDetector()
    signals = detector.detect([efficient])
    eff_signals = [s for s in signals if s.symbol == "EFF"]
    assert len(eff_signals) == 1
    assert eff_signals[0].signal_type in ("CAPITAL_EFFICIENCY", "REVENUE_SURGE")


# ── 3. Registry Tests ──────────────────────────────────────────────────────────

import tempfile
from pathlib import Path as PathlibPath
from src.database.registry import CAFRegistry


def test_registry_upsert_and_read():
    """Should insert and retrieve an asset."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = PathlibPath(tmpdir) / "test.db"
        reg = CAFRegistry(db_path=db_path)
        reg.upsert_asset(
            symbol="TEST",
            name="Test Protocol",
            tier="High Conviction",
            sector="DEX",
            score=75.5,
        )
        assets = reg.get_all_assets()
        found = [a for a in assets if a["symbol"] == "TEST"]
        assert len(found) == 1
        assert found[0]["tier"] == "High Conviction"


def test_registry_pnl_tracking():
    """Should calculate PnL correctly when prices are updated."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = PathlibPath(tmpdir) / "test.db"
        reg = CAFRegistry(db_path=db_path)
        reg.upsert_asset(symbol="PNL", name="PnL Test", tier="Watch")
        reg.update_price(symbol="PNL", entry_price=1.00, current_price=1.50)
        pnl_data = reg.get_pnl_summary()
        assert len(pnl_data) == 1
        assert pnl_data[0]["pnl_pct"] == 50.0  # +50%


def test_registry_migration():
    """PnL columns must exist even on an old DB without them."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = PathlibPath(tmpdir) / "test_migrated.db"
        reg = CAFRegistry(db_path=db_path)
        # Verify columns present
        with reg._get_conn() as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(assets)")}
            assert "entry_price" in cols
            assert "pnl_pct" in cols
