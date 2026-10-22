from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import CompletedTrade, Position, StrategySignal
from app.db.session import get_db
from app.engine.runner import engine

router = APIRouter()


@router.get("/positions")
def get_positions(db: Session = Depends(get_db)):
    rows = db.query(Position).filter_by(status="OPEN").all()
    return [
        {
            "symbol": p.symbol,
            "side": p.side,
            "quantity": p.quantity,
            "entry_price": p.entry_price,
            "last_price": p.last_price,
            "stop_loss": p.stop_loss,
            "target": p.target,
            "strategy": p.strategy,
            "unrealized_pnl": (
                ((p.last_price or p.entry_price) - p.entry_price) * p.quantity
                if p.side == "LONG"
                else (p.entry_price - (p.last_price or p.entry_price)) * p.quantity
            ),
        }
        for p in rows
    ]


@router.get("/trades")
def get_trades(limit: int = 100, db: Session = Depends(get_db)):
    rows = db.query(CompletedTrade).order_by(CompletedTrade.closed_at.desc()).limit(limit).all()
    return [
        {
            "id": t.id,
            "symbol": t.symbol,
            "side": t.side,
            "quantity": t.quantity,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "pnl": t.pnl,
            "strategy": t.strategy,
            "exit_reason": t.exit_reason,
            "opened_at": t.opened_at.isoformat() if t.opened_at else None,
            "closed_at": t.closed_at.isoformat() if t.closed_at else None,
        }
        for t in rows
    ]


@router.get("/signals")
def get_signals(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.query(StrategySignal).order_by(StrategySignal.created_at.desc()).limit(limit).all()
    return [
        {
            "id": s.id,
            "symbol": s.symbol,
            "action": s.action,
            "strategy": s.strategy,
            "price": s.price,
            "confidence": s.confidence,
            "reason": s.reason,
            "execution_status": s.execution_status,
            "execution_reason": s.execution_reason,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in rows
    ]
