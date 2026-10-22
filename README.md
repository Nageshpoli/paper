# AIStockTrade — Paper Trading

Intraday paper trading app — ORB strategy on Nifty 500 using Zerodha Kite Connect.

> **PAPER TRADING ONLY** — no real orders are ever placed.

---

## Quick Start

```bash
# 1. Clone and enter
cd /path/to/Paper

# 2. Create virtual env and install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure credentials
cp .env.example .env
# Edit .env — add KITE_API_KEY and KITE_API_SECRET

# 4. Start the OAuth callback server (terminal 1)
uvicorn app.auth_server:app --port 8000

# 5. Start the dashboard (terminal 2)
streamlit run app/dashboard/app.py
```

Open **http://localhost:8501** in your browser.

---

## Zerodha Setup

1. Log in to [kite.zerodha.com/settings/apps](https://kite.zerodha.com/settings/apps)
2. Create or edit your app — set **Redirect URL** to `http://localhost:8000/callback`
3. Copy API Key and Secret into `.env`

---

## First-Run Setup (in the dashboard sidebar)

| Step | Action | Time |
|---|---|---|
| 1 | **Login to Zerodha** — click the link in the sidebar | <5s |
| 2 | **Load Universe** — fetches Nifty 500 instrument tokens | ~15s |
| 3 | **Warmup History** — fetches 45-day 5-min candles for all 500 stocks | ~7 min |
| 4 | **Start Engine** — connects WebSocket and begins scanning | instant |

---

## Strategy: 15-min ORB

**Opening Range:** 9:15–9:30 AM IST  
**Signal candles:** 5-minute

| Check | Long | Short |
|---|---|---|
| Market | BULLISH (Nifty above VWAP) | BEARISH (Nifty below VWAP) |
| Sector | Top 2 strong sectors | Top 2 weak sectors |
| Stock | Price above VWAP | Price below VWAP |
| Breakout | Close > OR High + buffer | Close < OR Low − buffer |
| RVOL | ≥ 1.5× average | ≥ 1.5× average |
| Time | Before 14:30 | Before 14:30 |

**Stop-loss:** ORB boundary (ORL for longs, ORH for shorts)  
**Target:** 2× risk  
**Max trades/day:** 3  
**Max open positions:** 3  
**Force close:** 15:20 IST

---

## Running Backtests

In the dashboard → **⚙ Backtest** tab:
1. Select date range
2. Click **Run Backtest**
3. Results include: win rate, profit factor, max drawdown, equity curve, full trade log

Backtests require history data to be loaded first (step 3 above).

---

## Running Tests

```bash
cd /path/to/Paper
PYTHONPATH=. pytest tests/ -v
```

---

## Project Structure

```
app/
├── auth_server.py       OAuth callback (FastAPI, port 8000)
├── config.py            All parameters (pydantic-settings)
├── db/                  SQLAlchemy models + session
├── kite/                Zerodha integration (auth, feed, data)
├── market/              Candle builder, indicators, market/sector analyzers, scanner
├── strategy/orb.py      ORB signal logic
├── engine/              Paper broker, risk manager, trading engine runner
├── backtest/            Historical simulation engine
└── dashboard/app.py     Streamlit UI
data/
└── sector_map.json      Nifty 500 → sector mapping
tests/                   Unit tests
```
