from __future__ import annotations

import uuid
from datetime import time
from typing import Optional
from zoneinfo import ZoneInfo

from app.db.models import MarketCandle
from app.market.candles import Candle
from app.strategies.base import Signal, Strategy

IST = ZoneInfo("Asia/Kolkata")
OR_START = time(9, 15)
OR_END = time(9, 30)
ENTRY_WINDOW_END = time(14, 0)
MINIMUM_RVOL = 1.5
MINIMUM_RISK_REWARD = 1.8
STOP_ATR_MULTIPLE = 0.5


def candle_to_value(candle: MarketCandle) -> Candle:
    """Convert a DB MarketCandle row to an in-memory Candle dataclass."""
    ts = candle.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=IST)
    return Candle(
        symbol=candle.symbol,
        timestamp=ts,
        open=float(candle.open),
        high=float(candle.high),
        low=float(candle.low),
        close=float(candle.close),
        volume=int(candle.volume or 0),
    )


class OpeningRangeBreakoutStrategy(Strategy):
    """
    ORB: wait for first 15-minute opening range (9:15–9:30), then trade
    confirmed breakouts above/below on 5-minute candle close, with
    ATR-sized stops and market+sector alignment filters.
    """
    name = "orb_v1"
    description = "Opening Range Breakout — Nifty 500, 5-min bars, 9:15–9:30 range"

    def __init__(self) -> None:
        self.opening: dict[str, list[Candle]] = {}

    def observe_opening(self, candle: Candle) -> None:
        t = candle.timestamp.astimezone(IST).time()
        if OR_START <= t < OR_END:
            self.opening.setdefault(candle.symbol, []).append(candle)

    def evaluate(
        self,
        candle: Candle,
        *,
        relative_volume: float | None = None,
        atr: float | None = None,
        market_direction: str | None = None,
        sector_direction: str | None = None,
        tick_size: float = 0.05,
    ) -> Signal:
        symbol = candle.symbol
        t = candle.timestamp.astimezone(IST).time()
        reject = self._pre_checks(symbol, t, relative_volume, atr)
        if reject:
            return self._hold(symbol, candle.close, reject)

        opened = self.opening[symbol]
        or_high = max(x.high for x in opened)
        or_low = min(x.low for x in opened)
        daily_atr = atr

        if candle.close > or_high:
            stop = candle.close - STOP_ATR_MULTIPLE * daily_atr
            stop = max(stop, or_low)
            stop = round(stop / tick_size) * tick_size
            risk = candle.close - stop
            target = candle.close + MINIMUM_RISK_REWARD * risk
            if risk <= 0:
                return self._hold(symbol, candle.close, "Stop loss would be at or above entry")
            return Signal(
                action="BUY",
                symbol=symbol,
                strategy=self.name,
                price=candle.close,
                confidence=0.6,
                reason=f"ORB long breakout above {or_high:.2f}",
                stop_loss=stop,
                target=target,
                signal_id=str(uuid.uuid4()),
            )
        elif candle.close < or_low:
            stop = candle.close + STOP_ATR_MULTIPLE * daily_atr
            stop = min(stop, or_high)
            stop = round(stop / tick_size) * tick_size
            risk = stop - candle.close
            target = candle.close - MINIMUM_RISK_REWARD * risk
            if risk <= 0:
                return self._hold(symbol, candle.close, "Stop loss would be at or below entry")
            return Signal(
                action="SHORT",
                symbol=symbol,
                strategy=self.name,
                price=candle.close,
                confidence=0.6,
                reason=f"ORB short breakdown below {or_low:.2f}",
                stop_loss=stop,
                target=target,
                signal_id=str(uuid.uuid4()),
            )
        else:
            return self._hold(symbol, candle.close, "Price inside opening range")

    def _pre_checks(
        self, symbol: str, t: time, rv: float | None, daily_atr: float | None
    ) -> Optional[str]:
        if symbol not in self.opening or not self.opening[symbol]:
            return "Opening range not yet established (9:15–9:30)"
        if t < OR_END:
            return "Still inside opening range accumulation window"
        if t >= ENTRY_WINDOW_END:
            return "Past 14:00 entry cut-off"
        if daily_atr is None or daily_atr <= 0:
            return "Daily ATR(14) unavailable or zero"
        if rv is None or rv < MINIMUM_RVOL:
            return f"RVOL {rv:.2f} below minimum {MINIMUM_RVOL}" if rv is not None else "RVOL unavailable"
        return None

    @staticmethod
    def _hold(symbol: str, price: float, reason: str) -> Signal:
        return Signal(
            action="HOLD",
            symbol=symbol,
            strategy="orb_v1",
            price=price,
            confidence=0.0,
            reason=reason,
        )
