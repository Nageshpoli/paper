from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import BacktestRun, MarketCandle, UniverseMember, UniverseSnapshot
from app.market.candles import Candle
from app.market.indicators import atr, market_direction, relative_volume
from app.strategies.registry import strategy_registry

IST = ZoneInfo("Asia/Kolkata")
NIFTY50 = "IDX:NIFTY 50"


class BacktestEngine:
    """
    Next-bar simulator. For each completed 5-minute candle in the date range:
      - fetch point-in-time universe (nearest snapshot at or before bar date)
      - compute filters (RVOL, ATR, market/sector direction)
      - call strategy.evaluate()
      - simulate fill on the next candle's open
      - manage virtual positions with stop/target
    """

    def run(self, db: Session, run_id: int) -> None:
        run = db.get(BacktestRun, run_id)
        if not run:
            return
        run.status = "RUNNING"
        db.commit()
        try:
            metrics, trade_log = self._simulate(db, run)
            run.metrics = json.dumps(metrics)
            run.trade_log = json.dumps(trade_log)
            run.status = "DONE"
        except Exception as exc:
            run.status = "FAILED"
            run.metrics = json.dumps({"error": str(exc)})
        db.commit()

    def _simulate(self, db: Session, run: BacktestRun) -> tuple[dict, list[dict]]:
        settings = get_settings()
        strategy = strategy_registry.get(run.strategy_name)
        start = datetime.fromisoformat(run.start_date)
        end = datetime.fromisoformat(run.end_date)
        universe = self._universe_at(db, run.universe_name, start)
        if not universe:
            return {"error": "No universe snapshot found for start date"}, []

        cash = settings.virtual_capital
        positions: dict[str, dict] = {}
        trades: list[dict] = []
        daily_loss = 0.0
        entries_today = 0
        last_session_date = None

        symbols = [m.symbol for m in universe]
        all_bars = self._load_candles(db, symbols + [NIFTY50], start, end)

        unique_days = sorted({b.timestamp.date() for bars in all_bars.values() for b in bars
                               if start.date() <= b.timestamp.date() <= end.date()})

        for session_date in unique_days:
            if session_date != last_session_date:
                daily_loss = 0.0
                entries_today = 0
                strategy.opening.clear()
                last_session_date = session_date

            for symbol in symbols:
                bars_today = [b for b in all_bars.get(symbol, []) if b.timestamp.date() == session_date]
                for bar in bars_today:
                    candle = _db_to_candle(bar)
                    strategy.observe_opening(candle)
                    if symbol in positions:
                        pos = positions[symbol]
                        hit = self._check_exit(pos, bar.close)
                        if hit:
                            pnl = self._close(pos, bar.close, hit, trades)
                            cash += bar.close * pos["qty"]
                            daily_loss += min(0.0, pnl)
                            del positions[symbol]

                daily_bars = [b for b in all_bars.get(symbol, []) if b.interval == "day"
                               and b.timestamp.date() <= session_date]
                five_bars = [b for b in all_bars.get(symbol, []) if b.interval == "5minute"
                              and b.timestamp.date() <= session_date]
                daily_atr = atr(daily_bars[-20:]) if daily_bars else None

                last_five = [b for b in five_bars if b.timestamp.date() == session_date]
                if not last_five:
                    continue
                current_bar = last_five[-1]
                rv = relative_volume(five_bars, current_bar)

                market_five = [b for b in all_bars.get(NIFTY50, []) if b.interval == "5minute"
                                and b.timestamp.date() == session_date]
                if not market_five:
                    continue
                mdir = market_direction(market_five, market_five[-1].close)
                if mdir in (None, "NEUTRAL"):
                    continue

                member_data = next((m for m in universe if m.symbol == symbol), None)
                if not member_data or not member_data.sector_index:
                    continue
                sector_sym = "IDX:" + member_data.sector_index
                sector_five = [b for b in all_bars.get(sector_sym, []) if b.interval == "5minute"
                                and b.timestamp.date() == session_date]
                if not sector_five:
                    continue
                sdir = market_direction(sector_five, sector_five[-1].close)
                if sdir in (None, "NEUTRAL"):
                    continue

                if symbol in positions:
                    continue
                if entries_today >= settings.max_entries_per_day:
                    continue
                if daily_loss <= -settings.max_daily_loss:
                    continue
                if len(positions) >= settings.max_open_positions:
                    continue

                signal = strategy.evaluate(
                    _db_to_candle(current_bar),
                    relative_volume=rv,
                    atr=daily_atr,
                    market_direction=mdir,
                    sector_direction=sdir,
                    tick_size=member_data.tick_size,
                )
                if signal.action == "HOLD":
                    continue

                next_open = self._next_open(all_bars.get(symbol, []), current_bar)
                if next_open is None:
                    continue
                fill = next_open
                risk = abs(fill - (signal.stop_loss or fill))
                if risk <= 0 or daily_atr is None:
                    continue
                qty = int((cash * settings.risk_per_trade_pct) / risk)
                if qty <= 0:
                    continue
                notional = qty * fill
                if notional > settings.max_position_notional or cash < notional:
                    continue
                cash -= notional
                entries_today += 1
                positions[symbol] = {
                    "symbol": symbol, "side": signal.action, "qty": qty,
                    "entry": fill, "stop": signal.stop_loss, "target": signal.target,
                    "entry_date": str(session_date),
                }

        for symbol, pos in list(positions.items()):
            last_bar = all_bars.get(symbol, [])
            price = last_bar[-1].close if last_bar else pos["entry"]
            self._close(pos, price, "End of backtest", trades)
            cash += price * pos["qty"]

        return self._compute_metrics(trades, settings.virtual_capital), trades

    @staticmethod
    def _universe_at(db: Session, universe_name: str, at: datetime) -> list[UniverseMember]:
        snap = db.query(UniverseSnapshot).filter(
            UniverseSnapshot.universe_name == universe_name,
            UniverseSnapshot.effective_date <= str(at.date()),
        ).order_by(UniverseSnapshot.effective_date.desc()).first()
        if not snap:
            return []
        return db.query(UniverseMember).filter_by(version=snap.version).all()

    @staticmethod
    def _load_candles(db: Session, symbols: list[str],
                      start: datetime, end: datetime) -> dict[str, list[MarketCandle]]:
        rows = db.query(MarketCandle).filter(
            MarketCandle.symbol.in_(symbols),
            MarketCandle.timestamp >= start,
            MarketCandle.timestamp <= end + timedelta(days=1),
        ).order_by(MarketCandle.symbol, MarketCandle.interval, MarketCandle.timestamp).all()
        result: dict[str, list[MarketCandle]] = {}
        for row in rows:
            result.setdefault(row.symbol, []).append(row)
        return result

    @staticmethod
    def _check_exit(pos: dict, price: float) -> str | None:
        if pos["stop"] and pos["side"] == "BUY" and price <= pos["stop"]:
            return "Stop loss"
        if pos["stop"] and pos["side"] == "SHORT" and price >= pos["stop"]:
            return "Stop loss"
        if pos["target"] and pos["side"] == "BUY" and price >= pos["target"]:
            return "Target"
        if pos["target"] and pos["side"] == "SHORT" and price <= pos["target"]:
            return "Target"
        return None

    @staticmethod
    def _close(pos: dict, price: float, reason: str, trades: list) -> float:
        if pos["side"] == "BUY":
            pnl = (price - pos["entry"]) * pos["qty"]
        else:
            pnl = (pos["entry"] - price) * pos["qty"]
        trades.append({
            "symbol": pos["symbol"], "side": pos["side"], "qty": pos["qty"],
            "entry": pos["entry"], "exit": price, "pnl": pnl,
            "entry_date": pos.get("entry_date"), "exit_reason": reason,
        })
        return pnl

    @staticmethod
    def _next_open(bars: list[MarketCandle], current: MarketCandle) -> float | None:
        for bar in bars:
            if bar.interval == "5minute" and bar.timestamp > current.timestamp:
                return float(bar.open)
        return None

    @staticmethod
    def _compute_metrics(trades: list[dict], initial_capital: float) -> dict:
        if not trades:
            return {"total_trades": 0, "win_rate": 0.0, "total_pnl": 0.0,
                    "expectancy": 0.0, "profit_factor": 0.0, "max_drawdown_pct": 0.0}
        pnls = [t["pnl"] for t in trades]
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p <= 0]
        gross_profit = sum(winners) if winners else 0.0
        gross_loss = abs(sum(losers)) if losers else 0.0
        peak = equity = initial_capital
        max_dd = 0.0
        for p in pnls:
            equity += p
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100 if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        return {
            "total_trades": len(trades),
            "win_rate": round(len(winners) / len(trades) * 100, 1),
            "total_pnl": round(sum(pnls), 2),
            "expectancy": round(sum(pnls) / len(trades), 2),
            "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0.0,
            "max_drawdown_pct": round(max_dd, 2),
        }


def _db_to_candle(bar: MarketCandle) -> Candle:
    ts = bar.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=IST)
    return Candle(bar.symbol, ts, float(bar.open), float(bar.high),
                  float(bar.low), float(bar.close), int(bar.volume or 0))
