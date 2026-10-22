from __future__ import annotations

import pytest

from app.engine.paper_broker import PaperBroker
from app.strategy.orb import ORBSignal


def _signal(action="BUY", price=100.0, stop=95.0, target=110.0):
    return ORBSignal(
        symbol="TESTCO", sector="NIFTY IT", action=action,
        signal_price=price, or_high=102.0, or_low=95.0,
        vwap=99.0, rvol=2.5, stop_loss=stop, target=target,
        risk_reward=2.0,
    )


class TestCharges:
    def test_charges_are_non_negative(self):
        from app.config import get_settings
        cfg = get_settings()
        charges = PaperBroker._charges(100.0, 105.0, 10, "LONG", cfg)
        assert charges["total"] >= 0
        assert charges["brokerage"] <= 40.0  # max 2 × ₹20

    def test_brokerage_cap_applied(self):
        from app.config import get_settings
        cfg = get_settings()
        # Large trade — brokerage should cap at ₹20 per order
        charges = PaperBroker._charges(10000.0, 10500.0, 100, "LONG", cfg)
        assert charges["brokerage"] <= cfg.brokerage_cap * 2


class TestPositionSizing:
    def test_qty_proportional_to_risk(self):
        from app.db.models import VirtualAccount
        from app.config import get_settings
        cfg = get_settings()
        account = VirtualAccount(cash=100_000.0, realized_pnl=0.0)
        sig = _signal(price=100.0, stop=95.0)  # risk per share = ₹5
        qty = PaperBroker._calc_qty(account, sig, cfg)
        # risk_amt = 100000 * 0.005 = 500; qty = 500 / 5 = 100
        assert qty == 100

    def test_qty_zero_when_risk_is_zero(self):
        from app.db.models import VirtualAccount
        from app.config import get_settings
        cfg = get_settings()
        account = VirtualAccount(cash=100_000.0, realized_pnl=0.0)
        sig = _signal(price=100.0, stop=100.0)  # zero risk
        qty = PaperBroker._calc_qty(account, sig, cfg)
        assert qty == 0


class TestFillPrice:
    def test_buy_has_positive_slippage(self):
        from app.config import get_settings
        cfg = get_settings()
        fill = PaperBroker._fill_price(100.0, "BUY", cfg)
        assert fill > 100.0

    def test_short_has_negative_slippage(self):
        from app.config import get_settings
        cfg = get_settings()
        fill = PaperBroker._fill_price(100.0, "SHORT", cfg)
        assert fill < 100.0
