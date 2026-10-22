from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import CompletedTrade, DailySummary
from app.db.session import get_db

router = APIRouter()


@router.get("/analytics")
def get_analytics(db: Session = Depends(get_db)):
    trades = db.query(CompletedTrade).all()
    if not trades:
        return {"total_trades": 0, "win_rate": 0.0, "total_pnl": 0.0,
                "expectancy": 0.0, "profit_factor": 0.0}
    pnls = [t.pnl or 0.0 for t in trades]
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p <= 0]
    gross_profit = sum(winners)
    gross_loss = abs(sum(losers))
    return {
        "total_trades": len(trades),
        "win_rate": round(len(winners) / len(trades) * 100, 1),
        "total_pnl": round(sum(pnls), 2),
        "expectancy": round(sum(pnls) / len(trades), 2),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0.0,
    }


@router.get("/daily-summary")
def get_daily_summary(limit: int = 30, db: Session = Depends(get_db)):
    rows = db.query(DailySummary).order_by(DailySummary.date.desc()).limit(limit).all()
    return [
        {
            "date": r.date,
            "total_trades": r.total_trades,
            "winning_trades": r.winning_trades,
            "total_pnl": r.total_pnl,
            "ending_capital": r.ending_capital,
        }
        for r in rows
    ]
