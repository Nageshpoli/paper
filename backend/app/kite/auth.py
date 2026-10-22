from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import AppState

try:
    from kiteconnect import KiteConnect
except ModuleNotFoundError:
    KiteConnect = None

ACCESS_TOKEN_KEY = "kite_access_token"


class KiteAuthService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def client(self) -> KiteConnect:
        if KiteConnect is None:
            raise RuntimeError("kiteconnect not installed. Run: pip install -r requirements.txt")
        return KiteConnect(api_key=self.settings.kite_api_key)

    def login_url(self) -> str:
        return self.client().login_url()

    def exchange_request_token(self, db: Session, request_token: str) -> str:
        if not self.settings.kite_api_secret:
            raise ValueError("KITE_API_SECRET is missing in .env")
        kite = self.client()
        data = kite.generate_session(request_token, api_secret=self.settings.kite_api_secret)
        access_token = data["access_token"]
        self._save(db, access_token)
        return access_token

    def _save(self, db: Session, access_token: str) -> None:
        state = db.get(AppState, ACCESS_TOKEN_KEY)
        if state:
            state.value = access_token
        else:
            db.add(AppState(key=ACCESS_TOKEN_KEY, value=access_token))
        db.commit()

    def get_access_token(self, db: Session) -> str | None:
        state = db.get(AppState, ACCESS_TOKEN_KEY)
        return state.value if state else None
