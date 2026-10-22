from __future__ import annotations

import pytest

from app.db.models import VirtualAccount, Position, CompletedTrade, PaperOrder
from app.engine.paper_broker import PaperBroker
from app.strategies.base import Signal


class _MockSettings:
    virtual_capital = 100000.0
    max_position_notional = 30000.0
    risk_per_trade_pct = 0.005
    max_open_positions = 3
    max_entries_per_day = 3
    max_daily_loss = 3000.0
    max_total_exposure = 90000.0
    max_positions_per_sector = 1
    paper_only = True


def _account(db, cash=100000.0):
    acc = VirtualAccount(cash=cash, realized_pnl=0.0)
    db.add(acc)
    db.commit()
    return acc


def _buy_signal(symbol="TCS", price=3600.0, stop=3550.0):
    return Signal(
        action="BUY", symbol=symbol, strategy="orb_v1",
        price=price, confidence=0.6, reason="test",
        stop_loss=stop, target=3700.0, signal_id="test-sig-1",
    )


def test_open_position_deducts_cash(db):
    _account(db)
    broker = PaperBroker()
    sig = _buy_signal()
    pos = broker.open_position(db, sig, _MockSettings())
    assert pos is not None
    assert pos.status == "OPEN"
    acc = db.query(VirtualAccount).first()
    assert acc.cash < 100000.0


def test_close_position_returns_cash(db):
    _account(db)
    broker = PaperBroker()
    sig = _buy_signal()
    pos = broker.open_position(db, sig, _MockSettings())
    assert pos is not None
    cash_before = db.query(VirtualAccount).first().cash
    trade = broker.close_position(db, pos, 3700.0, "Target reached")
    assert trade is not None
    acc = db.query(VirtualAccount).first()
    assert acc.cash > cash_before
    assert trade.pnl > 0


def test_close_with_loss(db):
    _account(db)
    broker = PaperBroker()
    sig = _buy_signal()
    pos = broker.open_position(db, sig, _MockSettings())
    trade = broker.close_position(db, pos, 3500.0, "Stop loss hit")
    assert trade.pnl < 0


def test_get_position_returns_open(db):
    _account(db)
    broker = PaperBroker()
    broker.open_position(db, _buy_signal(), _MockSettings())
    pos = broker.get_position(db, "TCS")
    assert pos is not None and pos.status == "OPEN"


def test_get_position_none_after_close(db):
    _account(db)
    broker = PaperBroker()
    pos = broker.open_position(db, _buy_signal(), _MockSettings())
    broker.close_position(db, pos, 3600.0, "test")
    assert broker.get_position(db, "TCS") is None


def test_no_position_when_insufficient_cash(db):
    acc = VirtualAccount(cash=10.0, realized_pnl=0.0)
    db.add(acc); db.commit()
    broker = PaperBroker()
    pos = broker.open_position(db, _buy_signal(), _MockSettings())
    assert pos is None


def test_stop_loss_hit(db):
    from app.engine.paper_broker import PaperBroker as PB
    broker = PB()
    pos = Position(symbol="TCS", side="LONG", quantity=10,
                   entry_price=3600.0, stop_loss=3550.0, target=3700.0, status="OPEN")
    assert broker.check_exit_conditions(pos, 3545.0, _MockSettings()) == "Stop loss hit"


def test_target_hit(db):
    broker = PaperBroker()
    pos = Position(symbol="TCS", side="LONG", quantity=10,
                   entry_price=3600.0, stop_loss=3550.0, target=3700.0, status="OPEN")
    assert broker.check_exit_conditions(pos, 3705.0, _MockSettings()) == "Target reached"
