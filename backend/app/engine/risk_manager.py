from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Position, VirtualAccount
from app.strategies.base import Signal


class RiskManager:
    def pre_trade_check(
        self,
        db: Session,
        signal: Signal,
        entries_today: int,
        daily_loss: float,
    ) -> tuple[bool, str]:
        settings = get_settings()

        if settings.paper_only is False:
            return False, "Non-paper trading not allowed"

        open_positions = db.query(Position).filter_by(status="OPEN").count()
        if open_positions >= settings.max_open_positions:
            return False, f"Max open positions ({settings.max_open_positions}) reached"

        if entries_today >= settings.max_entries_per_day:
            return False, f"Max entries per day ({settings.max_entries_per_day}) reached"

        if daily_loss <= -settings.max_daily_loss:
            return False, f"Max daily loss (₹{settings.max_daily_loss:,.0f}) reached"

        account = db.query(VirtualAccount).first()
        if account is None or account.cash <= 0:
            return False, "Insufficient virtual capital"

        sector = self._sector_for(db, signal.symbol)
        if sector:
            sector_count = db.query(Position).filter(
                Position.status == "OPEN",
                Position.strategy == signal.strategy,
            ).count()
            if sector_count >= settings.max_positions_per_sector:
                return False, f"Sector position limit ({settings.max_positions_per_sector}) reached"

        total_exposure = self._total_exposure(db)
        notional = signal.price * self._estimate_qty(account, signal, settings)
        if total_exposure + notional > settings.max_total_exposure:
            return False, f"Would exceed max total exposure (₹{settings.max_total_exposure:,.0f})"

        return True, ""

    @staticmethod
    def _total_exposure(db: Session) -> float:
        positions = db.query(Position).filter_by(status="OPEN").all()
        return sum((p.last_price or p.entry_price) * p.quantity for p in positions)

    @staticmethod
    def _sector_for(db: Session, symbol: str) -> Optional[str]:
        from app.db.models import UniverseConstituent
        member = db.query(UniverseConstituent).filter_by(symbol=symbol).first()
        return member.sector_index if member else None

    @staticmethod
    def _estimate_qty(account: VirtualAccount, signal: Signal, settings) -> int:
        risk_amount = account.cash * settings.risk_per_trade_pct
        if signal.stop_loss and abs(signal.price - signal.stop_loss) > 0:
            return int(risk_amount / abs(signal.price - signal.stop_loss))
        return int(risk_amount / (signal.price * 0.01))
