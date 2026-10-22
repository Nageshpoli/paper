from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo

from app.config import get_settings

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class ORBSignal:
    symbol: str
    sector: str
    action: str          # BUY / SHORT
    signal_price: float
    or_high: float
    or_low: float
    vwap: float
    rvol: float | None
    stop_loss: float
    target: float
    risk_reward: float
    reason: str = "ORB breakout confirmed"


def evaluate_orb(
    scan: dict,
    market_direction: str,
    active_sectors: list[str],
) -> ORBSignal | tuple[None, str]:
    """
    Evaluate one completed candle against ORB conditions.

    Returns (ORBSignal, reason) on a valid signal,
    or (None, rejection_reason) if conditions are not met.
    """
    cfg = get_settings()
    symbol: str = scan["symbol"]
    sector: str = scan["sector"]
    price: float = scan["price"]
    or_high = scan.get("or_high")
    or_low = scan.get("or_low")
    or_complete: bool = scan.get("or_complete", False)
    vwap = scan.get("vwap")
    rvol = scan.get("rvol")
    candle_time: time = scan.get("candle_time", time(0, 0))

    # ── Pre-checks ────────────────────────────────────────────────────
    if market_direction == "NEUTRAL":
        return None, "Market NEUTRAL — no trades"

    if not or_complete or or_high is None or or_low is None:
        return None, "Opening range not yet complete"

    entry_cutoff = _parse_time(cfg.entry_cutoff_time)
    if candle_time >= entry_cutoff:
        return None, f"After entry cutoff {cfg.entry_cutoff_time}"

    if sector not in active_sectors:
        return None, f"Sector {sector!r} not in active list"

    if vwap is None or vwap == 0:
        return None, "VWAP unavailable"

    if rvol is not None and rvol < cfg.rvol_min:
        return None, f"RVOL {rvol:.2f} < {cfg.rvol_min}"

    buf = or_high * cfg.breakout_buffer_pct

    # ── Long signal ───────────────────────────────────────────────────
    if market_direction == "BULLISH":
        if price <= vwap:
            return None, f"Price {price:.2f} below VWAP {vwap:.2f}"
        if price < or_high + buf:
            return None, f"No upside breakout (need >{or_high + buf:.2f})"
        stop = or_low
        risk = price - stop
        if risk <= 0:
            return None, "Invalid stop distance (risk ≤ 0)"
        target = price + risk * cfg.reward_to_risk
        rr = (target - price) / risk
        return ORBSignal(
            symbol=symbol, sector=sector, action="BUY",
            signal_price=price, or_high=or_high, or_low=or_low,
            vwap=vwap, rvol=rvol,
            stop_loss=stop, target=target, risk_reward=rr,
        ), "ORB long breakout"

    # ── Short signal ──────────────────────────────────────────────────
    if market_direction == "BEARISH":
        if price >= vwap:
            return None, f"Price {price:.2f} above VWAP {vwap:.2f}"
        if price > or_low - buf:
            return None, f"No downside breakout (need <{or_low - buf:.2f})"
        stop = or_high
        risk = stop - price
        if risk <= 0:
            return None, "Invalid stop distance (risk ≤ 0)"
        target = price - risk * cfg.reward_to_risk
        rr = (price - target) / risk
        return ORBSignal(
            symbol=symbol, sector=sector, action="SHORT",
            signal_price=price, or_high=or_high, or_low=or_low,
            vwap=vwap, rvol=rvol,
            stop_loss=stop, target=target, risk_reward=rr,
        ), "ORB short breakout"

    return None, "No breakout in this candle"


def _parse_time(t: str) -> time:
    h, m = t.split(":")
    return time(int(h), int(m))
