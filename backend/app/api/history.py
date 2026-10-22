from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.kite.history import history_warmup

router = APIRouter()


@router.post("/warmup")
def warmup(db: Session = Depends(get_db)):
    history_warmup.start(db)
    return {"status": "warmup_started"}
