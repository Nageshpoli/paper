from __future__ import annotations

import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.db.models import MarketCandle, ScannerRow, UniverseConstituent
from app.db.session import SessionLocal
from app.market.candles import Candle, CandleBuilder
from app.market.indicators import intraday_vwap_price, relative_volume

IST = ZoneInfo("Asia/Kolkata")
log = logging.getLogger(__name__)


class StockScanner:
    """
    Per-symbol state machine that builds the Opening Range, computes
    VWAP and RVOL, and emits a scan result on each 5-min candle close.
    """

    def __init__(self, symbol: str, sector: str, prev_close: float,
                 hist_volumes_by_slot: dict[int, list[int]]):
        self.symbol = symbol
        self.sector = sector
        self.prev_close = prev_close
        self._hist_volumes = hist_volumes_by_slot  # {slot_minute: [volumes]}
        self._builder = CandleBuilder(symbol)
        self._intraday_candles: list[dict] = []
        self._or_high: float | None = None
        self._or_low: float | None = None
        self._or_complete = False
        self._last_price: float = 0.0

    # ------------------------------------------------------------------
    def on_tick(self, price: float, volume: int, ts: datetime) -> Candle | None:
        self._last_price = price
        return self._builder.on_tick(price, volume, ts)

    def on_candle_close(self, candle: Candle) -> dict:
        """Process a completed 5-min candle. Returns scan result dict."""
        c = candle
        t = c.timestamp.time() if isinstance(c.timestamp, datetime) else c.timestamp

        self._intraday_candles.append({
            "high": c.high, "low": c.low,
            "close": c.close, "volume": c.volume,
        })

        # Build / extend opening range (9:15–9:30)
        or_start = time(9, 15)
        or_end = time(9, 30)
        if or_start <= t < or_end:
            self._or_high = max(self._or_high or c.high, c.high)
            self._or_low = min(self._or_low or c.low, c.low)
        elif t >= or_end:
            self._or_complete = True

        vwap = intraday_vwap_price(self._intraday_candles)
        slot_minute = c.timestamp.hour * 60 + c.timestamp.minute if isinstance(c.timestamp, datetime) else 0
        hist_vols = self._hist_volumes.get(slot_minute, [])
        rvol = relative_volume(c.volume, hist_vols)

        chg_pct = None
        if self.prev_close and self.prev_close > 0:
            chg_pct = (c.close - self.prev_close) / self.prev_close * 100

        return {
            "symbol": self.symbol,
            "sector": self.sector,
            "price": c.close,
            "change_pct": chg_pct,
            "or_high": self._or_high,
            "or_low": self._or_low,
            "or_complete": self._or_complete,
            "vwap": vwap,
            "rvol": rvol,
            "candle": c,
            "candle_time": t,
        }

    @property
    def or_high(self) -> float | None:
        return self._or_high

    @property
    def or_low(self) -> float | None:
        return self._or_low

    @property
    def or_complete(self) -> bool:
        return self._or_complete


def load_hist_volumes(symbol: str) -> dict[int, list[int]]:
    """
    Load historical 5-min volume grouped by minute-of-day from DB.
    Returns {slot_minute: [list of volumes from past sessions]}.
    """
    db = SessionLocal()
    try:
        rows = db.query(MarketCandle).filter_by(symbol=symbol, interval="5minute").all()
    finally:
        db.close()

    result: dict[int, list[int]] = {}
    seen_dates: dict[int, set] = {}
    for row in rows:
        slot = row.timestamp.hour * 60 + row.timestamp.minute
        date = row.timestamp.date()
        if slot not in result:
            result[slot] = []
            seen_dates[slot] = set()
        if date not in seen_dates[slot]:
            result[slot].append(row.volume)
            seen_dates[slot].add(date)
    return result


def persist_scan_row(row: dict) -> None:
    db = SessionLocal()
    try:
        existing = db.get(ScannerRow, row["symbol"])
        if existing is None:
            existing = ScannerRow(symbol=row["symbol"])
            db.add(existing)
        for k, v in row.items():
            if hasattr(existing, k) and k != "symbol":
                setattr(existing, k, v)
        existing.updated_at = datetime.now(IST)
        db.commit()
    finally:
        db.close()
