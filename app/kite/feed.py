from __future__ import annotations

import logging
from typing import Callable

from app.config import get_settings
from app.kite.auth import _auth

log = logging.getLogger(__name__)


class KiteFeed:
    """WebSocket tick feed wrapper. Calls on_tick(tick_dict) for every tick."""

    def __init__(self, on_tick: Callable[[dict], None]):
        self._on_tick_cb = on_tick
        self._kws = None

    def start(self, tokens: list[int]) -> None:
        from kiteconnect import KiteTicker
        settings = get_settings()
        token = _auth.get_access_token()
        if not token:
            raise RuntimeError("Cannot start feed: not authenticated")

        self._kws = KiteTicker(settings.kite_api_key, token)
        self._kws.on_connect = lambda ws, _: ws.subscribe(tokens)
        self._kws.on_ticks = self._handle_ticks
        self._kws.on_close = lambda ws, code, reason: log.warning("WS closed: %s %s", code, reason)
        self._kws.on_error = lambda ws, code, reason: log.error("WS error: %s %s", code, reason)
        self._kws.on_reconnect = lambda ws, attempt, delay: log.info("WS reconnect attempt %s", attempt)
        self._kws.connect(threaded=True)
        log.info("KiteFeed started, subscribed %d tokens", len(tokens))

    def stop(self) -> None:
        if self._kws:
            try:
                self._kws.close()
            except Exception:
                pass

    def is_connected(self) -> bool:
        return self._kws is not None and self._kws.is_connected()

    def _handle_ticks(self, ws, ticks: list[dict]) -> None:
        for tick in ticks:
            try:
                self._on_tick_cb(tick)
            except Exception as exc:
                log.exception("on_tick callback error: %s", exc)
