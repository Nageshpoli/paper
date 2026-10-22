from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import AppState, ScannerState, UniverseConstituent
from app.db.session import get_db
from app.engine.runner import engine
from app.kite.auth import KiteAuthService

router = APIRouter()
_auth = KiteAuthService()


@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    account_token = _auth.get_access_token(db)
    from app.db.models import VirtualAccount, UniverseConstituent, MarketCandle
    account = db.query(VirtualAccount).first()
    universe_count = db.query(UniverseConstituent).count()
    candle_count = db.query(MarketCandle).count()
    from app.market.live import active_market_feed
    return {
        "running": engine.state.running,
        "kill_switch": engine.state.kill_switch,
        "mode": engine.state.mode,
        "last_message": engine.state.last_message,
        "last_tick_at": engine.state.last_tick_at.isoformat() if engine.state.last_tick_at else None,
        "setup": {
            "kite_connected": bool(account_token),
            "universe_loaded": universe_count > 0,
            "history_loaded": candle_count > 0,
            "feed_live": active_market_feed is not None,
        },
        "account": {
            "cash": account.cash if account else 0,
            "realized_pnl": account.realized_pnl if account else 0,
        },
    }


@router.get("/ready")
def ready():
    return {"mode": engine.state.mode}


@router.get("/scanner")
def get_scanner(db: Session = Depends(get_db)):
    rows = db.query(ScannerState).order_by(ScannerState.score.desc()).all()
    return [
        {
            "symbol": r.symbol,
            "price": r.price,
            "change_pct": r.change_pct,
            "or_high": r.or_high,
            "or_low": r.or_low,
            "relative_volume": r.relative_volume,
            "market_direction": r.market_direction,
            "sector_direction": r.sector_direction,
            "score": r.score,
            "status": r.status,
            "reason": r.reason,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        }
        for r in rows
    ]
