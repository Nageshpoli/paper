from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.market.candles import Candle
from app.strategies.orb.strategy import OpeningRangeBreakoutStrategy

IST = ZoneInfo("Asia/Kolkata")


def _candle(symbol, h, m, price, high=None, low=None):
    return Candle(
        symbol=symbol,
        timestamp=datetime(2024, 1, 15, h, m, tzinfo=IST),
        open=price,
        high=high or price + 5,
        low=low or price - 5,
        close=price,
        volume=10000,
    )


def test_orb_no_signal_before_range_established():
    strat = OpeningRangeBreakoutStrategy()
    c = _candle("RELIANCE", 9, 35, 2800)
    sig = strat.evaluate(c, relative_volume=2.5, atr=50.0,
                         market_direction="UP", sector_direction="UP")
    assert sig.action == "HOLD"
    assert "Opening range not yet established" in sig.reason


def test_orb_buy_signal_above_or():
    strat = OpeningRangeBreakoutStrategy()
    # Build opening range 9:15–9:30 → OR = 2790–2810
    for m in range(15, 30, 5):
        strat.observe_opening(_candle("RELIANCE", 9, m, 2800, high=2810, low=2790))

    # 9:35 candle closes above OR high
    breakout = _candle("RELIANCE", 9, 35, 2815, high=2820, low=2800)
    sig = strat.evaluate(breakout, relative_volume=2.5, atr=50.0,
                         market_direction="UP", sector_direction="UP")
    assert sig.action == "BUY"
    assert sig.stop_loss is not None and sig.stop_loss < 2815
    assert sig.target is not None and sig.target > 2815


def test_orb_short_signal_below_or():
    strat = OpeningRangeBreakoutStrategy()
    for m in range(15, 30, 5):
        strat.observe_opening(_candle("NIFTY", 9, m, 21000, high=21050, low=20950))

    breakdown = _candle("NIFTY", 9, 35, 20940, high=20960, low=20930)
    sig = strat.evaluate(breakdown, relative_volume=2.0, atr=200.0,
                         market_direction="DOWN", sector_direction="DOWN")
    assert sig.action == "SHORT"
    assert sig.stop_loss > 20940


def test_orb_inside_range_is_hold():
    strat = OpeningRangeBreakoutStrategy()
    for m in range(15, 30, 5):
        strat.observe_opening(_candle("TCS", 9, m, 3600, high=3620, low=3580))

    inside = _candle("TCS", 9, 35, 3600)
    sig = strat.evaluate(inside, relative_volume=2.5, atr=80.0,
                         market_direction="UP", sector_direction="UP")
    assert sig.action == "HOLD"
    assert "inside opening range" in sig.reason.lower()


def test_orb_low_rvol_rejected():
    strat = OpeningRangeBreakoutStrategy()
    for m in range(15, 30, 5):
        strat.observe_opening(_candle("WIPRO", 9, m, 450, high=455, low=445))
    breakout = _candle("WIPRO", 9, 35, 458)
    sig = strat.evaluate(breakout, relative_volume=0.8, atr=10.0,
                         market_direction="UP", sector_direction="UP")
    assert sig.action == "HOLD"
    assert "RVOL" in sig.reason


def test_orb_past_cutoff_rejected():
    strat = OpeningRangeBreakoutStrategy()
    for m in range(15, 30, 5):
        strat.observe_opening(_candle("HDFCBANK", 9, m, 1600, high=1620, low=1580))
    late = Candle("HDFCBANK", datetime(2024, 1, 15, 14, 5, tzinfo=IST),
                  1650, 1660, 1640, 1650, 10000)
    sig = strat.evaluate(late, relative_volume=3.0, atr=40.0,
                         market_direction="UP", sector_direction="UP")
    assert sig.action == "HOLD"
    assert "14:00" in sig.reason
