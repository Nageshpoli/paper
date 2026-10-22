from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from app.market.candles import Candle, CandleBuilder
from app.market.indicators import intraday_vwap_price, percent_change

IST = ZoneInfo("Asia/Kolkata")
log = logging.getLogger(__name__)

NIFTY50_SYMBOL = "NSE:NIFTY 50"
NIFTYBANK_SYMBOL = "NSE:NIFTY BANK"


@dataclass
class MarketState:
    direction: str = "NEUTRAL"   # BULLISH / BEARISH / NEUTRAL
    nifty_price: float = 0.0
    nifty_prev_close: float = 0.0
    nifty_vwap: float = 0.0
    nifty_change_pct: float = 0.0
    nifty_vs_vwap_pct: float = 0.0
    updated_at: datetime | None = None


class MarketAnalyzer:
    """
    Tracks Nifty 50 intraday data and classifies the market as
    BULLISH / BEARISH / NEUTRAL.
    """

    def __init__(self):
        self._builder = CandleBuilder(NIFTY50_SYMBOL)
        self._intraday_candles: list[dict] = []   # raw dicts for VWAP
        self._prev_close: float = 0.0
        self.state = MarketState()

    # ------------------------------------------------------------------
    def set_prev_close(self, price: float) -> None:
        self._prev_close = price

    def on_tick(self, price: float, volume: int, ts: datetime) -> None:
        completed = self._builder.on_tick(price, volume, ts)
        if completed:
            self._intraday_candles.append({
                "high": completed.high, "low": completed.low,
                "close": completed.close, "volume": completed.volume,
            })
        self._update_state(price)

    def _update_state(self, price: float) -> None:
        from app.config import get_settings
        cfg = get_settings()
        vwap = intraday_vwap_price(self._intraday_candles) if self._intraday_candles else None
        chg = percent_change(price, self._prev_close) if self._prev_close else 0.0

        vs_vwap = 0.0
        direction = "NEUTRAL"

        if vwap and vwap > 0:
            vs_vwap = (price - vwap) / vwap * 100
            threshold = cfg.market_vwap_min_gap_pct * 100
            if vs_vwap >= threshold and (chg or 0) >= 0:
                direction = "BULLISH"
            elif vs_vwap <= -threshold and (chg or 0) <= 0:
                direction = "BEARISH"

        self.state = MarketState(
            direction=direction,
            nifty_price=price,
            nifty_prev_close=self._prev_close,
            nifty_vwap=vwap or 0.0,
            nifty_change_pct=chg or 0.0,
            nifty_vs_vwap_pct=vs_vwap,
            updated_at=datetime.now(IST),
        )

    def classify(self) -> str:
        return self.state.direction
