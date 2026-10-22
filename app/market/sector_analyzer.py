from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.market.candles import CandleBuilder
from app.market.indicators import intraday_vwap_price, percent_change

IST = ZoneInfo("Asia/Kolkata")
log = logging.getLogger(__name__)
_SECTOR_MAP_PATH = Path(__file__).resolve().parents[2] / "data" / "sector_map.json"


@dataclass
class SectorState:
    name: str
    index_symbol: str
    price: float = 0.0
    prev_close: float = 0.0
    vwap: float = 0.0
    change_pct: float = 0.0
    vs_vwap_pct: float = 0.0
    relative_strength: float = 0.0   # vs Nifty 50
    score: float = 0.0
    rank: int = 0
    updated_at: datetime | None = None


class SectorAnalyzer:
    """
    Tracks sector indices and ranks them by intraday strength.
    Returns top 2 strong (for BULLISH) or weak (for BEARISH) sectors.
    """

    def __init__(self):
        self._sectors: dict[str, SectorState] = {}
        self._builders: dict[str, CandleBuilder] = {}
        self._intraday_candles: dict[str, list[dict]] = {}
        self._map: dict = self._load_map()

    # ------------------------------------------------------------------
    def _load_map(self) -> dict:
        if _SECTOR_MAP_PATH.exists():
            return json.loads(_SECTOR_MAP_PATH.read_text())
        return {}

    def initialize(self) -> None:
        """Set up state objects for all sectors in the map."""
        for sector_name, info in self._map.items():
            sym = info.get("index_symbol", "")
            self._sectors[sector_name] = SectorState(name=sector_name, index_symbol=sym)
            self._builders[sector_name] = CandleBuilder(sym)
            self._intraday_candles[sector_name] = []

    def set_prev_close(self, sector_name: str, price: float) -> None:
        if sector_name in self._sectors:
            self._sectors[sector_name].prev_close = price

    def on_tick(self, index_symbol: str, price: float, volume: int, ts: datetime) -> None:
        """Feed a tick; find which sector owns this index_symbol."""
        sector_name = self._symbol_to_sector(index_symbol)
        if not sector_name:
            return
        completed = self._builders[sector_name].on_tick(price, volume, ts)
        if completed:
            self._intraday_candles[sector_name].append({
                "high": completed.high, "low": completed.low,
                "close": completed.close, "volume": completed.volume,
            })
        self._update_sector(sector_name, price)

    def _update_sector(self, name: str, price: float) -> None:
        s = self._sectors[name]
        s.price = price
        vwap = intraday_vwap_price(self._intraday_candles[name])
        s.vwap = vwap or 0.0
        s.change_pct = percent_change(price, s.prev_close) or 0.0
        if vwap and vwap > 0:
            s.vs_vwap_pct = (price - vwap) / vwap * 100
        s.updated_at = datetime.now(IST)

    def compute_rankings(self, market_change_pct: float) -> None:
        """Compute relative strength and rank all sectors."""
        for s in self._sectors.values():
            s.relative_strength = s.change_pct - market_change_pct
            s.score = s.change_pct * 0.4 + s.relative_strength * 0.4 + s.vs_vwap_pct * 0.2

        ranked = sorted(self._sectors.values(), key=lambda x: x.score, reverse=True)
        for i, s in enumerate(ranked):
            s.rank = i + 1

    def top_sectors(self, direction: str, n: int = 2) -> list[str]:
        """Return top N sector names matching market direction."""
        if direction == "BULLISH":
            ranked = sorted(self._sectors.values(), key=lambda x: x.score, reverse=True)
            return [s.name for s in ranked[:n] if s.score > 0]
        elif direction == "BEARISH":
            ranked = sorted(self._sectors.values(), key=lambda x: x.score)
            return [s.name for s in ranked[:n] if s.score < 0]
        return []

    def all_states(self) -> list[SectorState]:
        return sorted(self._sectors.values(), key=lambda x: x.score, reverse=True)

    def get_stocks_in_sectors(self, sectors: list[str]) -> set[str]:
        stocks: set[str] = set()
        for sector in sectors:
            info = self._map.get(sector, {})
            stocks.update(info.get("stocks", []))
        return stocks

    def sector_for_stock(self, symbol: str) -> str:
        for sector_name, info in self._map.items():
            if symbol in info.get("stocks", []):
                return sector_name
        return ""

    def all_index_symbols(self) -> list[str]:
        return [info.get("index_symbol", "") for info in self._map.values() if info.get("index_symbol")]

    def _symbol_to_sector(self, index_symbol: str) -> str | None:
        for name, info in self._map.items():
            if info.get("index_symbol") == index_symbol:
                return name
        return None
