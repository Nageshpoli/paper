from __future__ import annotations

import pytest

from app.market.candles import CandleBuilder, _slot
from app.market.indicators import relative_volume, intraday_vwap_price, percent_change
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


class TestCandleBuilder:
    def test_no_candle_on_first_tick(self):
        b = CandleBuilder("TEST")
        result = b.on_tick(100.0, 500, datetime(2024, 1, 2, 9, 15, 5, tzinfo=IST))
        assert result is None

    def test_candle_completes_on_new_slot(self):
        b = CandleBuilder("TEST")
        b.on_tick(100.0, 500, datetime(2024, 1, 2, 9, 15, 5, tzinfo=IST))
        b.on_tick(102.0, 300, datetime(2024, 1, 2, 9, 15, 45, tzinfo=IST))
        completed = b.on_tick(105.0, 200, datetime(2024, 1, 2, 9, 20, 5, tzinfo=IST))
        assert completed is not None
        assert completed.high == 102.0
        assert completed.close == 102.0
        assert completed.volume == 800

    def test_slot_rounds_to_5_min(self):
        ts = datetime(2024, 1, 2, 9, 17, 33, tzinfo=IST)
        slot = _slot(ts)
        assert slot.minute == 15
        assert slot.second == 0


class TestIndicators:
    def test_relative_volume_basic(self):
        rv = relative_volume(2000, [1000, 1000, 1000, 1000, 1000])
        assert rv == pytest.approx(2.0)

    def test_relative_volume_none_on_insufficient_history(self):
        rv = relative_volume(500, [1000, 1000])  # only 2 samples
        assert rv is None

    def test_relative_volume_zero_average(self):
        rv = relative_volume(500, [0, 0, 0, 0, 0])
        assert rv is None

    def test_vwap_basic(self):
        candles = [
            {"high": 102, "low": 98, "close": 100, "volume": 1000},
            {"high": 104, "low": 100, "close": 102, "volume": 1000},
        ]
        v = intraday_vwap_price(candles)
        assert v == pytest.approx(101.0)

    def test_percent_change(self):
        assert percent_change(110.0, 100.0) == pytest.approx(10.0)
        assert percent_change(90.0, 100.0) == pytest.approx(-10.0)
        assert percent_change(100.0, 0.0) is None
