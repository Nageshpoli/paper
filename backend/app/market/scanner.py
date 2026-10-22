from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import MarketCandle, ScannerState, StrategySignal, UniverseConstituent
from app.market.indicators import atr, market_direction, relative_volume
from app.strategies.base import Signal

IST = ZoneInfo("Asia/Kolkata")
NIFTY50 = "IDX:NIFTY 50"


@dataclass
class Quote:
    last: float
    bid: float | None
    ask: float | None
    timestamp: datetime
    received_at: datetime | None = None


@dataclass
class PendingEntry:
    signal: Signal
    threshold: float
    atr: float
    queued_at: datetime


class CandidateScanner:
    def __init__(self):
        self.settings = get_settings()
        self._load_strategy()

    def _load_strategy(self) -> None:
        from app.strategies.registry import strategy_registry
        self.strategy = strategy_registry.get("orb_v1")

    def evaluate(self, db: Session, candle: MarketCandle,
                 quotes: dict[str, Quote]) -> tuple[Signal | None, float | None]:
        from app.strategies.orb.strategy import candle_to_value
        from app.db.models import ScannerState
        symbol = candle.symbol
        now = candle.timestamp.replace(tzinfo=IST)
        self.strategy.observe_opening(candle_to_value(candle))
        member = db.get(UniverseConstituent, symbol)
        reject = market_side = sector_side = rv = None
        daily_bars = five_bars = []
        threshold = score = 0.0

        if member is None:
            reject = "Outside validated Nifty 500 universe"
        else:
            five_bars = db.query(MarketCandle).filter(
                MarketCandle.symbol == symbol, MarketCandle.interval == "5minute"
            ).order_by(MarketCandle.timestamp).all()
            daily_bars = db.query(MarketCandle).filter(
                MarketCandle.symbol == symbol, MarketCandle.interval == "day"
            ).order_by(MarketCandle.timestamp).all()
            rv = relative_volume(five_bars, candle)
            daily_atr = atr(daily_bars)
            liquidity = (median([b.close * b.volume for b in daily_bars[-20:]])
                         if len(daily_bars) >= 20 else None)
            if daily_atr is None:
                reject = "Daily ATR(14) unavailable"
            elif rv is None:
                reject = "20-session RVOL baseline unavailable"
            elif liquidity is None:
                reject = "20-session median traded-value history unavailable"
            elif self.settings.minimum_median_traded_value <= 0:
                reject = "minimum_median_traded_value not calibrated in settings"
            elif liquidity < self.settings.minimum_median_traded_value:
                reject = "Median traded value below minimum"

            if not reject:
                market_bars = self._recent_index(db, NIFTY50, candle.timestamp)
                if not market_bars or not self._fresh_index(NIFTY50, quotes, now):
                    reject = "Nifty 50 data missing or stale"
                else:
                    market_side = market_direction(market_bars, market_bars[-1].close)
                    if market_side in (None, "NEUTRAL"):
                        reject = "Nifty 50 context neutral"

            if not reject:
                if not member.sector_index:
                    reject = "No sector-index mapping for this constituent"
                else:
                    sector_sym = "IDX:" + member.sector_index
                    sector_bars = self._recent_index(db, sector_sym, candle.timestamp)
                    if not sector_bars or not self._fresh_index(sector_sym, quotes, now):
                        reject = "Sector-index data missing or stale"
                    else:
                        sector_side = market_direction(sector_bars, sector_bars[-1].close)
                        if sector_side in (None, "NEUTRAL"):
                            reject = "Sector context neutral"

            if not reject:
                quote = quotes.get(symbol)
                if not quote or (now - quote.timestamp.astimezone(IST)).total_seconds() > 30:
                    reject = "Stock quote is stale"
                elif quote.bid is None or quote.ask is None or quote.bid <= 0 or quote.ask < quote.bid:
                    reject = "Valid bid/ask spread unavailable"
                elif self.settings.maximum_spread_bps <= 0:
                    reject = "maximum_spread_bps not calibrated in settings"
                elif ((quote.ask - quote.bid) / quote.last * 10000) > self.settings.maximum_spread_bps:
                    reject = "Bid/ask spread exceeds limit"

            signal = None
            if not reject:
                from app.strategies.orb.strategy import candle_to_value as cv
                signal = self.strategy.evaluate(cv(candle), relative_volume=rv,
                    atr=daily_atr, market_direction=market_side, sector_direction=sector_side,
                    tick_size=member.tick_size)
                if signal.action == "HOLD":
                    reject = signal.reason
                else:
                    score = (min(30, (rv or 0) * 10) + 25 + 25
                             + min(20, abs(candle.close - (signal.stop_loss or candle.close)) / daily_atr * 10))
                    opened = self.strategy.opening.get(symbol, [])
                    if opened:
                        orh = max(x.high for x in opened)
                        orl = min(x.low for x in opened)
                        threshold = (orh + max(.05 * daily_atr, member.tick_size) if signal.action == "BUY"
                                     else orl - max(.05 * daily_atr, member.tick_size))

            self._save_state(db, symbol, candle, rv, market_side, sector_side, score,
                             "SIGNAL" if signal and signal.action != "HOLD" else "REJECTED",
                             reject or (signal.reason if signal else ""), signal)
            if signal and signal.action != "HOLD":
                from app.db.models import StrategySignal
                from app.config import get_settings as gs
                if not db.query(StrategySignal.id).filter_by(signal_key=signal.signal_id).first():
                    db.add(StrategySignal(symbol=symbol, action=signal.action, strategy=signal.strategy,
                        confidence=score / 100, reason=signal.reason, price=signal.price,
                        signal_key=signal.signal_id))
                    db.commit()
                return signal, threshold
            return None, threshold

        self._save_state(db, symbol, candle, rv, market_side, sector_side, score, "REJECTED", reject, None)
        return None, None

    @staticmethod
    def _recent_index(db: Session, symbol: str, when: datetime) -> list[MarketCandle]:
        bars = db.query(MarketCandle).filter(
            MarketCandle.symbol == symbol, MarketCandle.interval == "5minute",
            MarketCandle.timestamp <= when
        ).order_by(MarketCandle.timestamp.desc()).limit(100).all()
        bars.reverse()
        if not bars or when.replace(tzinfo=None) - bars[-1].timestamp > timedelta(minutes=5):
            return []
        return bars

    @staticmethod
    def _fresh_index(symbol: str, quotes: dict[str, Quote], now: datetime) -> bool:
        q = quotes.get(symbol)
        return bool(q and (now - q.timestamp.astimezone(IST)).total_seconds() <= 30)

    @staticmethod
    def _save_state(db: Session, symbol, candle, rv, market_side, sector_side,
                    score, status, reason, signal) -> None:
        row = db.get(ScannerState, symbol)
        if row is None:
            row = ScannerState(symbol=symbol, timestamp=candle.timestamp)
            db.add(row)
        from app.strategies.registry import strategy_registry
        strat = strategy_registry.get("orb_v1")
        opened = strat.opening.get(symbol, []) if strat else []
        row.timestamp = candle.timestamp
        row.price = candle.close
        prev_daily = db.query(MarketCandle).filter(
            MarketCandle.symbol == symbol, MarketCandle.interval == "day",
            MarketCandle.timestamp < candle.timestamp
        ).order_by(MarketCandle.timestamp.desc()).first()
        row.change_pct = ((candle.close - prev_daily.close) / prev_daily.close * 100
                          if prev_daily and prev_daily.close else None)
        row.or_high = max((x.high for x in opened), default=None)
        row.or_low = min((x.low for x in opened), default=None)
        row.relative_volume = rv
        row.market_direction = market_side
        row.sector_direction = sector_side
        row.score = score
        row.status = status
        row.reason = reason or "Qualified ORB signal"
        db.commit()
