from __future__ import annotations

import time
from datetime import datetime, timedelta
from threading import Lock, Thread
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import MarketCandle, SystemEvent
from app.db.session import SessionLocal
from app.kite.client import KiteClientFactory

IST = ZoneInfo("Asia/Kolkata")


class HistoryWarmup:
    """Bounded, restartable Kite historical cache fill executed off the API thread."""
    def __init__(self, delay_seconds: float = 0.4):
        self.delay_seconds = max(0.3, delay_seconds)
        self.lock = Lock()
        self.state: dict = {"running": False, "completed": 0, "total": 0,
                            "errors": [], "started_at": None, "finished_at": None}

    def start(self, access_db: Session, instruments: list[dict]) -> dict:
        with self.lock:
            if self.state["running"]:
                return dict(self.state)
            token_map = {int(i["instrument_token"]): i.get("history_symbol", i["tradingsymbol"])
                         for i in instruments}
            token = KiteClientFactory().auth.get_access_token(access_db)
            if not token:
                raise ValueError("Kite token missing")
            now = datetime.now(IST).replace(second=0, microsecond=0)
            stale_before = now - timedelta(days=7)
            db = SessionLocal()
            tasks = []
            try:
                for tok, symbol in token_map.items():
                    for interval, begin, min_count in (
                        ("5minute", now - timedelta(days=45), 1200),
                        ("day",     now - timedelta(days=45), 15),
                    ):
                        count, newest = db.query(
                            func.count(MarketCandle.id), func.max(MarketCandle.timestamp)
                        ).filter(MarketCandle.symbol == symbol, MarketCandle.interval == interval).one()
                        if count < min_count or newest is None or newest < stale_before.replace(tzinfo=None):
                            tasks.append((tok, symbol, interval, begin))
            finally:
                db.close()
            api_key = KiteClientFactory().auth.settings.kite_api_key
            self.state = {"running": True, "completed": 0, "total": len(tasks), "errors": [],
                          "started_at": datetime.now(IST).isoformat(), "finished_at": None}
            if not tasks:
                self.state["running"] = False
                self.state["finished_at"] = datetime.now(IST).isoformat()
                return dict(self.state)
            Thread(target=self._run, args=(api_key, token, tasks, now),
                   daemon=True, name="kite-history-warmup").start()
            return dict(self.state)

    def _run(self, api_key: str, access_token: str, tasks: list, to_dt: datetime) -> None:
        from kiteconnect import KiteConnect
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)
        try:
            for tok, symbol, interval, begin in tasks:
                try:
                    rows = self._fetch(kite, tok, begin, to_dt, interval)
                    self._persist(symbol, rows, interval, to_dt)
                except Exception as exc:
                    with self.lock:
                        self.state["errors"].append({"symbol": symbol, "interval": interval,
                                                     "error": str(exc)[:240]})
                finally:
                    with self.lock:
                        self.state["completed"] += 1
                    time.sleep(self.delay_seconds)
        finally:
            db = SessionLocal()
            try:
                db.add(SystemEvent(category="history", level="INFO",
                    message=f"History warmup finished: {self.state['completed']}/{self.state['total']}"))
                db.commit()
            finally:
                db.close()
            with self.lock:
                self.state["running"] = False
                self.state["finished_at"] = datetime.now(IST).isoformat()

    @staticmethod
    def _fetch(kite, token: int, start: datetime, end: datetime, interval: str) -> list:
        last_err = None
        for attempt in range(4):
            try:
                return kite.historical_data(token, start, end, interval, continuous=False, oi=False)
            except Exception as exc:
                last_err = exc
                if attempt < 3:
                    time.sleep(min(8, 0.5 * (2 ** attempt)))
        raise RuntimeError(f"Historical request failed after retries: {last_err}")

    def _persist(self, symbol: str, rows: list[dict], interval: str, as_of: datetime) -> None:
        db = SessionLocal()
        try:
            for row in rows:
                stamp = row["date"]
                if stamp.tzinfo is not None:
                    stamp = stamp.astimezone(IST).replace(tzinfo=None)
                if interval == "day" and stamp.date() >= as_of.date():
                    continue
                if interval == "5minute" and stamp + timedelta(minutes=5) > as_of.replace(tzinfo=None):
                    continue
                exists = db.query(MarketCandle.id).filter_by(
                    symbol=symbol, timestamp=stamp, interval=interval).first()
                if exists:
                    continue
                db.add(MarketCandle(symbol=symbol, timestamp=stamp, interval=interval,
                    open=row["open"], high=row["high"], low=row["low"],
                    close=row["close"], volume=row["volume"]))
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


history_warmup = HistoryWarmup()
