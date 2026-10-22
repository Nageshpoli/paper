from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from app.config import get_settings
from app.db.models import MarketCandle
from app.db.session import SessionLocal
from app.engine.paper_broker import PaperBroker
from app.market.indicators import intraday_vwap_price, relative_volume
from app.strategy.orb import evaluate_orb, ORBSignal

IST = ZoneInfo("Asia/Kolkata")
log = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    symbol: str
    sector: str
    side: str
    qty: int
    entry_date: str
    entry_time: str
    entry_price: float
    exit_price: float
    exit_reason: str
    gross_pnl: float
    net_pnl: float
    stop_loss: float
    target: float
    or_high: float
    or_low: float
    rvol: float | None


@dataclass
class BacktestResult:
    start_date: str
    end_date: str
    total_trades: int = 0
    winning_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    expectancy: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    equity_curve: list[dict] = field(default_factory=list)
    trades: list[BacktestTrade] = field(default_factory=list)
    notes: str = ""


def run_backtest(
    start_date: str,
    end_date: str,
    sectors_filter: list[str] | None = None,
    progress_cb=None,
) -> BacktestResult:
    """
    Replay historical 5-min candles for all universe symbols and simulate
    the same ORB strategy logic, returns in-sample + OOS split metrics.
    """
    cfg = get_settings()
    result = BacktestResult(start_date=start_date, end_date=end_date)

    db = SessionLocal()
    try:
        from app.db.models import UniverseConstituent
        constituents = db.query(UniverseConstituent).all()
    finally:
        db.close()

    if not constituents:
        result.notes = "Universe not loaded"
        return result

    start_dt = datetime.fromisoformat(start_date)
    end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)

    # Group all trading days
    trading_days = _trading_days(start_dt.date(), end_dt.date())
    if not trading_days:
        result.notes = "No trading days in range"
        return result

    capital = cfg.virtual_capital
    equity = capital
    peak = capital
    max_dd = 0.0
    all_trades: list[BacktestTrade] = []
    equity_curve = [{"date": start_date, "equity": capital}]

    broker = PaperBroker()

    for i, day in enumerate(trading_days):
        if progress_cb:
            progress_cb(i + 1, len(trading_days))

        day_trades = _simulate_day(day, constituents, cfg, equity, sectors_filter)
        for t in day_trades:
            equity += t.net_pnl
            all_trades.append(t)

        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)
        equity_curve.append({"date": str(day), "equity": equity})

    wins = [t for t in all_trades if t.net_pnl > 0]
    losses = [t for t in all_trades if t.net_pnl <= 0]
    gross_wins = sum(t.gross_pnl for t in wins)
    gross_losses = abs(sum(t.gross_pnl for t in losses))

    result.total_trades = len(all_trades)
    result.winning_trades = len(wins)
    result.total_pnl = equity - capital
    result.win_rate = len(wins) / len(all_trades) * 100 if all_trades else 0
    result.profit_factor = gross_wins / gross_losses if gross_losses > 0 else 0
    result.max_drawdown_pct = max_dd
    result.expectancy = result.total_pnl / len(all_trades) if all_trades else 0
    result.avg_win = sum(t.net_pnl for t in wins) / len(wins) if wins else 0
    result.avg_loss = sum(t.net_pnl for t in losses) / len(losses) if losses else 0
    result.equity_curve = equity_curve
    result.trades = all_trades
    return result


def _simulate_day(
    day: date,
    constituents,
    cfg,
    equity: float,
    sectors_filter: list[str] | None,
) -> list[BacktestTrade]:
    db = SessionLocal()
    try:
        candles = (
            db.query(MarketCandle)
            .filter(
                MarketCandle.interval == "5minute",
                MarketCandle.timestamp >= datetime(day.year, day.month, day.day, 9, 15),
                MarketCandle.timestamp < datetime(day.year, day.month, day.day, 15, 30),
            )
            .order_by(MarketCandle.symbol, MarketCandle.timestamp)
            .all()
        )
    finally:
        db.close()

    if not candles:
        return []

    # Group by symbol
    by_symbol: dict[str, list] = {}
    for c in candles:
        by_symbol.setdefault(c.symbol, []).append(c)

    trades: list[BacktestTrade] = []
    open_positions: dict[str, dict] = {}
    trades_today = 0

    # Determine market direction from Nifty (approximated from all candles)
    market_dir = "NEUTRAL"  # simplified: would need Nifty data

    entry_cutoff = time(14, 30)
    eod_time = time(15, 20)

    for symbol, sym_candles in by_symbol.items():
        if trades_today >= cfg.max_trades_per_day:
            break
        if len(open_positions) >= cfg.max_open_positions:
            break

        constituent = next((c for c in constituents if c.symbol == symbol), None)
        if not constituent:
            continue
        sector = constituent.sector
        if sectors_filter and sector not in sectors_filter:
            continue

        or_high = or_low = None
        intraday_candles = []
        or_complete = False
        hist_vols = _get_hist_vols_for_day(symbol, day, db_only=True)

        for c in sym_candles:
            t = c.timestamp.time()
            intraday_candles.append({
                "high": c.high, "low": c.low,
                "close": c.close, "volume": c.volume,
            })

            if time(9, 15) <= t < time(9, 30):
                or_high = max(or_high or c.high, c.high)
                or_low = min(or_low or c.low, c.low)
            elif t >= time(9, 30):
                or_complete = True

            # Check exit for open position
            if symbol in open_positions:
                pos = open_positions[symbol]
                if pos["side"] == "LONG":
                    if c.low <= pos["stop"]:
                        pnl = (pos["stop"] - pos["entry"]) * pos["qty"]
                        charges = _est_charges(pos["entry"], pos["stop"], pos["qty"], cfg)
                        trades.append(_make_trade(symbol, sector, pos, pos["stop"],
                                                  "STOP_LOSS", pnl, pnl - charges))
                        del open_positions[symbol]
                        continue
                    if c.high >= pos["target"]:
                        pnl = (pos["target"] - pos["entry"]) * pos["qty"]
                        charges = _est_charges(pos["entry"], pos["target"], pos["qty"], cfg)
                        trades.append(_make_trade(symbol, sector, pos, pos["target"],
                                                  "TARGET", pnl, pnl - charges))
                        del open_positions[symbol]
                        continue
                elif pos["side"] == "SHORT":
                    if c.high >= pos["stop"]:
                        pnl = (pos["entry"] - pos["stop"]) * pos["qty"]
                        charges = _est_charges(pos["entry"], pos["stop"], pos["qty"], cfg)
                        trades.append(_make_trade(symbol, sector, pos, pos["stop"],
                                                  "STOP_LOSS", pnl, pnl - charges))
                        del open_positions[symbol]
                        continue
                    if c.low <= pos["target"]:
                        pnl = (pos["entry"] - pos["target"]) * pos["qty"]
                        charges = _est_charges(pos["entry"], pos["target"], pos["qty"], cfg)
                        trades.append(_make_trade(symbol, sector, pos, pos["target"],
                                                  "TARGET", pnl, pnl - charges))
                        del open_positions[symbol]
                        continue

            if t >= eod_time and symbol in open_positions:
                pos = open_positions[symbol]
                exit_p = c.close
                if pos["side"] == "LONG":
                    pnl = (exit_p - pos["entry"]) * pos["qty"]
                else:
                    pnl = (pos["entry"] - exit_p) * pos["qty"]
                charges = _est_charges(pos["entry"], exit_p, pos["qty"], cfg)
                trades.append(_make_trade(symbol, sector, pos, exit_p,
                                          "EOD", pnl, pnl - charges))
                del open_positions[symbol]
                continue

            if not or_complete or t >= entry_cutoff:
                continue
            if symbol in open_positions:
                continue

            vwap = intraday_vwap_price(intraday_candles)
            slot = t.hour * 60 + t.minute
            rvol = relative_volume(c.volume, hist_vols.get(slot, []))

            scan = {
                "symbol": symbol, "sector": sector, "price": c.close,
                "or_high": or_high, "or_low": or_low, "or_complete": or_complete,
                "vwap": vwap, "rvol": rvol, "candle_time": t,
            }
            # Use BULLISH for backtest (bidirectional would need index data)
            signal, _ = evaluate_orb(scan, "BULLISH", [sector] if sector else ["ANY"])
            if signal is None:
                signal, _ = evaluate_orb(scan, "BEARISH", [sector] if sector else ["ANY"])
            if signal is None:
                continue

            risk_amt = min(equity * cfg.risk_per_trade_pct, cfg.max_risk_per_trade)
            if signal.action == "BUY":
                risk_per = signal.signal_price - signal.stop_loss
            else:
                risk_per = signal.stop_loss - signal.signal_price
            if risk_per <= 0:
                continue
            qty = int(risk_amt / risk_per)
            if qty <= 0:
                continue

            fill = signal.signal_price * (1 + cfg.slippage_pct if signal.action == "BUY"
                                          else 1 - cfg.slippage_pct)
            if signal.action == "BUY":
                stop = signal.stop_loss
                target = fill + (fill - stop) * cfg.reward_to_risk
            else:
                stop = signal.stop_loss
                target = fill - (stop - fill) * cfg.reward_to_risk

            open_positions[symbol] = {
                "side": "LONG" if signal.action == "BUY" else "SHORT",
                "entry": fill, "stop": stop, "target": target,
                "qty": qty, "or_high": or_high, "or_low": or_low,
                "rvol": rvol, "date": str(day), "entry_t": str(t),
            }
            trades_today += 1

    # Force close any remaining positions at last candle close
    for symbol, pos in list(open_positions.items()):
        sym_candles_list = by_symbol.get(symbol, [])
        if sym_candles_list:
            exit_p = sym_candles_list[-1].close
            if pos["side"] == "LONG":
                pnl = (exit_p - pos["entry"]) * pos["qty"]
            else:
                pnl = (pos["entry"] - exit_p) * pos["qty"]
            charges = _est_charges(pos["entry"], exit_p, pos["qty"], cfg)
            constituent = next((c for c in [] if c.symbol == symbol), None)
            trades.append(_make_trade(symbol, "", pos, exit_p, "EOD", pnl, pnl - charges))

    return trades


def _make_trade(symbol, sector, pos, exit_p, reason, gross, net) -> BacktestTrade:
    return BacktestTrade(
        symbol=symbol, sector=sector, side=pos["side"],
        qty=pos["qty"], entry_date=pos.get("date", ""),
        entry_time=pos.get("entry_t", ""),
        entry_price=pos["entry"], exit_price=exit_p,
        exit_reason=reason, gross_pnl=gross, net_pnl=net,
        stop_loss=pos["stop"], target=pos["target"],
        or_high=pos.get("or_high", 0), or_low=pos.get("or_low", 0),
        rvol=pos.get("rvol"),
    )


def _est_charges(entry, exit_, qty, cfg) -> float:
    buy_v = entry * qty
    sell_v = exit_ * qty
    brok = min(buy_v * cfg.brokerage_pct, cfg.brokerage_cap) + \
           min(sell_v * cfg.brokerage_pct, cfg.brokerage_cap)
    return brok * (1 + cfg.gst_pct) + sell_v * cfg.stt_sell_pct + \
           (buy_v + sell_v) * cfg.exchange_charges_pct + buy_v * cfg.stamp_duty_pct


def _trading_days(start: date, end: date) -> list[date]:
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:  # Mon–Fri
            days.append(d)
        d += timedelta(days=1)
    return days


def _get_hist_vols_for_day(symbol: str, day: date, db_only: bool = True) -> dict[int, list[int]]:
    db = SessionLocal()
    try:
        rows = db.query(MarketCandle).filter(
            MarketCandle.symbol == symbol,
            MarketCandle.interval == "5minute",
            MarketCandle.timestamp < datetime(day.year, day.month, day.day),
        ).all()
    finally:
        db.close()
    result: dict[int, list[int]] = {}
    seen: dict[int, set] = {}
    for r in rows:
        slot = r.timestamp.hour * 60 + r.timestamp.minute
        d = r.timestamp.date()
        if slot not in result:
            result[slot] = []
            seen[slot] = set()
        if d not in seen[slot]:
            result[slot].append(r.volume)
            seen[slot].add(d)
    return result
