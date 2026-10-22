from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import CompletedTrade, PaperOrder, Position, VirtualAccount
from app.strategies.base import Signal

IST = ZoneInfo("Asia/Kolkata")


class PaperBroker:
    def open_position(self, db: Session, signal: Signal, settings: Settings) -> Optional[Position]:
        account = self._account(db)
        price = signal.price
        qty = self._calculate_qty(account, price, signal.stop_loss, settings)
        if qty <= 0:
            return None
        notional = qty * price
        if notional > settings.max_position_notional:
            qty = int(settings.max_position_notional // price)
        if qty <= 0:
            return None
        notional = qty * price
        if account.cash < notional:
            return None
        account.cash -= notional
        order = PaperOrder(
            symbol=signal.symbol,
            action=signal.action,
            quantity=qty,
            price=price,
            status="FILLED",
            strategy=signal.strategy,
            signal_key=signal.signal_id,
        )
        db.add(order)
        db.flush()
        position = Position(
            symbol=signal.symbol,
            side="LONG" if signal.action == "BUY" else "SHORT",
            quantity=qty,
            entry_price=price,
            last_price=price,
            stop_loss=signal.stop_loss,
            target=signal.target,
            strategy=signal.strategy,
            status="OPEN",
            entry_order_id=order.id,
        )
        db.add(position)
        db.commit()
        db.refresh(position)
        return position

    def close_position(self, db: Session, position: Position,
                       exit_price: float, reason: str) -> Optional[CompletedTrade]:
        account = self._account(db)
        qty = position.quantity
        notional = qty * exit_price
        if position.side == "LONG":
            pnl = (exit_price - position.entry_price) * qty
        else:
            pnl = (position.entry_price - exit_price) * qty
        account.cash += notional
        account.realized_pnl = (account.realized_pnl or 0) + pnl
        order = PaperOrder(
            symbol=position.symbol,
            action="SELL" if position.side == "LONG" else "COVER",
            quantity=qty,
            price=exit_price,
            status="FILLED",
            strategy=position.strategy,
        )
        db.add(order)
        db.flush()
        position.status = "CLOSED"
        position.last_price = exit_price
        trade = CompletedTrade(
            symbol=position.symbol,
            side=position.side,
            quantity=qty,
            entry_price=position.entry_price,
            exit_price=exit_price,
            pnl=pnl,
            strategy=position.strategy,
            entry_order_id=position.entry_order_id,
            exit_order_id=order.id,
            exit_reason=reason,
        )
        db.add(trade)
        db.commit()
        db.refresh(trade)
        return trade

    def close_all_positions(self, db: Session) -> None:
        from app.db.models import Position as P
        positions = db.query(P).filter(P.status == "OPEN").all()
        for pos in positions:
            self.close_position(db, pos, pos.last_price or pos.entry_price, "Kill-switch close")

    def get_position(self, db: Session, symbol: str) -> Optional[Position]:
        return db.query(Position).filter_by(symbol=symbol, status="OPEN").first()

    @staticmethod
    def unrealized_pnl(position: Position, price: float) -> float:
        if position.side == "LONG":
            return (price - position.entry_price) * position.quantity
        return (position.entry_price - price) * position.quantity

    @staticmethod
    def check_exit_conditions(position: Position, price: float, settings: Settings) -> Optional[str]:
        if position.stop_loss and position.side == "LONG" and price <= position.stop_loss:
            return "Stop loss hit"
        if position.stop_loss and position.side == "SHORT" and price >= position.stop_loss:
            return "Stop loss hit"
        if position.target and position.side == "LONG" and price >= position.target:
            return "Target reached"
        if position.target and position.side == "SHORT" and price <= position.target:
            return "Target reached"
        return None

    @staticmethod
    def _account(db: Session) -> VirtualAccount:
        account = db.query(VirtualAccount).first()
        if account is None:
            from app.config import get_settings
            account = VirtualAccount(cash=get_settings().virtual_capital)
            db.add(account)
            db.commit()
            db.refresh(account)
        return account

    @staticmethod
    def _calculate_qty(account: VirtualAccount, price: float,
                       stop_loss: Optional[float], settings: Settings) -> int:
        risk_amount = account.cash * settings.risk_per_trade_pct
        if stop_loss and abs(price - stop_loss) > 0:
            return int(risk_amount / abs(price - stop_loss))
        return int(risk_amount / (price * 0.01))
