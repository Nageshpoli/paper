from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ── Zerodha ──────────────────────────────────────────────────────────────
    kite_api_key: str = ""
    kite_api_secret: str = ""
    kite_redirect_url: str = "http://localhost:8000/callback"

    # ── Capital & risk ────────────────────────────────────────────────────────
    virtual_capital: float = 100_000.0
    risk_per_trade_pct: float = 0.005        # 0.5% of equity
    max_risk_per_trade: float = 500.0        # ₹ cap
    reward_to_risk: float = 2.0
    max_trades_per_day: int = 3
    max_open_positions: int = 3
    max_position_notional: float = 50_000.0  # max ₹ per position

    # ── Strategy ─────────────────────────────────────────────────────────────
    or_start_time: str = "09:15"
    or_end_time: str = "09:30"
    entry_cutoff_time: str = "14:30"
    eod_close_time: str = "15:20"
    rvol_min: float = 1.5
    breakout_buffer_pct: float = 0.001       # 0.1% above ORH / below ORL
    slippage_pct: float = 0.0005             # 0.05% simulated slippage

    # ── Market direction thresholds ───────────────────────────────────────────
    market_vwap_min_gap_pct: float = 0.0     # Nifty must be at least this % above VWAP for BULLISH

    # ── Brokerage & charges ───────────────────────────────────────────────────
    brokerage_pct: float = 0.0003            # 0.03% per order
    brokerage_cap: float = 20.0              # ₹20 per order cap
    stt_sell_pct: float = 0.00025            # STT on intraday sell
    exchange_charges_pct: float = 0.0000345
    gst_pct: float = 0.18                    # on brokerage only
    stamp_duty_pct: float = 0.00003          # on buy side

    # ── Historical warmup ─────────────────────────────────────────────────────
    history_days: int = 45
    history_warmup_delay: float = 0.35       # seconds between Kite API calls


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
