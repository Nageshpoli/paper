from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.market.candles import Candle, FiveMinuteBuilder

IST = ZoneInfo("Asia/Kolkata")


def ts(h, m, s=0):
    return datetime(2024, 1, 15, h, m, s, tzinfo=IST)


def test_builder_emits_completed_candle():
    builder = FiveMinuteBuilder()
    builder.add_tick("TCS", 3600.0, ts(9, 15, 1), 1000, 10)
    builder.add_tick("TCS", 3610.0, ts(9, 15, 30), 1100, 15)
    completed = builder.add_tick("TCS", 3605.0, ts(9, 20, 1), 1200, 5)
    assert completed is not None
    assert completed.symbol == "TCS"
    assert completed.open == 3600.0
    assert completed.high == 3610.0
    assert completed.low == 3600.0
    assert completed.close == 3610.0


def test_builder_no_early_completion():
    builder = FiveMinuteBuilder()
    builder.add_tick("INFY", 1500.0, ts(9, 15, 1), 100, 5)
    result = builder.add_tick("INFY", 1502.0, ts(9, 18, 0), 200, 5)
    assert result is None


def test_builder_ignores_out_of_order():
    builder = FiveMinuteBuilder()
    builder.add_tick("RELIANCE", 2800.0, ts(9, 20, 10), 1000, 5)
    result = builder.add_tick("RELIANCE", 2790.0, ts(9, 20, 5), 900, 5)
    assert result is None


def test_freshness():
    builder = FiveMinuteBuilder()
    now = ts(9, 30, 0)
    builder.add_tick("HDFC", 1600.0, ts(9, 29, 45), 500, 10)
    assert builder.freshness("HDFC", now, max_age_seconds=30) is True
    assert builder.freshness("HDFC", now, max_age_seconds=5) is False
