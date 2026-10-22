## Architecture Overview

### Module layers (top → bottom)

```
API (FastAPI routes)
  │
  ├── engine/runner.py    ← TradingEngine singleton (orchestrates all live trading)
  │     ├── paper_broker.py   (virtual cash + position management)
  │     ├── risk_manager.py   (pre-trade checks: capital, exposure, daily loss)
  │     └── session.py        (NSE daily lifecycle thread)
  │
  ├── strategies/
  │     ├── registry.py       (StrategyRegistry: name → Strategy instance)
  │     └── orb/strategy.py   (OpeningRangeBreakout)
  │
  ├── market/
  │     ├── scanner.py        (CandidateScanner: calls strategy.evaluate per 5-min candle)
  │     ├── live.py           (LiveMarketFeed: handles raw Kite ticks)
  │     ├── candles.py        (FiveMinuteBuilder: tick → 5-min candle)
  │     ├── indicators.py     (atr, relative_volume, vwap, ema, market_direction)
  │     └── universe.py       (UniverseService: Nifty 500/200 constituents)
  │
  ├── kite/
  │     ├── auth.py           (token storage/exchange)
  │     ├── client.py         (authenticated KiteConnect factory)
  │     ├── history.py        (HistoryWarmup: 45-day candle fetch)
  │     └── websocket.py      (KiteTicker setup)
  │
  └── db/
        ├── models.py         (all SQLAlchemy ORM models)
        └── session.py        (engine, SessionLocal, get_db)
```

### Key design decisions

**Strategy Registry**: `strategies/registry.py` is a plain dict mapping name → strategy instance. Adding a new strategy = create a file + one `register(...)` call. No dynamic imports, no plugin system complexity.

**No circular imports**: The registry imports from strategies. The scanner imports from the registry. The engine imports from the scanner. The API imports from the engine. Nothing imports upward.

**Separated frontend**: `frontend/` is served as a static mount. Zero build step — Alpine.js and Tailwind CSS come from CDN. `app.js` holds all state as a single Alpine component.

**Paper broker accounting**: Virtual cash is debited on entry (qty × fill price) and credited on exit. P&L is computed as (exit − entry) × qty for LONG and (entry − exit) × qty for SHORT. No costs are deducted in paper mode (costs would be subtracted in real mode).

**Backtest simulator**: Next-bar fill — signal fires on candle close, fill is simulated at the next candle's open price. This is the conservative industry-standard approach (avoids look-ahead bias).

### Data flow (live trading)

```
Kite WebSocket tick
  → LiveMarketFeed.on_tick()
  → FiveMinuteBuilder.add_tick()         (accumulate tick into candle)
  → [on candle close] CandidateScanner.evaluate()
  → ORBStrategy.observe_opening() / evaluate()
  → [if SIGNAL] PendingEntry queued
  → [on next tick] verify breakout still holds
  → TradingEngine.execute_signal()
  → RiskManager.pre_trade_check()        (5 checks in sequence)
  → PaperBroker.open_position()          (debit cash, write Position row)
```
