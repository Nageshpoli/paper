from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func

from app.config import get_settings
from app.db.models import MarketCandle, UniverseConstituent
from app.db.session import SessionLocal
from app.kite.client import get_kite

IST = ZoneInfo("Asia/Kolkata")
_SECTOR_MAP_PATH = Path(__file__).resolve().parents[2] / "data" / "sector_map.json"


def load_sector_map() -> dict:
    if _SECTOR_MAP_PATH.exists():
        return json.loads(_SECTOR_MAP_PATH.read_text())
    return {}


def refresh_universe() -> dict:
    """Fetch NSE instrument master and populate UniverseConstituent table."""
    kite = get_kite()
    sector_map = load_sector_map()

    # build reverse lookup: symbol -> sector
    symbol_to_sector: dict[str, str] = {}
    for sector_name, info in sector_map.items():
        for sym in info.get("stocks", []):
            symbol_to_sector[sym] = sector_name

    instruments = kite.instruments("NSE")
    nifty500_symbols = set(symbol_to_sector.keys())

    db = SessionLocal()
    try:
        added = 0
        for inst in instruments:
            sym = inst["tradingsymbol"]
            if sym not in nifty500_symbols:
                continue
            row = db.get(UniverseConstituent, sym)
            if row is None:
                row = UniverseConstituent(symbol=sym)
                db.add(row)
                added += 1
            row.name = inst.get("name", "")
            row.instrument_token = inst.get("instrument_token")
            row.sector = symbol_to_sector.get(sym, "")
        db.commit()
        total = db.query(UniverseConstituent).count()
        return {"added": added, "total": total}
    finally:
        db.close()


def fetch_historical(symbol: str, token: int, interval: str, days: int) -> list[dict]:
    """Fetch historical candles for a single symbol from Kite."""
    kite = get_kite()
    now = datetime.now(IST)
    start = now - timedelta(days=days)
    retries = 3
    for attempt in range(retries):
        try:
            return kite.historical_data(token, start, now, interval, continuous=False, oi=False)
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(min(8, 0.5 * (2 ** attempt)))
            else:
                raise RuntimeError(f"Historical fetch failed for {symbol}: {exc}")
    return []


def persist_candles(symbol: str, rows: list[dict], interval: str) -> int:
    """Upsert candle rows into the DB. Returns count of new rows inserted."""
    db = SessionLocal()
    added = 0
    try:
        for row in rows:
            stamp = row["date"]
            if hasattr(stamp, "tzinfo") and stamp.tzinfo is not None:
                stamp = stamp.astimezone(IST).replace(tzinfo=None)
            exists = db.query(MarketCandle.id).filter_by(
                symbol=symbol, interval=interval, timestamp=stamp
            ).first()
            if not exists:
                db.add(MarketCandle(
                    symbol=symbol, interval=interval, timestamp=stamp,
                    open=row["open"], high=row["high"], low=row["low"],
                    close=row["close"], volume=row.get("volume", 0),
                ))
                added += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return added


def warmup_history(progress_callback=None) -> dict:
    """
    Fetch 45-day 5-min + daily candles for all universe constituents.
    Calls progress_callback(completed, total) after each symbol.
    Returns summary dict.
    """
    settings = get_settings()
    db = SessionLocal()
    try:
        constituents = db.query(UniverseConstituent).filter(
            UniverseConstituent.instrument_token.isnot(None)
        ).all()
    finally:
        db.close()

    if not constituents:
        return {"status": "no_universe", "total": 0, "completed": 0}

    total = len(constituents)
    completed = 0
    errors = []

    for c in constituents:
        for interval, days, min_count in [("5minute", settings.history_days, 1000), ("day", 60, 30)]:
            db2 = SessionLocal()
            try:
                count = db2.query(func.count(MarketCandle.id)).filter_by(
                    symbol=c.symbol, interval=interval
                ).scalar()
            finally:
                db2.close()
            if count and count >= min_count:
                continue
            try:
                rows = fetch_historical(c.symbol, c.instrument_token, interval, days)
                persist_candles(c.symbol, rows, interval)
            except Exception as exc:
                errors.append({"symbol": c.symbol, "error": str(exc)[:120]})
            time.sleep(settings.history_warmup_delay)

        completed += 1
        if progress_callback:
            progress_callback(completed, total)

    return {"status": "done", "total": total, "completed": completed, "errors": errors}


def get_ltp(symbols: list[str]) -> dict[str, float]:
    """Fetch last traded price for a list of 'EXCHANGE:SYMBOL' strings."""
    kite = get_kite()
    try:
        data = kite.ltp(symbols)
        return {k: v["last_price"] for k, v in data.items()}
    except Exception:
        return {}


def get_ohlc(symbols: list[str]) -> dict:
    """Fetch OHLC for a list of 'EXCHANGE:SYMBOL' strings."""
    kite = get_kite()
    try:
        return kite.ohlc(symbols)
    except Exception:
        return {}
