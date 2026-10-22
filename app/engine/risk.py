from __future__ import annotations

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.db.models import CompletedTrade, Position, VirtualAccount
from app.db.session import SessionLocal
from app.strategy.orb import ORBSignal

IST = ZoneInfo("Asia/Kolkata")
log = logging.getLogger(__name__)


class RiskManager:
    """Guards against daily limits before a trade is placed."""

    def can_trade(self, signal: ORBSignal) -> tuple[bool, str]:
        cfg = get_settings()
        db = SessionLocal()
        try:
            account = db.query(VirtualAccount).first()
            if account is None:
                return False, "No virtual account"

            # Daily trade count
            today = date.today()
            today_trades = db.query(CompletedTrade).filter(
                CompletedTrade.entry_time >= datetime(today.year, today.month, today.day)
            ).count()
            if today_trades >= cfg.max_trades_per_day:
                return False, f"Daily trade limit {cfg.max_trades_per_day} reached"

            # Open positions count
            open_count = db.query(Position).filter_by(status="OPEN").count()
            if open_count >= cfg.max_open_positions:
                return False, f"Max open positions {cfg.max_open_positions} reached"

            # No duplicate for same symbol
            already_open = db.query(Position).filter_by(
                symbol=signal.symbol, status="OPEN"
            ).first()
            if already_open:
                return False, f"Already have an open position in {signal.symbol}"

            # No re-entry after stop-loss today
            stopped_out_today = db.query(CompletedTrade).filter(
                CompletedTrade.symbol == signal.symbol,
                CompletedTrade.exit_reason == "STOP_LOSS",
                CompletedTrade.entry_time >= datetime(today.year, today.month, today.day),
            ).first()
            if stopped_out_today:
                return False, f"{signal.symbol} was stopped out today — no re-entry"

            # Daily loss limit (10% of starting capital)
            today_pnl = db.query(CompletedTrade).filter(
                CompletedTrade.entry_time >= datetime(today.year, today.month, today.day)
            ).all()
            realized_today = sum(t.net_pnl for t in today_pnl)
            starting = account.starting_capital or cfg.virtual_capital
            if realized_today <= -(starting * 0.10):
                return False, f"Daily loss limit reached (₹{abs(realized_today):.0f})"

            return True, "OK"
        finally:
            db.close()
