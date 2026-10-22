from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class Candle:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class FiveMinuteBuilder:
    """Build exchange-time five-minute candles from Kite ticks. Gaps remain gaps."""
    def __init__(self):
        self.current: dict[str, Candle] = {}
        self.last_tick: dict[str, datetime] = {}
        self.last_cumulative_volume: dict[str, int] = {}

    def add_tick(self, symbol: str, price: float, at: datetime,
                 cumulative_volume: int | None = None,
                 last_quantity: int | None = None) -> Candle | None:
        if at.tzinfo is None or price <= 0:
            return None
        at = at.astimezone(IST)
        previous = self.last_tick.get(symbol)
        if previous and at <= previous:
            return None
        self.last_tick[symbol] = at
        bucket = at.replace(minute=(at.minute // 5) * 5, second=0, microsecond=0)
        last_vol = self.last_cumulative_volume.get(symbol)
        if cumulative_volume is not None:
            delta = max(0, cumulative_volume - last_vol) if last_vol is not None else int(last_quantity or 0)
            self.last_cumulative_volume[symbol] = cumulative_volume
        else:
            delta = int(last_quantity or 0)
        active = self.current.get(symbol)
        completed = None
        if active and active.timestamp != bucket:
            if bucket > active.timestamp:
                completed = active
            active = None
        if active is None:
            self.current[symbol] = Candle(symbol, bucket, price, price, price, price, delta)
        else:
            active.high = max(active.high, price)
            active.low = min(active.low, price)
            active.close = price
            active.volume += delta
        return completed

    def freshness(self, symbol: str, now: datetime, max_age_seconds: int = 30) -> bool:
        last = self.last_tick.get(symbol)
        return bool(last and now.astimezone(IST) - last <= timedelta(seconds=max_age_seconds))
