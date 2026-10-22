from __future__ import annotations

import json
import threading

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.backtest.engine import BacktestEngine
from app.db.models import BacktestRun
from app.db.session import get_db

router = APIRouter()
_engine = BacktestEngine()


@router.post("")
def run_backtest(
    strategy_name: str = "orb_v1",
    start_date: str = "2024-01-01",
    end_date: str = "2024-03-31",
    universe_name: str = "NIFTY_500",
    db: Session = Depends(get_db),
):
    run = BacktestRun(
        strategy_name=strategy_name,
        start_date=start_date,
        end_date=end_date,
        universe_name=universe_name,
        status="PENDING",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = run.id
    threading.Thread(
        target=_run_backtest_thread, args=(run_id,), daemon=True
    ).start()
    return {"run_id": run_id, "status": "PENDING"}


def _run_backtest_thread(run_id: int) -> None:
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        _engine.run(db, run_id)
    finally:
        db.close()


@router.get("/{run_id}")
def get_backtest(run_id: int, db: Session = Depends(get_db)):
    run = db.get(BacktestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    metrics = json.loads(run.metrics) if run.metrics else None
    trade_log = json.loads(run.trade_log) if run.trade_log else None
    return {
        "id": run.id,
        "status": run.status,
        "strategy_name": run.strategy_name,
        "start_date": run.start_date,
        "end_date": run.end_date,
        "universe_name": run.universe_name,
        "metrics": metrics,
        "trade_log": trade_log,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


@router.get("")
def list_backtests(limit: int = 20, db: Session = Depends(get_db)):
    rows = db.query(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "status": r.status,
            "strategy_name": r.strategy_name,
            "start_date": r.start_date,
            "end_date": r.end_date,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
