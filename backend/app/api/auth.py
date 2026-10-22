from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.kite.auth import KiteAuthService

router = APIRouter()
_auth = KiteAuthService()


@router.get("/login")
def login():
    return RedirectResponse(url=_auth.login_url())


@router.get("/callback")
def callback(request_token: str, db: Session = Depends(get_db)):
    _auth.exchange_request_token(request_token, db)
    return RedirectResponse(url="/")
