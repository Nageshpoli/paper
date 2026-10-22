from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.engine.runner import engine
from app.engine.session import nse_session

router = APIRouter()


@router.post("/start")
def start(db: Session = Depends(get_db)):
    engine.start(db)
    nse_session.start()
    return {"status": "started"}


@router.post("/stop")
def stop(db: Session = Depends(get_db)):
    engine.stop(db)
    return {"status": "stopped"}


@router.post("/kill-switch")
def kill_switch(db: Session = Depends(get_db)):
    engine.kill(db)
    return {"status": "kill_switch_activated"}


@router.post("/reset-kill")
def reset_kill(db: Session = Depends(get_db)):
    engine.reset_kill(db)
    return {"status": "kill_switch_reset"}
