from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.router import router
from app.config import get_settings
from app.db.session import Base, engine as db_engine

PROJECT_DIR = Path(__file__).resolve().parents[3]
FRONTEND_DIR = PROJECT_DIR / "frontend"


def create_app() -> FastAPI:
    settings = get_settings()
    Base.metadata.create_all(bind=db_engine)
    _upgrade_sqlite_schema()
    app = FastAPI(title=settings.app_name, version="1.0.0")
    app.include_router(router)
    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    return app


def _upgrade_sqlite_schema() -> None:
    """Apply additive column migrations for existing databases."""
    from sqlalchemy import inspect, text
    from app.db.session import engine as eng

    insp = inspect(eng)
    with eng.connect() as conn:
        _add_column_if_missing(conn, insp, "virtual_accounts", "cash", "FLOAT DEFAULT 100000.0")
        _add_column_if_missing(conn, insp, "positions", "entry_price", "FLOAT DEFAULT 0.0")
        _add_column_if_missing(conn, insp, "positions", "status", "VARCHAR(20) DEFAULT 'OPEN'")
        _add_column_if_missing(conn, insp, "positions", "side", "VARCHAR(8) DEFAULT 'LONG'")
        _add_column_if_missing(conn, insp, "paper_orders", "action", "VARCHAR(10) DEFAULT 'BUY'")
        _add_column_if_missing(conn, insp, "paper_orders", "signal_key", "VARCHAR(180)")
        _add_column_if_missing(conn, insp, "completed_trades", "pnl", "FLOAT DEFAULT 0.0")
        _add_column_if_missing(conn, insp, "app_state", "running", "BOOLEAN DEFAULT 0")
        _add_column_if_missing(conn, insp, "app_state", "kill_switch", "BOOLEAN DEFAULT 0")
        _add_column_if_missing(conn, insp, "app_state", "mode", "VARCHAR(20) DEFAULT 'PAPER'")
        _add_column_if_missing(conn, insp, "app_state", "last_message", "VARCHAR(500) DEFAULT ''")
        _add_column_if_missing(conn, insp, "universe_snapshots", "universe_name", "VARCHAR(20) DEFAULT 'NIFTY_500'")
        _add_column_if_missing(conn, insp, "universe_members", "universe_name", "VARCHAR(20) DEFAULT 'NIFTY_500'")
        _add_column_if_missing(conn, insp, "backtest_runs", "trade_log", "TEXT")
        _add_column_if_missing(conn, insp, "backtest_runs", "strategy_name", "VARCHAR(80) DEFAULT 'orb_v1'")
        _add_column_if_missing(conn, insp, "backtest_runs", "universe_name", "VARCHAR(20) DEFAULT 'NIFTY_500'")
        _add_column_if_missing(conn, insp, "daily_summaries", "total_trades", "INTEGER DEFAULT 0")
        _add_column_if_missing(conn, insp, "daily_summaries", "winning_trades", "INTEGER DEFAULT 0")
        _add_column_if_missing(conn, insp, "daily_summaries", "total_pnl", "FLOAT DEFAULT 0.0")
        _add_column_if_missing(conn, insp, "daily_summaries", "ending_capital", "FLOAT")
        conn.commit()


def _add_column_if_missing(conn, insp, table: str, column: str, col_def: str) -> None:
    from sqlalchemy import text
    if not insp.has_table(table):
        return
    existing = [c["name"] for c in insp.get_columns(table)]
    if column not in existing:
        conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {col_def}'))


app = create_app()
