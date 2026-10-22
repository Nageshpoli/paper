from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_DIR / "data"
LOG_DIR = PROJECT_DIR / "logs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8")

    app_name: str = "AIStockTrade"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    kite_api_key: str = ""
    kite_api_secret: str = ""
    kite_redirect_url: str = "http://localhost:8000/callback"

    # Capital & sizing
    virtual_capital: float = Field(default=100000, gt=0)
    max_open_positions: int = Field(default=3, gt=0)
    max_position_notional: float = Field(default=30000, gt=0)
    max_total_exposure: float = Field(default=90000, gt=0)
    max_positions_per_sector: int = Field(default=1, gt=0)

    # Risk controls
    risk_per_trade_pct: float = Field(default=0.005, gt=0, le=0.02)
    max_entries_per_day: int = Field(default=3, gt=0)
    max_daily_loss: float = Field(default=3000, gt=0)

    # Scanner filters
    minimum_relative_volume: float = Field(default=1.5, gt=0)
    minimum_median_traded_value: float = Field(default=0, ge=0)
    maximum_spread_bps: float = Field(default=0, ge=0)

    # Costs & timing
    estimated_cost_bps: float = Field(default=5.0, ge=0)
    history_delay_seconds: float = Field(default=0.4, ge=0.3)

    paper_only: bool = True
    database_url: str = f"sqlite:///{DATA_DIR / 'aistocktrade.db'}"


@lru_cache
def get_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()
