from sqlalchemy.orm import Session

from app.kite.auth import KiteAuthService


class KiteClientFactory:
    def __init__(self) -> None:
        self.auth = KiteAuthService()

    def authenticated_client(self, db: Session):
        token = self.auth.get_access_token(db)
        if not token:
            raise ValueError("Kite access token missing. Visit /login first.")
        kite = self.auth.client()
        kite.set_access_token(token)
        return kite
