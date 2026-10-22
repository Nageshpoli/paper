"""
AIStockTrade — Paper Trading Dashboard
Run: streamlit run app/dashboard/app.py
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from app.config import get_settings
from app.db.models import (
    CompletedTrade, Position, Signal, ScannerRow, VirtualAccount,
    UniverseConstituent,
)
from app.db.session import SessionLocal, init_db
from app.kite.auth import _auth
from app.kite.data import refresh_universe, warmup_history

IST = ZoneInfo("Asia/Kolkata")

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AIStockTrade — Paper",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Init DB once ───────────────────────────────────────────────────────────
init_db()

# ── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .metric-label { font-size: 0.75rem; color: #9ca3af; }
  .green { color: #10b981; }
  .red   { color: #ef4444; }
  .neutral { color: #6b7280; }
  .pill-green  { background:#064e3b; color:#6ee7b7; padding:2px 8px;
                 border-radius:12px; font-size:0.7rem; font-weight:600; }
  .pill-red    { background:#7f1d1d; color:#fca5a5; padding:2px 8px;
                 border-radius:12px; font-size:0.7rem; font-weight:600; }
  .pill-yellow { background:#78350f; color:#fcd34d; padding:2px 8px;
                 border-radius:12px; font-size:0.7rem; font-weight:600; }
  .pill-gray   { background:#1f2937; color:#9ca3af; padding:2px 8px;
                 border-radius:12px; font-size:0.7rem; font-weight:600; }
  .big-badge   { font-size:1.4rem; font-weight:700; }
  [data-testid="stMetric"] { background:#111827; border-radius:8px;
                              padding:12px; border:1px solid #1f2937; }
</style>
""", unsafe_allow_html=True)


def _seed_account():
    cfg = get_settings()
    db = SessionLocal()
    try:
        if not db.query(VirtualAccount).first():
            db.add(VirtualAccount(
                cash=cfg.virtual_capital,
                starting_capital=cfg.virtual_capital,
                peak_equity=cfg.virtual_capital,
            ))
            db.commit()
    finally:
        db.close()


# ── Engine singleton (one per Streamlit process) ───────────────────────────
@st.cache_resource
def _get_engine():
    from app.engine.runner import engine
    return engine


# ── Sidebar ────────────────────────────────────────────────────────────────
def render_sidebar():
    engine = _get_engine()
    st.sidebar.markdown("## 📈 AIStockTrade")
    st.sidebar.markdown("**🔴 PAPER TRADING ONLY**")
    st.sidebar.markdown("---")

    # Auth status
    authenticated = _auth.is_authenticated()
    if authenticated:
        st.sidebar.success("✅ Zerodha connected")
    else:
        login_url = _auth.get_login_url()
        st.sidebar.warning("⚠️ Not logged in to Zerodha")
        st.sidebar.markdown(f"[🔐 Login to Zerodha]({login_url})")

    st.sidebar.markdown("---")

    # Engine controls
    if engine.state.running:
        st.sidebar.markdown(f"**Engine:** 🟢 LIVE")
        if st.sidebar.button("⏹ Stop Engine", use_container_width=True):
            engine.stop()
            st.rerun()
        if st.sidebar.button("🚨 KILL SWITCH", use_container_width=True, type="primary"):
            engine.activate_kill_switch()
            st.rerun()
    else:
        st.sidebar.markdown(f"**Engine:** ⚫ Stopped")
        if authenticated:
            if st.sidebar.button("▶ Start Engine", use_container_width=True, type="primary"):
                engine.start()
                time.sleep(1)
                st.rerun()

    if engine.state.message:
        st.sidebar.caption(engine.state.message)

    st.sidebar.markdown("---")

    # Setup actions
    st.sidebar.markdown("**Setup**")
    db = SessionLocal()
    try:
        uni_count = db.query(UniverseConstituent).count()
    finally:
        db.close()

    if st.sidebar.button(f"🔄 Load Universe {'✅' if uni_count > 0 else '⬜'}",
                         use_container_width=True, disabled=not authenticated):
        with st.sidebar:
            with st.spinner("Loading Nifty 500…"):
                try:
                    res = refresh_universe()
                    st.success(f"Loaded {res['total']} stocks")
                except Exception as e:
                    st.error(str(e))
        st.rerun()

    db2 = SessionLocal()
    try:
        from app.db.models import MarketCandle
        candle_count = db2.query(MarketCandle).count()
    finally:
        db2.close()
    candle_label = f"📥 Warmup History {'✅' if candle_count > 10000 else '⬜'} ({candle_count:,} candles)"
    if st.sidebar.button(candle_label, use_container_width=True, disabled=not authenticated):
        with st.sidebar:
            prog = st.progress(0, text="Fetching historical candles…")
            def cb(done, total):
                prog.progress(done / total, text=f"{done}/{total} symbols")
            try:
                res = warmup_history(cb)
                prog.empty()
                st.success(f"Done — {res['completed']} symbols")
            except Exception as e:
                prog.empty()
                st.error(str(e))
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.caption(f"Last refresh: {datetime.now(IST).strftime('%H:%M:%S')}")


# ── Tab: Market ─────────────────────────────────────────────────────────────
def tab_market():
    engine = _get_engine()
    ms = engine._market.state

    col1, col2, col3, col4 = st.columns(4)
    direction_color = {"BULLISH": "green", "BEARISH": "red", "NEUTRAL": "neutral"}[ms.direction]
    col1.metric("Market Direction", ms.direction)
    col2.metric("Nifty 50", f"₹{ms.nifty_price:,.2f}",
                delta=f"{ms.nifty_change_pct:+.2f}%")
    col3.metric("VWAP", f"₹{ms.nifty_vwap:,.2f}" if ms.nifty_vwap else "—")
    col4.metric("vs VWAP", f"{ms.nifty_vs_vwap_pct:+.2f}%" if ms.nifty_vwap else "—")

    st.markdown("---")
    st.subheader("Sector Rankings")

    states = engine._sectors.all_states()
    if not states:
        st.info("Sector data will appear once the engine is running and the market is open.")
        return

    rows = []
    for s in states:
        rows.append({
            "Rank": s.rank,
            "Sector": s.name,
            "Price": f"₹{s.price:,.2f}" if s.price else "—",
            "Change %": f"{s.change_pct:+.2f}%" if s.change_pct else "—",
            "vs VWAP %": f"{s.vs_vwap_pct:+.2f}%" if s.vs_vwap_pct else "—",
            "Rel. Strength": f"{s.relative_strength:+.2f}%" if s.relative_strength else "—",
            "Score": f"{s.score:.2f}" if s.score else "—",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    active = engine._sectors.top_sectors(ms.direction)
    if active:
        st.success(f"**Active sectors ({ms.direction}):** {', '.join(active)}")
    else:
        st.warning("No qualifying sectors for current market direction.")


# ── Tab: Scanner ────────────────────────────────────────────────────────────
def tab_scanner():
    db = SessionLocal()
    try:
        rows = db.query(ScannerRow).order_by(
            ScannerRow.rvol.desc().nullslast()
        ).all()
    finally:
        db.close()

    if not rows:
        st.info("Scanner results appear during market hours (9:15–15:30 IST) once the engine is running.")
        st.markdown("""
        **How the ORB Scanner works:**
        1. **9:15–9:30** — Opening Range is built from live ticks
        2. **9:30–14:30** — Each completed 5-min candle is evaluated
        3. **Filters:** Market direction → Top sectors → VWAP position → RVOL ≥ 1.5 → Breakout above/below OR
        4. **Signal** → Risk check → Paper order placed
        """)
        return

    signal_rows = [r for r in rows if r.status == "SIGNAL"]
    rejected_rows = [r for r in rows if r.status == "REJECTED"]
    st.caption(f"{len(signal_rows)} signals · {len(rejected_rows)} rejected · {len(rows)} total scanned")

    # Status filter
    status_filter = st.selectbox("Show", ["All", "SIGNAL", "REJECTED", "PENDING_FILL", "OPEN"])

    data = []
    for r in rows:
        if status_filter != "All" and r.status != status_filter:
            continue
        data.append({
            "Symbol": r.symbol,
            "Sector": r.sector,
            "Price": f"₹{r.price:.2f}" if r.price else "—",
            "Chg %": f"{r.change_pct:+.2f}%" if r.change_pct is not None else "—",
            "OR High": f"{r.or_high:.2f}" if r.or_high else "—",
            "OR Low": f"{r.or_low:.2f}" if r.or_low else "—",
            "VWAP": f"{r.vwap:.2f}" if r.vwap else "—",
            "RVOL": f"{r.rvol:.2f}" if r.rvol else "—",
            "Signal": r.signal or "—",
            "Stop": f"{r.stop_loss:.2f}" if r.stop_loss else "—",
            "Target": f"{r.target:.2f}" if r.target else "—",
            "R:R": f"{r.risk_reward:.2f}" if r.risk_reward else "—",
            "Status": r.status,
            "Reason": r.reason,
        })

    if data:
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
    else:
        st.info("No rows match filter.")


# ── Tab: Portfolio ──────────────────────────────────────────────────────────
def tab_portfolio():
    db = SessionLocal()
    try:
        account = db.query(VirtualAccount).first()
        positions = db.query(Position).filter_by(status="OPEN").all()
    finally:
        db.close()

    if not account:
        st.warning("No account found.")
        return

    # Unrealized P&L
    unrealized = sum(p.unrealized_pnl or 0 for p in positions)
    equity = (account.cash or 0) + unrealized
    today_realized = _today_realized()
    win_rate = (account.winning_trades / account.total_trades * 100
                if account.total_trades else 0)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Starting Capital", f"₹{account.starting_capital:,.0f}")
    c2.metric("Available Cash", f"₹{account.cash:,.0f}")
    c3.metric("Current Equity", f"₹{equity:,.0f}",
              delta=f"₹{equity - account.starting_capital:+,.0f}")
    c4.metric("Max Drawdown", f"{account.max_drawdown_pct:.2f}%")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Realized P&L", f"₹{account.realized_pnl:+,.0f}")
    c6.metric("Unrealized P&L", f"₹{unrealized:+,.0f}")
    c7.metric("Today P&L", f"₹{today_realized:+,.0f}")
    c8.metric("Win Rate", f"{win_rate:.1f}%",
              delta=f"{account.total_trades} trades")

    st.markdown("---")
    st.subheader("Open Positions")
    if not positions:
        st.info("No open positions.")
    else:
        rows = []
        for p in positions:
            rows.append({
                "Symbol": p.symbol,
                "Sector": p.sector,
                "Side": p.side,
                "Qty": p.qty,
                "Entry": f"₹{p.fill_price:.2f}",
                "LTP": f"₹{p.last_price:.2f}" if p.last_price else "—",
                "Stop": f"₹{p.stop_loss:.2f}",
                "Target": f"₹{p.target:.2f}",
                "Unreal. P&L": f"₹{p.unrealized_pnl:+.2f}",
                "Since": p.entry_time.strftime("%H:%M") if p.entry_time else "—",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ── Tab: Trades ──────────────────────────────────────────────────────────────
def tab_trades():
    db = SessionLocal()
    try:
        trades = db.query(CompletedTrade).order_by(CompletedTrade.exit_time.desc()).limit(200).all()
    finally:
        db.close()

    if not trades:
        st.info("No completed trades yet.")
        return

    today = date.today()
    day_filter = st.selectbox("Period", ["Today", "This Week", "All"])

    rows = []
    for t in trades:
        if day_filter == "Today" and (not t.entry_time or t.entry_time.date() != today):
            continue
        if day_filter == "This Week":
            week_start = today - timedelta(days=today.weekday())
            if not t.entry_time or t.entry_time.date() < week_start:
                continue
        rows.append({
            "Symbol": t.symbol,
            "Sector": t.sector,
            "Side": t.side,
            "Qty": t.qty,
            "Entry": f"₹{t.entry_price:.2f}",
            "Exit": f"₹{t.exit_price:.2f}",
            "Entry Time": t.entry_time.strftime("%d %b %H:%M") if t.entry_time else "—",
            "Exit Time": t.exit_time.strftime("%d %b %H:%M") if t.exit_time else "—",
            "Gross P&L": f"₹{t.gross_pnl:+.2f}",
            "Charges": f"₹{t.brokerage + t.other_charges:.2f}",
            "Net P&L": f"₹{t.net_pnl:+.2f}",
            "Exit Reason": t.exit_reason,
        })

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
        net_total = sum(t.net_pnl for t in trades
                       if (day_filter == "All" or
                           (day_filter == "Today" and t.entry_time and t.entry_time.date() == today)))
        st.metric("Net P&L (shown period)", f"₹{net_total:+,.2f}")
    else:
        st.info("No trades for selected period.")

    # Signals log
    st.markdown("---")
    st.subheader("Signal Log")
    db2 = SessionLocal()
    try:
        signals = db2.query(Signal).order_by(Signal.created_at.desc()).limit(50).all()
    finally:
        db2.close()
    sig_rows = []
    for s in signals:
        sig_rows.append({
            "Symbol": s.symbol, "Action": s.action,
            "Price": f"₹{s.signal_price:.2f}",
            "Stop": f"₹{s.stop_loss:.2f}", "Target": f"₹{s.target:.2f}",
            "R:R": f"{s.risk_reward:.2f}" if s.risk_reward else "—",
            "Status": s.status, "Reason": s.reason,
            "Time": s.created_at.strftime("%H:%M:%S") if s.created_at else "—",
        })
    if sig_rows:
        st.dataframe(pd.DataFrame(sig_rows), use_container_width=True, hide_index=True)


# ── Tab: Backtest ────────────────────────────────────────────────────────────
def tab_backtest():
    from app.backtest.engine import run_backtest

    st.subheader("Backtest — ORB Strategy")
    st.info("Uses historical 5-min candles from DB. Run 'Warmup History' in the sidebar first.")

    c1, c2 = st.columns(2)
    start_date = c1.date_input("Start Date", value=date.today() - timedelta(days=90))
    end_date = c2.date_input("End Date", value=date.today() - timedelta(days=1))

    if st.button("▶ Run Backtest", type="primary"):
        prog = st.progress(0, text="Running backtest…")
        status = st.empty()

        def cb(done, total):
            prog.progress(done / total, text=f"Day {done}/{total}")

        try:
            result = run_backtest(str(start_date), str(end_date), progress_cb=cb)
        except Exception as e:
            st.error(f"Backtest failed: {e}")
            return
        prog.empty()
        status.empty()

        if result.total_trades == 0:
            st.warning("No trades generated. Check that history data is loaded for this period.")
            if result.notes:
                st.info(result.notes)
            return

        # Metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Trades", result.total_trades)
        col2.metric("Win Rate", f"{result.win_rate:.1f}%")
        col3.metric("Net P&L", f"₹{result.total_pnl:+,.2f}")
        col4.metric("Max Drawdown", f"{result.max_drawdown_pct:.2f}%")

        col5, col6, col7, col8 = st.columns(4)
        col5.metric("Profit Factor", f"{result.profit_factor:.2f}")
        col6.metric("Expectancy", f"₹{result.expectancy:+.2f}")
        col7.metric("Avg Win", f"₹{result.avg_win:+.2f}")
        col8.metric("Avg Loss", f"₹{result.avg_loss:+.2f}")

        if result.notes:
            st.caption(result.notes)

        # Equity curve
        if result.equity_curve:
            eq_df = pd.DataFrame(result.equity_curve)
            eq_df["date"] = pd.to_datetime(eq_df["date"])
            st.markdown("**Equity Curve**")
            st.line_chart(eq_df.set_index("date")["equity"])

        # Trade log
        if result.trades:
            st.markdown("**Trade Log**")
            trade_data = [{
                "Date": t.entry_date,
                "Symbol": t.symbol,
                "Sector": t.sector,
                "Side": t.side,
                "Qty": t.qty,
                "Entry": f"₹{t.entry_price:.2f}",
                "Exit": f"₹{t.exit_price:.2f}",
                "OR High": f"₹{t.or_high:.2f}" if t.or_high else "—",
                "OR Low": f"₹{t.or_low:.2f}" if t.or_low else "—",
                "RVOL": f"{t.rvol:.2f}" if t.rvol else "—",
                "Gross P&L": f"₹{t.gross_pnl:+.2f}",
                "Net P&L": f"₹{t.net_pnl:+.2f}",
                "Exit Reason": t.exit_reason,
            } for t in result.trades]
            st.dataframe(pd.DataFrame(trade_data), use_container_width=True, hide_index=True)


# ── Tab: Settings ────────────────────────────────────────────────────────────
def tab_settings():
    cfg = get_settings()
    st.subheader("Strategy Parameters")
    st.info("Edit `.env` file to change these permanently. Changes here only affect the current session.")

    st.markdown("""
| Parameter | Value | Description |
|---|---|---|
| Virtual Capital | ₹{:,.0f} | Starting paper cash |
| Risk Per Trade | {:.1%} | % of equity risked per trade |
| Max Risk Per Trade | ₹{:,.0f} | Hard cap in rupees |
| Reward:Risk | {:.1f}× | Target R:R ratio |
| Max Trades/Day | {} | Max new entries per day |
| Max Open Positions | {} | Concurrent positions |
| Max Position Notional | ₹{:,.0f} | Max ₹ per single trade |
| RVOL Minimum | {:.1f}× | Relative volume threshold |
| Breakout Buffer | {:.2%} | % above ORH / below ORL |
| Entry Cutoff | {} | No new entries after this |
| EOD Close | {} | Force close by this time |
""".format(
        cfg.virtual_capital,
        cfg.risk_per_trade_pct,
        cfg.max_risk_per_trade,
        cfg.reward_to_risk,
        cfg.max_trades_per_day,
        cfg.max_open_positions,
        cfg.max_position_notional,
        cfg.rvol_min,
        cfg.breakout_buffer_pct,
        cfg.entry_cutoff_time,
        cfg.eod_close_time,
    ))


# ── Helpers ────────────────────────────────────────────────────────────────
def _today_realized() -> float:
    today = date.today()
    db = SessionLocal()
    try:
        trades = db.query(CompletedTrade).filter(
            CompletedTrade.entry_time >= datetime(today.year, today.month, today.day)
        ).all()
        return sum(t.net_pnl for t in trades)
    finally:
        db.close()


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    _seed_account()
    render_sidebar()

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Market", "🔍 Scanner", "💼 Portfolio", "📋 Trades", "⚙ Backtest", "⚙ Settings"
    ])

    with tab1:
        tab_market()
    with tab2:
        tab_scanner()
    with tab3:
        tab_portfolio()
    with tab4:
        tab_trades()
    with tab5:
        tab_backtest()
    with tab6:
        tab_settings()

    # Auto-refresh every 10 seconds during market hours
    now = datetime.now(IST)
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    if market_open <= now <= market_close and now.weekday() < 5:
        time.sleep(10)
        st.rerun()


main()
