from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class VirtualAccount(Base):
    __tablename__ = "virtual_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), default="default")
    cash: Mapped[float] = mapped_column(Float, default=100000.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PaperOrder(Base):
    __tablename__ = "paper_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(40), index=True)
    action: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="FILLED")
    strategy: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    signal_key: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Position(Base):
    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(40), index=True)
    side: Mapped[str] = mapped_column(String(8), default="LONG")
    quantity: Mapped[int] = mapped_column(Integer)
    entry_price: Mapped[float] = mapped_column(Float)
    last_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    strategy: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    entry_order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("paper_orders.id"), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CompletedTrade(Base):
    __tablename__ = "completed_trades"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(40), index=True)
    side: Mapped[str] = mapped_column(String(8), default="LONG")
    quantity: Mapped[int] = mapped_column(Integer)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float)
    pnl: Mapped[float] = mapped_column(Float, default=0.0)
    strategy: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    exit_reason: Mapped[str] = mapped_column(String(200), default="")
    entry_order_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    exit_order_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StrategySignal(Base):
    __tablename__ = "strategy_signals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(40), index=True)
    action: Mapped[str] = mapped_column(String(10))
    strategy: Mapped[str] = mapped_column(String(80))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(String(500), default="")
    price: Mapped[float] = mapped_column(Float)
    signal_key: Mapped[Optional[str]] = mapped_column(String(180), unique=True, nullable=True)
    execution_status: Mapped[str] = mapped_column(String(20), default="CANDIDATE")
    execution_reason: Mapped[str] = mapped_column(String(500), default="")
    fill_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AppState(Base):
    """Single-row table keeping engine runtime state across restarts."""
    __tablename__ = "app_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    running: Mapped[bool] = mapped_column(Boolean, default=False)
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)
    mode: Mapped[str] = mapped_column(String(20), default="PAPER")
    last_message: Mapped[str] = mapped_column(String(500), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UniverseConstituent(Base):
    __tablename__ = "universe_constituents"
    symbol: Mapped[str] = mapped_column(String(40), primary_key=True)
    instrument_token: Mapped[Optional[int]] = mapped_column(Integer, unique=True, index=True, nullable=True)
    tick_size: Mapped[float] = mapped_column(Float, default=0.05)
    sector: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sector_index: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    source: Mapped[str] = mapped_column(String(300), default="")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    effective_date: Mapped[str] = mapped_column(String(20), default="")


class MarketCandle(Base):
    __tablename__ = "market_candles"
    __table_args__ = (
        UniqueConstraint("symbol", "timestamp", "interval", name="uq_candle_symbol_time_interval"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(40), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer, default=0)
    interval: Mapped[str] = mapped_column(String(12), default="5minute")


class ScannerState(Base):
    __tablename__ = "scanner_states"
    symbol: Mapped[str] = mapped_column(String(40), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    change_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    or_high: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    or_low: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    relative_volume: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    market_direction: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    sector_direction: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="WAITING")
    reason: Mapped[str] = mapped_column(String(500), default="")


class UniverseSnapshot(Base):
    __tablename__ = "universe_snapshots"
    version: Mapped[str] = mapped_column(String(80), primary_key=True)
    universe_name: Mapped[str] = mapped_column(String(20), default="NIFTY_500")
    source: Mapped[str] = mapped_column(String(300), default="")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    effective_date: Mapped[str] = mapped_column(String(20), default="")
    constituent_count: Mapped[int] = mapped_column(Integer, default=0)


class UniverseMember(Base):
    __tablename__ = "universe_members"
    __table_args__ = (
        UniqueConstraint("version", "symbol", name="uq_universe_version_symbol"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(ForeignKey("universe_snapshots.version"), index=True)
    universe_name: Mapped[str] = mapped_column(String(20), default="NIFTY_500")
    symbol: Mapped[str] = mapped_column(String(40), index=True)
    instrument_token: Mapped[int] = mapped_column(Integer)
    tick_size: Mapped[float] = mapped_column(Float, default=0.05)
    sector: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sector_index: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)


class StrategyConfigVersion(Base):
    __tablename__ = "strategy_config_versions"
    version: Mapped[str] = mapped_column(String(80), primary_key=True)
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DailySummary(Base):
    __tablename__ = "daily_summaries"
    date: Mapped[str] = mapped_column(String(20), primary_key=True)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    total_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    ending_capital: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    strategy_name: Mapped[str] = mapped_column(String(80), default="orb_v1")
    start_date: Mapped[str] = mapped_column(String(20))
    end_date: Mapped[str] = mapped_column(String(20))
    universe_name: Mapped[str] = mapped_column(String(20), default="NIFTY_500")
    metrics: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trade_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SystemEvent(Base):
    __tablename__ = "system_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level: Mapped[str] = mapped_column(String(12), default="INFO")
    category: Mapped[str] = mapped_column(String(40), index=True)
    message: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
