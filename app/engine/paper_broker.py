from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import Settings, get_settings
from app.db.models import CompletedTrade, Position, VirtualAccount
from app.db.session import SessionLocal
from app.strategy.orb import ORBSignal

IST = ZoneInfo("Asia/Kolkata")
log = logging.getLogger(__name__)


class PaperBroker:
    """
    Simulates order fills, maintains virtual cash, tracks positions.
    Never places real Kite orders.
    """

    # ------------------------------------------------------------------
    def place_order(self, signal: ORBSignal) -> Position | None:
        cfg = get_settings()
        db = SessionLocal()
        try:
            account = self._get_account(db, cfg)
            qty = self._calc_qty(account, signal, cfg)
            if qty <= 0:
                log.info("Skipping %s: qty=0 (risk too small for price)", signal.symbol)
                return None

            fill = self._fill_price(signal.signal_price, signal.action, cfg)
            notional = fill * qty
            if notional > cfg.max_position_notional:
                qty = int(cfg.max_position_notional / fill)
            if qty <= 0:
                return None

            notional = fill * qty
            if account.cash < notional:
                log.info("Skipping %s: insufficient cash (need ₹%.0f, have ₹%.0f)",
                         signal.symbol, notional, account.cash)
                return None

            # Recalculate stop/target from actual fill price
            if signal.action == "BUY":
                stop = signal.stop_loss
                risk = fill - stop
                target = fill + risk * cfg.reward_to_risk
            else:
                stop = signal.stop_loss
                risk = stop - fill
                target = fill - risk * cfg.reward_to_risk

            if risk <= 0:
                return None

            pos = Position(
                symbol=signal.symbol, sector=signal.sector,
                side="LONG" if signal.action == "BUY" else "SHORT",
                qty=qty, entry_price=signal.signal_price, fill_price=fill,
                stop_loss=stop, target=target,
                entry_time=datetime.now(IST).replace(tzinfo=None),
                last_price=fill,
            )
            db.add(pos)
            account.cash -= notional
            db.commit()
            db.refresh(pos)
            log.info("Paper order filled: %s %s %d @ %.2f | stop=%.2f target=%.2f",
                     signal.action, signal.symbol, qty, fill, stop, target)
            return pos
        finally:
            db.close()

    def update_positions(self, prices: dict[str, float]) -> None:
        """Update unrealized P&L for all open positions."""
        db = SessionLocal()
        try:
            positions = db.query(Position).filter_by(status="OPEN").all()
            account = db.query(VirtualAccount).first()
            for pos in positions:
                ltp = prices.get(pos.symbol)
                if ltp is None:
                    continue
                pos.last_price = ltp
                if pos.side == "LONG":
                    pos.unrealized_pnl = (ltp - pos.fill_price) * pos.qty
                else:
                    pos.unrealized_pnl = (pos.fill_price - ltp) * pos.qty
            db.commit()
        finally:
            db.close()

    def check_exits(self, prices: dict[str, float], reason: str | None = None) -> list[CompletedTrade]:
        """Check stops, targets, and EOD. Returns list of closed trades."""
        db = SessionLocal()
        closed = []
        try:
            positions = db.query(Position).filter_by(status="OPEN").all()
            for pos in positions:
                ltp = prices.get(pos.symbol)
                if ltp is None:
                    continue
                exit_reason = reason  # EOD
                if not exit_reason:
                    if pos.side == "LONG":
                        if ltp <= pos.stop_loss:
                            exit_reason = "STOP_LOSS"
                        elif ltp >= pos.target:
                            exit_reason = "TARGET"
                    else:
                        if ltp >= pos.stop_loss:
                            exit_reason = "STOP_LOSS"
                        elif ltp <= pos.target:
                            exit_reason = "TARGET"
                if exit_reason:
                    trade = self._close(db, pos, ltp, exit_reason)
                    closed.append(trade)
            db.commit()
        finally:
            db.close()
        return closed

    # ------------------------------------------------------------------
    def _close(self, db, pos: Position, exit_price: float, reason: str) -> CompletedTrade:
        cfg = get_settings()
        account = db.query(VirtualAccount).first()

        if pos.side == "LONG":
            gross = (exit_price - pos.fill_price) * pos.qty
        else:
            gross = (pos.fill_price - exit_price) * pos.qty

        charges = self._charges(pos.fill_price, exit_price, pos.qty, pos.side, cfg)
        net = gross - charges["total"]

        trade = CompletedTrade(
            symbol=pos.symbol, sector=pos.sector, side=pos.side,
            qty=pos.qty, entry_price=pos.fill_price, exit_price=exit_price,
            entry_time=pos.entry_time,
            exit_time=datetime.now(IST).replace(tzinfo=None),
            gross_pnl=gross, brokerage=charges["brokerage"],
            other_charges=charges["total"] - charges["brokerage"],
            net_pnl=net, exit_reason=reason,
            or_high=None, or_low=None, rvol=None,
        )
        db.add(trade)

        # Return notional to cash
        if pos.side == "LONG":
            account.cash += exit_price * pos.qty
        else:
            account.cash += pos.fill_price * pos.qty + gross

        account.realized_pnl = (account.realized_pnl or 0) + net
        account.total_trades = (account.total_trades or 0) + 1
        if net > 0:
            account.winning_trades = (account.winning_trades or 0) + 1

        equity = account.cash + account.realized_pnl
        if equity > account.peak_equity:
            account.peak_equity = equity
        dd = (account.peak_equity - equity) / account.peak_equity * 100 if account.peak_equity else 0
        account.max_drawdown_pct = max(account.max_drawdown_pct or 0, dd)

        pos.status = "CLOSED"
        pos.unrealized_pnl = 0.0
        log.info("Trade closed: %s %s exit=%.2f net=₹%.0f reason=%s",
                 pos.side, pos.symbol, exit_price, net, reason)
        return trade

    @staticmethod
    def _fill_price(price: float, action: str, cfg: Settings) -> float:
        slip = cfg.slippage_pct
        return price * (1 + slip) if action == "BUY" else price * (1 - slip)

    @staticmethod
    def _calc_qty(account: VirtualAccount, signal: ORBSignal, cfg: Settings) -> int:
        equity = account.cash + (account.realized_pnl or 0)
        risk_amt = min(equity * cfg.risk_per_trade_pct, cfg.max_risk_per_trade)
        if signal.action == "BUY":
            risk_per_share = signal.signal_price - signal.stop_loss
        else:
            risk_per_share = signal.stop_loss - signal.signal_price
        if risk_per_share <= 0:
            return 0
        return int(risk_amt / risk_per_share)

    @staticmethod
    def _get_account(db, cfg: Settings) -> VirtualAccount:
        acc = db.query(VirtualAccount).first()
        if acc is None:
            acc = VirtualAccount(cash=cfg.virtual_capital, starting_capital=cfg.virtual_capital)
            db.add(acc)
            db.commit()
            db.refresh(acc)
        return acc

    @staticmethod
    def _charges(entry: float, exit_: float, qty: int, side: str, cfg: Settings) -> dict:
        buy_val = entry * qty
        sell_val = exit_ * qty
        brok = min(buy_val * cfg.brokerage_pct, cfg.brokerage_cap) + \
               min(sell_val * cfg.brokerage_pct, cfg.brokerage_cap)
        gst = brok * cfg.gst_pct
        stt = sell_val * cfg.stt_sell_pct
        exc = (buy_val + sell_val) * cfg.exchange_charges_pct
        stamp = buy_val * cfg.stamp_duty_pct
        return {"brokerage": brok, "gst": gst, "stt": stt, "exc": exc,
                "stamp": stamp, "total": brok + gst + stt + exc + stamp}
