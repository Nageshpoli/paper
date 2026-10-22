from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.db.models import UniverseConstituent
from app.db.session import SessionLocal
from app.engine.paper_broker import PaperBroker
from app.engine.risk import RiskManager
from app.kite.auth import _auth
from app.kite.data import get_ohlc, get_ltp
from app.kite.feed import KiteFeed
from app.market.candles import CandleBuilder
from app.market.market_analyzer import MarketAnalyzer, NIFTY50_SYMBOL, NIFTYBANK_SYMBOL
from app.market.scanner import StockScanner, load_hist_volumes, persist_scan_row
from app.market.sector_analyzer import SectorAnalyzer
from app.strategy.orb import evaluate_orb
from app.db.models import Signal, ScannerRow

IST = ZoneInfo("Asia/Kolkata")
log = logging.getLogger(__name__)


@dataclass
class EngineState:
    running: bool = False
    kill_switch: bool = False
    message: str = "Not started"
    started_at: datetime | None = None
    last_tick_at: datetime | None = None
    feed_connected: bool = False
    trades_today: int = 0


class TradingEngine:
    """
    Main paper-trading engine. Runs in background threads.
    Dashboard reads shared state and DB.
    """

    def __init__(self):
        self.state = EngineState()
        self._broker = PaperBroker()
        self._risk = RiskManager()
        self._market = MarketAnalyzer()
        self._sectors = SectorAnalyzer()
        self._stock_scanners: dict[str, StockScanner] = {}
        self._token_to_symbol: dict[int, str] = {}
        self._symbol_to_token: dict[str, int] = {}
        self._feed: KiteFeed | None = None
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    def start(self) -> None:
        if self.state.running:
            return
        if not _auth.is_authenticated():
            self.state.message = "Not authenticated — log in first"
            return
        t = threading.Thread(target=self._run, daemon=True, name="trading-engine")
        t.start()
        self._thread = t

    def stop(self) -> None:
        self.state.running = False
        self.state.message = "Stopped by user"
        if self._feed:
            self._feed.stop()

    def activate_kill_switch(self) -> None:
        self.state.kill_switch = True
        self.state.running = False
        self.state.message = "KILL SWITCH activated"
        if self._feed:
            self._feed.stop()

    # ------------------------------------------------------------------
    def _run(self) -> None:
        self.state.running = True
        self.state.started_at = datetime.now(IST)
        self.state.message = "Starting up…"
        try:
            self._setup()
            self.state.message = "Live — scanning market"
        except Exception as exc:
            self.state.message = f"Startup failed: {exc}"
            self.state.running = False
            log.exception("Engine startup failed: %s", exc)

    def _setup(self) -> None:
        cfg = get_settings()
        db = SessionLocal()
        try:
            constituents = db.query(UniverseConstituent).filter(
                UniverseConstituent.instrument_token.isnot(None)
            ).all()
        finally:
            db.close()

        if not constituents:
            raise RuntimeError("Universe not loaded. Run 'Load Universe' first.")

        # Fetch previous close for all symbols + indices
        all_symbols = [f"NSE:{c.symbol}" for c in constituents]
        index_syms = [NIFTY50_SYMBOL, NIFTYBANK_SYMBOL]
        sector_index_syms = self._sectors.all_index_symbols()

        all_fetch = all_symbols + index_syms + [s for s in sector_index_syms if s]
        ohlc_data = get_ohlc(all_fetch[:500])  # Kite allows up to 500 per call

        # Init market analyzer
        nifty_ohlc = ohlc_data.get(NIFTY50_SYMBOL, {})
        self._market.set_prev_close(nifty_ohlc.get("ohlc", {}).get("close", 0))

        # Init sector analyzer
        self._sectors.initialize()
        for sector_idx in sector_index_syms:
            if sector_idx:
                d = ohlc_data.get(sector_idx, {})
                sector_name = self._sectors._symbol_to_sector(sector_idx)
                if sector_name:
                    self._sectors.set_prev_close(sector_name, d.get("ohlc", {}).get("close", 0))

        # Init stock scanners
        for c in constituents:
            prev = ohlc_data.get(f"NSE:{c.symbol}", {}).get("ohlc", {}).get("close", 0)
            hist_vols = load_hist_volumes(c.symbol)
            self._stock_scanners[c.symbol] = StockScanner(
                symbol=c.symbol, sector=c.sector,
                prev_close=prev, hist_volumes_by_slot=hist_vols,
            )
            self._token_to_symbol[c.instrument_token] = c.symbol
            self._symbol_to_token[c.symbol] = c.instrument_token

        # Build token subscription list
        stock_tokens = [c.instrument_token for c in constituents]
        # Add index tokens if available
        index_token_syms = index_syms + [s for s in sector_index_syms if s]
        index_tokens = []
        for sym in index_token_syms:
            d = ohlc_data.get(sym, {})
            tok = d.get("instrument_token")
            if tok:
                self._token_to_symbol[tok] = sym
                index_tokens.append(tok)

        all_tokens = list(set(stock_tokens + index_tokens))
        self._feed = KiteFeed(self._on_tick)
        self._feed.start(all_tokens)
        self.state.feed_connected = True

    def _on_tick(self, tick: dict) -> None:
        if not self.state.running or self.state.kill_switch:
            return

        self.state.last_tick_at = datetime.now(IST)
        tok = tick.get("instrument_token")
        price = tick.get("last_price", 0)
        volume = tick.get("last_quantity", 0) or tick.get("volume", 0)
        ts = tick.get("timestamp") or datetime.now(IST)

        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=IST)

        symbol = self._token_to_symbol.get(tok)
        if not symbol:
            return

        # Route to correct handler
        if symbol == NIFTY50_SYMBOL:
            self._market.on_tick(price, volume, ts)
            return

        if symbol in self._sectors._symbol_to_sector.__self__._map or True:
            # Check if it's a sector index
            sect_name = self._sectors._symbol_to_sector(symbol)
            if sect_name:
                self._sectors.on_tick(symbol, price, volume, ts)
                return

        # Stock tick
        scanner = self._stock_scanners.get(symbol)
        if not scanner:
            return

        completed_candle = scanner.on_tick(price, volume, ts)
        if not completed_candle:
            return

        self._on_candle(symbol, scanner, completed_candle)

        # Update exits on every candle
        ltp_map = {s: sc._last_price for s, sc in self._stock_scanners.items() if sc._last_price}
        self._broker.check_exits(ltp_map)

        # EOD close
        cfg = get_settings()
        now_time = datetime.now(IST).time()
        eod = _parse_time(cfg.eod_close_time)
        if now_time >= eod:
            self._broker.check_exits(ltp_map, reason="EOD")

    def _on_candle(self, symbol: str, scanner: StockScanner, candle) -> None:
        scan = scanner.on_candle_close(candle)
        market_dir = self._market.classify()
        self._sectors.compute_rankings(self._market.state.nifty_change_pct)
        active = self._sectors.top_sectors(market_dir)

        signal, reason = evaluate_orb(scan, market_dir, active)

        # Persist scan row
        persist_scan_row({
            "symbol": symbol,
            "sector": scanner.sector,
            "price": scan.get("price"),
            "change_pct": scan.get("change_pct"),
            "or_high": scan.get("or_high"),
            "or_low": scan.get("or_low"),
            "vwap": scan.get("vwap"),
            "rvol": scan.get("rvol"),
            "signal": signal.action if signal else None,
            "stop_loss": signal.stop_loss if signal else None,
            "target": signal.target if signal else None,
            "risk_reward": signal.risk_reward if signal else None,
            "status": "SIGNAL" if signal else "REJECTED",
            "reason": reason,
        })

        if not signal:
            return

        ok, block_reason = self._risk.can_trade(signal)
        if not ok:
            log.info("Signal blocked for %s: %s", symbol, block_reason)
            _record_signal(signal, "REJECTED", block_reason)
            return

        pos = self._broker.place_order(signal)
        if pos:
            _record_signal(signal, "FILLED", reason)
            self.state.trades_today += 1
        else:
            _record_signal(signal, "REJECTED", "Order not filled (qty=0 or cash)")


def _record_signal(signal, status: str, reason: str) -> None:
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        db.add(Signal(
            symbol=signal.symbol, sector=signal.sector, action=signal.action,
            signal_price=signal.signal_price,
            or_high=signal.or_high, or_low=signal.or_low,
            vwap=signal.vwap, rvol=signal.rvol,
            market_direction="", sector_direction="",
            stop_loss=signal.stop_loss, target=signal.target,
            risk_reward=signal.risk_reward,
            status=status, reason=reason,
        ))
        db.commit()
    finally:
        db.close()


def _parse_time(t: str) -> time:
    h, m = t.split(":")
    return time(int(h), int(m))


# Module-level singleton
engine = TradingEngine()
