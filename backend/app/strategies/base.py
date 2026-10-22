from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Action = Literal["BUY", "SELL", "SHORT", "HOLD"]


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    last_price: float
    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    volume: Optional[int] = None


@dataclass(frozen=True)
class Signal:
    action: Action
    symbol: str
    strategy: str
    price: float
    confidence: float
    reason: str
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    signal_id: Optional[str] = None


class Strategy:
    """Base class for all strategies. Subclass this and register in registry.py."""
    name: str = "base"

    def observe_opening(self, candle) -> None:
        """Optional hook called on each candle; used by ORB to accumulate the opening range."""

    def evaluate(self, candle, **kwargs) -> Signal:
        raise NotImplementedError
