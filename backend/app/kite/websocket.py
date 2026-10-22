from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.config import get_settings
from app.kite.auth import KiteAuthService

try:
    from kiteconnect import KiteTicker
except ModuleNotFoundError:
    KiteTicker = None

TickHandler = Callable[[dict], None]


class KiteWebSocketService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.auth = KiteAuthService()

    def create_ticker(self, db: Session, instrument_tokens: list[int], on_tick: TickHandler):
        if KiteTicker is None:
            raise RuntimeError("kiteconnect not installed. Run: pip install -r requirements.txt")
        token = self.auth.get_access_token(db)
        if not token:
            raise ValueError("Kite access token missing. Visit /login first.")
        ticker = KiteTicker(self.settings.kite_api_key, token)

        def handle_ticks(_ws, ticks):
            for tick in ticks:
                on_tick(tick)

        ticker.on_ticks = handle_ticks
        return ticker
