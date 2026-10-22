from __future__ import annotations

import threading
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.db.session import SessionLocal
from app.engine.runner import engine

IST = ZoneInfo("Asia/Kolkata")

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
HISTORY_START = time(9, 0)
ENTRY_CLOSE = time(14, 0)


class NSESession:
    """
    Background thread that manages one NSE trading day.

    Timeline (all IST):
      09:00 — trigger history warmup
      09:15 — open market feed, enable entries
      14:00 — disable new entries
      15:30 — close all positions for EOD, write daily summary
    """

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.quotes: dict = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="nse-session")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        import time as _time
        from app.kite.history import history_warmup

        history_triggered = False
        feed_started = False

        while not self._stop_event.is_set():
            now = datetime.now(IST)
            t = now.time()

            if not history_triggered and t >= HISTORY_START:
                try:
                    db = SessionLocal()
                    history_warmup.start(db)
                    db.close()
                except Exception:
                    pass
                history_triggered = True

            if not feed_started and t >= MARKET_OPEN:
                self._start_feed()
                feed_started = True

            if t >= MARKET_CLOSE and feed_started:
                db = SessionLocal()
                try:
                    engine.close_all_for_eod(db, self.quotes)
                finally:
                    db.close()
                break

            _time.sleep(10)

    def _start_feed(self) -> None:
        from app.db.models import UniverseConstituent
        from app.kite.client import KiteClientFactory
        from app.kite.websocket import KiteWebSocketService
        from app.market.live import LiveMarketFeed

        db = SessionLocal()
        try:
            kite = KiteClientFactory.authenticated_client(db)
            members = db.query(UniverseConstituent).filter(
                UniverseConstituent.instrument_token.isnot(None)
            ).all()
            token_to_symbol = {m.instrument_token: m.symbol for m in members}
            feed = LiveMarketFeed(token_to_symbol)
            ticker = KiteWebSocketService.create_ticker(
                kite,
                list(token_to_symbol.keys()),
                feed.on_tick,
            )
            ticker.connect(threaded=True)
        finally:
            db.close()


nse_session = NSESession()
