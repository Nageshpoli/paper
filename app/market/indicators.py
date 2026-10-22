from __future__ import annotations

import pandas as pd
import numpy as np


def vwap(df: pd.DataFrame) -> pd.Series:
    """
    Calculate VWAP from a candles DataFrame with columns: high, low, close, volume.
    Returns cumulative VWAP series.
    """
    typical = (df["high"] + df["low"] + df["close"]) / 3
    cumvol = df["volume"].cumsum()
    cumtp = (typical * df["volume"]).cumsum()
    return (cumtp / cumvol.replace(0, np.nan)).fillna(method="ffill")


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range over daily candles."""
    h = df["high"]
    l = df["low"]
    pc = df["close"].shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def relative_volume(current_volume: int, hist_volumes: list[int]) -> float | None:
    """
    RVOL = current candle volume / average volume of same 5-min slot across history.
    Returns None if insufficient history.
    """
    if not hist_volumes or len(hist_volumes) < 5:
        return None
    avg = float(np.mean(hist_volumes))
    if avg <= 0:
        return None
    return current_volume / avg


def intraday_vwap_price(candles: list[dict]) -> float | None:
    """
    Calculate VWAP from a list of intraday candle dicts:
    each dict must have high, low, close, volume keys.
    """
    if not candles:
        return None
    total_vol = 0
    total_tp_vol = 0.0
    for c in candles:
        vol = c.get("volume", 0)
        tp = (c["high"] + c["low"] + c["close"]) / 3
        total_tp_vol += tp * vol
        total_vol += vol
    if total_vol == 0:
        return None
    return total_tp_vol / total_vol


def percent_change(current: float, reference: float) -> float | None:
    if reference is None or reference == 0:
        return None
    return (current - reference) / reference * 100
