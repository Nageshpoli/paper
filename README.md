# AiStockTrade — Paper Trading

A paper trading application for learning and practicing algorithmic trading with Zerodha (Indian markets). No real money is ever placed — all positions are virtual.

## Quick Start

### 1. Prerequisites

- Python 3.9+
- Zerodha KiteConnect API credentials

### 2. Setup

```bash
# Clone / enter the project
cd /Users/I311860/Personal/Paper

# Create virtualenv and install dependencies
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure credentials
cp .env.example .env
# Edit .env and fill in KITE_API_KEY and KITE_API_SECRET
```

### 3. Run

```bash
cd backend
source .venv/bin/activate
PYTHONPATH=. uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000** in your browser.

### 4. First-time setup (in the UI)

Follow the four-step checklist shown on the Dashboard:

| Step | What it does |
|------|-------------|
| 1. Kite Login | Redirects to Zerodha to authorize the API |
| 2. Load Universe | Downloads Nifty 500 constituents from NSE |
| 3. History Warmup | Fetches 45 days of 5-min + daily candles |
| 4. Start Engine | Click **START** in the top bar |

The live feed starts automatically once the engine is running and market hours begin (9:15 IST).

### 5. Run tests

```bash
cd backend
PYTHONPATH=. pytest tests/ -v
```

---

## Project Structure

```
Paper/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app factory
│   │   ├── config.py        # Settings (.env)
│   │   ├── api/             # REST endpoints (split by domain)
│   │   ├── db/              # SQLAlchemy models + session
│   │   ├── engine/          # TradingEngine, PaperBroker, RiskManager, NSESession
│   │   ├── strategies/      # Strategy registry + ORB strategy
│   │   ├── backtest/        # Backtest simulator
│   │   ├── kite/            # Zerodha auth, client, history, websocket
│   │   └── market/          # Candles, indicators, live feed, scanner, universe
│   ├── tests/               # pytest test suite
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html           # Single-page app (Alpine.js + Tailwind CDN)
│   └── app.js               # All state and API calls
├── data/                    # SQLite database (auto-created)
├── docs/
│   ├── architecture.md      # System design
│   └── setup.md             # Detailed setup
└── README.md
```

---

## Adding a New Strategy

1. Create `backend/app/strategies/my_strategy/strategy.py`
2. Subclass `Strategy` from `app.strategies.base`
3. Implement `evaluate(candle, **kwargs) -> Signal`
4. Register it at the bottom of `app/strategies/registry.py`:
   ```python
   from app.strategies.my_strategy.strategy import MyStrategy
   strategy_registry.register(MyStrategy())
   ```

The new strategy will immediately appear in the UI's Backtest strategy dropdown.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KITE_API_KEY` | — | Zerodha KiteConnect API key |
| `KITE_API_SECRET` | — | Zerodha KiteConnect API secret |
| `VIRTUAL_CAPITAL` | `100000` | Starting paper capital (₹) |
| `MAX_OPEN_POSITIONS` | `3` | Max concurrent paper positions |
| `MAX_POSITION_NOTIONAL` | `30000` | Max value per position (₹) |
| `RISK_PER_TRADE_PCT` | `0.005` | Risk per trade as decimal (0.005 = 0.5%) |
| `MAX_DAILY_LOSS` | `3000` | Kill-switch daily loss limit (₹) |

## Push to GitHub

```bash
cd /Users/I311860/Personal/Paper
git init
git add .
git commit -m "Initial paper trading app"
git remote add origin https://github.com/Nageshpoli/paper.git
git push -u origin main
```
