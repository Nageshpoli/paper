from __future__ import annotations

from app.config import get_settings
from app.db.models import SystemKV
from app.db.session import SessionLocal

ACCESS_TOKEN_KEY = "kite_access_token"


class KiteAuth:
    def __init__(self):
        self._settings = get_settings()

    def get_login_url(self) -> str:
        from kiteconnect import KiteConnect
        kite = KiteConnect(api_key=self._settings.kite_api_key)
        return kite.login_url()

    def exchange_request_token(self, request_token: str) -> str:
        from kiteconnect import KiteConnect
        kite = KiteConnect(api_key=self._settings.kite_api_key)
        session = kite.generate_session(request_token, api_secret=self._settings.kite_api_secret)
        access_token = session["access_token"]
        self._save(access_token)
        return access_token

    def get_access_token(self) -> str | None:
        db = SessionLocal()
        try:
            row = db.get(SystemKV, ACCESS_TOKEN_KEY)
            return row.value if row and row.value else None
        finally:
            db.close()

    def _save(self, token: str) -> None:
        db = SessionLocal()
        try:
            row = db.get(SystemKV, ACCESS_TOKEN_KEY)
            if row:
                row.value = token
            else:
                db.add(SystemKV(key=ACCESS_TOKEN_KEY, value=token))
            db.commit()
        finally:
            db.close()

    def is_authenticated(self) -> bool:
        return self.get_access_token() is not None


_auth = KiteAuth()
