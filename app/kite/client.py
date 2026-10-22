from __future__ import annotations

from app.config import get_settings
from app.kite.auth import _auth


def get_kite():
    """Return an authenticated KiteConnect instance, or raise if not logged in."""
    from kiteconnect import KiteConnect
    settings = get_settings()
    token = _auth.get_access_token()
    if not token:
        raise RuntimeError("Not authenticated — log in via Zerodha first")
    kite = KiteConnect(api_key=settings.kite_api_key)
    kite.set_access_token(token)
    return kite
