from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    AppState, CompletedTrade, DailySummary, PaperOrder,
    Position, StrategySignal, VirtualAccount,
)
from app.engine.paper_broker import PaperBroker
from app.engine.risk_manager import RiskManager
from app.strategies.base import MarketSnapshot, Signal


@dataclass
class EngineState:
    running: bool = False
    kill_switch: bool = False
    mode: str = "PAPER"
    last_tick_at: Optional[datetime] = None
    last_message: str = ""
    entries_today: int = 0
    daily_loss: float = 0.0


class TradingEngine:
    def __init__(self) -> None:
        self.state = EngineState()
        self.broker = PaperBroker()
        self.risk = RiskManager()

    # ── lifecycle ────────────────────────────────────────────────────────────
    def start(self, db: Session) -> None:
        if self.state.running:
            return
        self.state.running = True
        self.state.kill_switch = False
        self.state.last_message = "Engine started"
        self._persist_state(db)

    def stop(self, db: Session) -> None:
        self.state.running = False
        self.state.last_message = "Engine stopped"
        self._persist_state(db)

    def kill(self, db: Session) -> None:
        self.state.kill_switch = True
        self.state.running = False
        self.state.last_message = "Kill-switch activated — all new entries blocked"
        self._persist_state(db)
        self.broker.close_all_positions(db)

    def reset_kill(self, db: Session) -> None:
        self.state.kill_switch = False
        self.state.last_message = "Kill-switch reset"
        self._persist_state(db)

    # ── signal execution ─────────────────────────────────────────────────────
    def execute_signal(self, db: Session, signal: Signal) -> bool:
        settings = get_settings()
        if not self.state.running or self.state.kill_switch:
            return False
        ok, reason = self.risk.pre_trade_check(
            db, signal, self.state.entries_today, self.state.daily_loss)
        if not ok:
            self._update_signal(db, signal, "REJECTED", reason)
            self.state.last_message = f"Risk: {reason}"
            return False
        position = self.broker.open_position(db, signal, settings)
        if position:
            self.state.entries_today += 1
            self._update_signal(db, signal, "FILLED", "Paper entry opened")
            self.state.last_message = f"Opened {signal.action} {signal.symbol} @ {signal.price:.2f}"
            self._persist_state(db)
            return True
        return False

    def update_open_positions(self, db: Session, snapshot: MarketSnapshot) -> None:
        settings = get_settings()
        position = self.broker.get_position(db, snapshot.symbol)
        if not position:
            return
        pnl = self.broker.unrealized_pnl(position, snapshot.last_price)
        hit = self.broker.check_exit_conditions(position, snapshot.last_price, settings)
        if hit:
            trade = self.broker.close_position(db, position, snapshot.last_price, hit)
            if trade:
                self.state.daily_loss += min(0, trade.pnl or 0)
                self.state.last_message = (
                    f"Closed {position.symbol} @ {snapshot.last_price:.2f} — {hit}")

    # ── EOD close ────────────────────────────────────────────────────────────
    def close_all_for_eod(self, db: Session, quotes: dict) -> None:
        from app.db.models import Position as P
        positions = db.query(P).filter(P.status == "OPEN").all()
        for pos in positions:
            q = quotes.get(pos.symbol)
            price = q.last if q else pos.last_price
            if price:
                self.broker.close_position(db, pos, float(price), "EOD forced close")
        self._write_daily_summary(db)

    def _write_daily_summary(self, db: Session) -> None:
        from datetime import date as _date
        from app.db.models import CompletedTrade as CT
        today = _date.today()
        trades = db.query(CT).filter(CT.closed_at >= str(today)).all()
        winners = [t for t in trades if (t.pnl or 0) > 0]
        account = db.query(VirtualAccount).first()
        row = db.query(DailySummary).filter_by(date=str(today)).first()
        if row is None:
            row = DailySummary(date=str(today))
            db.add(row)
        row.total_trades = len(trades)
        row.winning_trades = len(winners)
        row.total_pnl = sum(t.pnl or 0 for t in trades)
        row.ending_capital = account.cash if account else None
        db.commit()

    # ── helpers ──────────────────────────────────────────────────────────────
    def _persist_state(self, db: Session) -> None:
        row = db.query(AppState).first()
        if row is None:
            row = AppState()
            db.add(row)
        row.running = self.state.running
        row.kill_switch = self.state.kill_switch
        row.mode = self.state.mode
        row.last_message = self.state.last_message
        db.commit()

    @staticmethod
    def _update_signal(db: Session, signal: Signal, status: str, reason: str) -> None:
        if not signal.signal_id:
            return
        row = db.query(StrategySignal).filter_by(signal_key=signal.signal_id).first()
        if row:
            row.execution_status = status
            row.execution_reason = reason
            db.commit()

    def restore_from_db(self, db: Session) -> None:
        row = db.query(AppState).first()
        if row:
            self.state.running = bool(row.running)
            self.state.kill_switch = bool(row.kill_switch)
            self.state.mode = row.mode or "PAPER"
            self.state.last_message = row.last_message or ""


engine = TradingEngine()
