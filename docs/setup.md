## Detailed Setup Guide

### System requirements

| Requirement | Minimum | Notes |
|-------------|---------|-------|
| Python | 3.9+ | Uses `zoneinfo` (stdlib in 3.9) |
| OS | macOS / Linux | Windows should work but untested |
| Network | Open internet | Required for Zerodha API and NSE data |

### Zerodha KiteConnect setup

1. Log in to [kite.trade/developers](https://kite.trade/developers)
2. Create a new app
3. Set the redirect URL to `http://localhost:8000/callback`
4. Copy the **API key** and **API secret**

### Install and configure

```bash
cd /Users/I311860/Personal/Paper/backend

# Create isolated Python environment
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env from template
cp .env.example .env
```

Edit `.env`:
```
KITE_API_KEY=your_actual_api_key
KITE_API_SECRET=your_actual_api_secret
```

Optional settings in `.env` (see README for full list):
```
VIRTUAL_CAPITAL=100000
MAX_OPEN_POSITIONS=3
RISK_PER_TRADE_PCT=0.005
MAX_DAILY_LOSS=3000
```

### Start the server

```bash
cd /Users/I311860/Personal/Paper/backend
source .venv/bin/activate
PYTHONPATH=. uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000)

### First-time daily flow

1. **Login to Kite**: Click the "1. Kite Login" action button. You'll be redirected to Zerodha, authorize, and be brought back.
2. **Load Universe**: Click "2. Load Universe". This fetches Nifty 500 constituent symbols (~500 stocks). Takes about 30 seconds.
3. **History Warmup**: Click "3. History Warmup". This fetches 45 days of 5-minute and daily candles for all ~500 symbols. Takes several minutes (rate-limited). The app will log progress.
4. **Start Engine**: Click the **START** button in the top bar. The live feed starts automatically when market opens at 9:15 IST.

### On subsequent days

- Steps 2 & 3 don't need to be repeated unless you want to update the universe or refresh the history window.
- You only need to re-login to Kite each day (the access token expires daily).
- The engine can be left running — the NSE session thread manages entry/exit windows automatically.

### Running tests

```bash
cd /Users/I311860/Personal/Paper/backend
source .venv/bin/activate
PYTHONPATH=. pytest tests/ -v
```

Expected: 21 passed in < 1 second.

### Troubleshooting

**"No module named app"**: Make sure you run from inside `backend/` with `PYTHONPATH=.`

**Kite login fails / token expired**: Click "1. Kite Login" again to re-authorize.

**Scanner shows nothing**: Universe must be loaded and history warmed up. Check that steps 2 & 3 completed successfully.

**Port already in use**: Kill any existing process on 8000: `lsof -ti:8000 | xargs kill`
