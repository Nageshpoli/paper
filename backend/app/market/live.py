from __future__ import annotations

from datetime import datetime, timedelta
from threading import Lock
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.db.models import MarketCandle, ScannerState, StrategySignal, UniverseConstituent
from app.db.session import SessionLocal
from app.engine.runner import engine
from app.market.candles import Candle, FiveMinuteBuilder
from app.market.scanner import CandidateScanner, PendingEntry, Quote
from app.strategies.base import MarketSnapshot, Signal

IST = ZoneInfo("Asia/Kolkata")
MAX_ENTRY_GAP_ATR = 0.25
MAX_STOP_DISTANCE_ATR = 1.5
active_market_feed = None


class LiveMarketFeed:
    def __init__(self, token_to_symbol: dict[int, str]):
        global active_market_feed
        self.token_to_symbol = token_to_symbol
        self.builder = FiveMinuteBuilder()
        self.scanner = CandidateScanner()
        self.quotes: dict[str, Quote] = {}
        self.pending: dict[str, PendingEntry] = {}
        self.lock = Lock()
        self._restore_opening_range()
        active_market_feed = self

    def _restore_opening_range(self) -> None:
        from app.strategies.orb.strategy import candle_to_value
        now = datetime.now(IST)
        db = SessionLocal()
        try:
            members = [row.symbol for row in db.query(UniverseConstituent.symbol).all()]
            for symbol in members:
                bars = db.query(MarketCandle).filter(
                    MarketCandle.symbol == symbol, MarketCandle.interval == "5minute",
                    MarketCandle.timestamp >= now.date().isoformat() + " 09:15:00",
                    MarketCandle.timestamp < now.date().isoformat() + " 09:30:00",
                ).order_by(MarketCandle.timestamp).all()
                for bar in bars[:3]:
                    self.scanner.strategy.observe_opening(
                        Candle(bar.symbol, bar.timestamp.replace(tzinfo=IST),
                               bar.open, bar.high, bar.low, bar.close, bar.volume))
        finally:
            db.close()

    def on_tick(self, tick: dict) -> None:
        symbol = self.token_to_symbol.get(tick.get("instrument_token"))
        stamp = tick.get("exchange_timestamp") or tick.get("last_trade_time")
        price = tick.get("last_price")
        if not symbol or not isinstance(stamp, datetime) or not isinstance(price, (int, float)) or price <= 0:
            return
        if stamp.tzinfo is None:
            return
        bid, ask = self._best_prices(tick)
        received_at = datetime.now(IST)
        quote = Quote(float(price), bid, ask, stamp, received_at)
        engine.state.last_tick_at = stamp
        volume = tick.get("volume_traded")
        last_quantity = int(tick.get("last_quantity") or 0)
        with self.lock:
            self.quotes[symbol] = quote
            complete = self.builder.add_tick(symbol, float(price), stamp, volume, last_quantity)
            quotes = dict(self.quotes)
        self._try_pending(symbol, quote)
        db = SessionLocal()
        try:
            if not symbol.startswith("IDX:"):
                position = engine.broker.get_position(db, symbol)
                if position:
                    executable = bid if position.side == "LONG" else ask
                    if executable and executable > 0:
                        engine.update_open_positions(db, MarketSnapshot(symbol=symbol, last_price=executable))
                    else:
                        position.last_price = float(price)
                        db.commit()
            if complete:
                persisted = self._persist_candle(db, complete)
                if persisted and not symbol.startswith("IDX:"):
                    signal, threshold = self.scanner.evaluate(db, persisted, quotes)
                    if signal and threshold is not None:
                        state = db.get(ScannerState, symbol)
                        if state:
                            state.status = "PENDING_FILL"
                            state.reason = "Qualified on completed candle; awaiting next valid quote"
                        self.pending[symbol] = PendingEntry(signal, threshold, self._atr_for(db, symbol), received_at)
                        db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _best_prices(tick: dict) -> tuple[float | None, float | None]:
        depth = tick.get("depth") or {}
        buys = depth.get("buy") or []
        sells = depth.get("sell") or []
        bid = float(buys[0]["price"]) if buys and buys[0].get("price") else None
        ask = float(sells[0]["price"]) if sells and sells[0].get("price") else None
        return bid, ask

    @staticmethod
    def _persist_candle(db, candle: Candle) -> MarketCandle | None:
        stamp = candle.timestamp.replace(tzinfo=None)
        existing = db.query(MarketCandle).filter_by(symbol=candle.symbol, timestamp=stamp, interval="5minute").first()
        if existing:
            return existing
        row = MarketCandle(symbol=candle.symbol, timestamp=stamp, interval="5minute",
            open=candle.open, high=candle.high, low=candle.low, close=candle.close, volume=candle.volume)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def _atr_for(db, symbol: str) -> float:
        from app.market.indicators import atr
        bars = db.query(MarketCandle).filter_by(symbol=symbol, interval="day").order_by(MarketCandle.timestamp).all()
        return atr(bars) or 0.0

    def _try_pending(self, symbol: str, quote: Quote) -> None:
        pending = self.pending.get(symbol)
        if not pending:
            return
        received = quote.received_at or quote.timestamp
        if received <= pending.queued_at:
            return
        signal = pending.signal
        if (received - pending.queued_at).total_seconds() > 30:
            self._finish_pending(symbol, pending, "No valid quote within 30 s of confirmation", None)
            return
        if signal.action == "BUY":
            fill = quote.ask
            still_breaking = fill is not None and fill >= pending.threshold
            gap = fill - pending.threshold if fill is not None else None
        else:
            fill = quote.bid
            still_breaking = fill is not None and fill <= pending.threshold
            gap = pending.threshold - fill if fill is not None else None
        if fill is None or not still_breaking:
            self._finish_pending(symbol, pending, "Next quote did not retain the breakout", None)
            return
        if gap > MAX_ENTRY_GAP_ATR * pending.atr:
            self._finish_pending(symbol, pending, "Next quote gapped more than 0.25 ATR beyond breakout", None)
            return
        risk = abs(fill - (signal.stop_loss or fill))
        if risk <= 0 or risk > MAX_STOP_DISTANCE_ATR * pending.atr:
            self._finish_pending(symbol, pending, "Fill-to-stop distance exceeds ATR limit", None)
            return
        target = fill + (2 * risk if signal.action == "BUY" else -2 * risk)
        filled = Signal(signal.action, signal.symbol, signal.strategy, fill, signal.confidence,
                        signal.reason, signal.stop_loss, target, signal.signal_id)
        db = SessionLocal()
        try:
            success = engine.execute_signal(db, filled)
            self._finish_pending(symbol, pending,
                "Paper entry filled at next executable quote" if success else "Risk manager rejected entry", success)
        finally:
            db.close()

    def _finish_pending(self, symbol: str, pending: PendingEntry, reason: str, filled: bool | None) -> None:
        db = SessionLocal()
        try:
            sig_row = db.query(StrategySignal).filter_by(signal_key=pending.signal.signal_id).first()
            if sig_row and filled is None:
                sig_row.execution_status = "REJECTED"
                sig_row.execution_reason = reason
            state = db.get(ScannerState, symbol)
            if state:
                state.status = "PAPER_OPEN" if filled else "REJECTED"
                state.reason = reason
            db.commit()
        finally:
            db.close()
        self.pending.pop(symbol, None)
