from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class VirtualAccount(Base):
    __tablename__ = "virtual_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    starting_capital: Mapped[float] = mapped_column(Float, default=100_000.0)
    cash: Mapped[float] = mapped_column(Float, default=100_000.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    peak_equity: Mapped[float] = mapped_column(Float, default=100_000.0)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)


class Position(Base):
    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(40))
    sector: Mapped[str] = mapped_column(String(60), default="")
    side: Mapped[str] = mapped_column(String(8))           # LONG / SHORT
    qty: Mapped[int] = mapped_column(Integer)
    entry_price: Mapped[float] = mapped_column(Float)      # signal price
    fill_price: Mapped[float] = mapped_column(Float)       # after slippage
    stop_loss: Mapped[float] = mapped_column(Float)
    target: Mapped[float] = mapped_column(Float)
    entry_time: Mapped[datetime] = mapped_column(DateTime)
    last_price: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")


class CompletedTrade(Base):
    __tablename__ = "completed_trades"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(40))
    sector: Mapped[str] = mapped_column(String(60), default="")
    side: Mapped[str] = mapped_column(String(8))
    qty: Mapped[int] = mapped_column(Integer)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float)
    entry_time: Mapped[datetime] = mapped_column(DateTime)
    exit_time: Mapped[datetime] = mapped_column(DateTime)
    gross_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    brokerage: Mapped[float] = mapped_column(Float, default=0.0)
    other_charges: Mapped[float] = mapped_column(Float, default=0.0)
    net_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    exit_reason: Mapped[str] = mapped_column(String(40), default="")
    or_high: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    or_low: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rvol: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class Signal(Base):
    __tablename__ = "signals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(40))
    sector: Mapped[str] = mapped_column(String(60), default="")
    action: Mapped[str] = mapped_column(String(8))         # BUY / SHORT
    signal_price: Mapped[float] = mapped_column(Float)
    or_high: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    or_low: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vwap: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rvol: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    market_direction: Mapped[str] = mapped_column(String(12), default="")
    sector_direction: Mapped[str] = mapped_column(String(12), default="")
    stop_loss: Mapped[float] = mapped_column(Float, default=0.0)
    target: Mapped[float] = mapped_column(Float, default=0.0)
    risk_reward: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="ACCEPTED")
    reason: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class DailyPerformance(Base):
    __tablename__ = "daily_performance"
    date: Mapped[str] = mapped_column(String(12), primary_key=True)
    starting_capital: Mapped[float] = mapped_column(Float, default=0.0)
    ending_capital: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)


class SystemKV(Base):
    __tablename__ = "system_kv"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class MarketCandle(Base):
    __tablename__ = "market_candles"
    __table_args__ = (UniqueConstraint("symbol", "interval", "timestamp"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(60), index=True)
    interval: Mapped[str] = mapped_column(String(12))      # 5minute / day
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer, default=0)


class UniverseConstituent(Base):
    __tablename__ = "universe_constituents"
    symbol: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    sector: Mapped[str] = mapped_column(String(60), default="")
    instrument_token: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    exchange: Mapped[str] = mapped_column(String(8), default="NSE")


class ScannerRow(Base):
    __tablename__ = "scanner_rows"
    symbol: Mapped[str] = mapped_column(String(40), primary_key=True)
    sector: Mapped[str] = mapped_column(String(60), default="")
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    change_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    or_high: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    or_low: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vwap: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rvol: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    signal: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_reward: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    reason: Mapped[str] = mapped_column(String(300), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
