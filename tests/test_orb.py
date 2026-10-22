from __future__ import annotations

from datetime import time

import pytest

from app.strategy.orb import evaluate_orb, ORBSignal


def _scan(price, or_high, or_low, vwap, rvol=2.0, or_complete=True,
          candle_time=time(10, 0)):
    return {
        "symbol": "TEST", "sector": "NIFTY IT",
        "price": price, "or_high": or_high, "or_low": or_low,
        "or_complete": or_complete, "vwap": vwap, "rvol": rvol,
        "candle_time": candle_time, "change_pct": 0.5,
    }


class TestORBLong:
    def test_valid_long_signal(self):
        scan = _scan(price=1010, or_high=1000, or_low=980, vwap=995)
        sig, reason = evaluate_orb(scan, "BULLISH", ["NIFTY IT"])
        assert sig is not None
        assert sig.action == "BUY"
        assert sig.stop_loss == 980        # ORL is the stop
        assert sig.target > sig.signal_price

    def test_rejects_below_vwap(self):
        scan = _scan(price=990, or_high=1000, or_low=980, vwap=995)
        sig, reason = evaluate_orb(scan, "BULLISH", ["NIFTY IT"])
        assert sig is None
        assert "VWAP" in reason

    def test_rejects_no_breakout(self):
        scan = _scan(price=999, or_high=1000, or_low=980, vwap=990)
        sig, reason = evaluate_orb(scan, "BULLISH", ["NIFTY IT"])
        assert sig is None
        assert "breakout" in reason.lower()

    def test_rejects_low_rvol(self):
        scan = _scan(price=1010, or_high=1000, or_low=980, vwap=990, rvol=0.8)
        sig, reason = evaluate_orb(scan, "BULLISH", ["NIFTY IT"])
        assert sig is None
        assert "RVOL" in reason

    def test_rejects_after_cutoff(self):
        scan = _scan(price=1010, or_high=1000, or_low=980, vwap=990,
                     candle_time=time(14, 35))
        sig, reason = evaluate_orb(scan, "BULLISH", ["NIFTY IT"])
        assert sig is None
        assert "cutoff" in reason.lower()

    def test_rejects_wrong_sector(self):
        scan = _scan(price=1010, or_high=1000, or_low=980, vwap=990)
        sig, reason = evaluate_orb(scan, "BULLISH", ["NIFTY BANK"])
        assert sig is None
        assert "Sector" in reason

    def test_rejects_or_incomplete(self):
        scan = _scan(price=1010, or_high=1000, or_low=980, vwap=990, or_complete=False)
        sig, reason = evaluate_orb(scan, "BULLISH", ["NIFTY IT"])
        assert sig is None


class TestORBShort:
    def test_valid_short_signal(self):
        scan = _scan(price=978, or_high=1000, or_low=980, vwap=985)
        sig, reason = evaluate_orb(scan, "BEARISH", ["NIFTY IT"])
        assert sig is not None
        assert sig.action == "SHORT"
        assert sig.stop_loss == 1000       # ORH is the stop

    def test_rejects_above_vwap(self):
        scan = _scan(price=990, or_high=1000, or_low=980, vwap=985)
        sig, reason = evaluate_orb(scan, "BEARISH", ["NIFTY IT"])
        assert sig is None

    def test_neutral_market_no_trade(self):
        scan = _scan(price=1010, or_high=1000, or_low=980, vwap=990)
        sig, reason = evaluate_orb(scan, "NEUTRAL", ["NIFTY IT"])
        assert sig is None
        assert "NEUTRAL" in reason
