from sqlalchemy.orm import Session

from app.kite.client import KiteClientFactory


class InstrumentService:
    def __init__(self) -> None:
        self.factory = KiteClientFactory()

    def nse_equities(self, db: Session) -> list[dict]:
        """NSE equity instruments only (EQ segment)."""
        kite = self.factory.authenticated_client(db)
        return [i for i in kite.instruments("NSE")
                if i.get("instrument_type") == "EQ" and i.get("segment") == "NSE"]

    def all_nse(self, db: Session) -> list[dict]:
        """All NSE instruments including indices — used for token lookups."""
        kite = self.factory.authenticated_client(db)
        return list(kite.instruments("NSE"))
