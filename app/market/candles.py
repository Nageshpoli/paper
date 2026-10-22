from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class Candle:
    symbol: str
    timestamp: datetime   # candle start (5-min slot)
    open: float
    high: float
    low: float
    close: float
    volume: int
    is_complete: bool = False


class CandleBuilder:
    """Accumulate live ticks into 5-minute candles (IST-aligned)."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self._current: Candle | None = None
        self._completed: list[Candle] = []

    # ------------------------------------------------------------------
    def on_tick(self, price: float, volume: int, ts: datetime) -> Candle | None:
        """
        Feed a tick. Returns the just-completed candle when a new 5-min
        slot starts, else None.
        """
        slot = _slot(ts)
        if self._current is None:
            self._current = Candle(self.symbol, slot, price, price, price, price, volume)
            return None

        if self._current.timestamp == slot:
            c = self._current
            c.high = max(c.high, price)
            c.low = min(c.low, price)
            c.close = price
            c.volume += volume
            return None

        # Slot changed → current candle is complete
        self._current.is_complete = True
        completed = self._current
        self._completed.append(completed)
        self._current = Candle(self.symbol, slot, price, price, price, price, volume)
        return completed

    def current(self) -> Candle | None:
        return self._current

    def last_n(self, n: int) -> list[Candle]:
        return self._completed[-n:]

    def all_completed(self) -> list[Candle]:
        return list(self._completed)


def _slot(ts: datetime) -> datetime:
    """Round down to 5-minute boundary in IST."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=IST)
    ts = ts.astimezone(IST)
    minute = (ts.minute // 5) * 5
    return ts.replace(minute=minute, second=0, microsecond=0, tzinfo=None)
