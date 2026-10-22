from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.kite.client import KiteClientFactory
from app.market.universe import UniverseService

router = APIRouter()
_service = UniverseService()


@router.post("/refresh")
def refresh_universe(db: Session = Depends(get_db)):
    kite = KiteClientFactory.authenticated_client(db)
    result = _service.refresh(kite, db)
    return result
