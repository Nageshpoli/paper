from __future__ import annotations

from statistics import median
from typing import Iterable

from app.db.models import MarketCandle


def relative_volume(candles: Iterable[MarketCandle], candidate: MarketCandle,
                    sessions: int = 20) -> float | None:
    """Compare a completed candle only with earlier sessions at its exact slot."""
    by_date: dict = {}
    for c in candles:
        if (c.timestamp.date() < candidate.timestamp.date()
                and c.timestamp.time() == candidate.timestamp.time()
                and c.volume > 0):
            by_date[c.timestamp.date()] = c.volume
    values = [by_date[d] for d in sorted(by_date)[-sessions:]]
    if len(values) < sessions or not candidate.volume:
        return None
    baseline = median(values)
    return candidate.volume / baseline if baseline > 0 else None


def atr(daily_candles: list[MarketCandle], period: int = 14) -> float | None:
    bars = sorted(daily_candles, key=lambda c: c.timestamp)
    if len(bars) < period + 1:
        return None
    ranges = []
    for prev, curr in zip(bars[-period - 1:-1], bars[-period:]):
        ranges.append(max(curr.high - curr.low,
                          abs(curr.high - prev.close),
                          abs(curr.low - prev.close)))
    return sum(ranges) / period


def vwap(candles: Iterable[MarketCandle]) -> float | None:
    bars = [b for b in candles if b.volume > 0]
    volume = sum(b.volume for b in bars)
    if not volume:
        return None
    return sum(((b.high + b.low + b.close) / 3) * b.volume for b in bars) / volume


def ema(values: list[float], period: int = 20) -> float | None:
    if len(values) < period:
        return None
    alpha = 2 / (period + 1)
    result = sum(values[:period]) / period
    for v in values[period:]:
        result = v * alpha + result * (1 - alpha)
    return result


def market_direction(candles: list[MarketCandle], now_close: float) -> str | None:
    completed = sorted(candles, key=lambda c: c.timestamp)
    if not completed:
        return None
    current_day = [b for b in completed if b.timestamp.date() == completed[-1].timestamp.date()]
    day_vwap = vwap(current_day)
    moving = ema([b.close for b in completed], 20)
    if day_vwap is None or moving is None:
        return None
    if now_close > day_vwap and now_close > moving:
        return "BULLISH"
    if now_close < day_vwap and now_close < moving:
        return "BEARISH"
    return "NEUTRAL"
