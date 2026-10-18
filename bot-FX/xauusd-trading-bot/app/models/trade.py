"""Trade and execution audit persistence models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    basket_id: Mapped[int | None] = mapped_column(ForeignKey("baskets.id"), index=True)
    broker_ticket: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8))
    state: Mapped[str] = mapped_column(String(32), index=True)
    volume: Mapped[float] = mapped_column(Float)
    initial_volume: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    initial_stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[float] = mapped_column(Float)
    realized_profit: Mapped[float] = mapped_column(Float, default=0)
    floating_profit: Mapped[float] = mapped_column(Float, default=0)
    estimated_win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initial_risk_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_adverse_profit: Mapped[float] = mapped_column(Float, default=0)
    max_favorable_profit: Mapped[float] = mapped_column(Float, default=0)
    max_adverse_r: Mapped[float] = mapped_column(Float, default=0)
    max_favorable_r: Mapped[float] = mapped_column(Float, default=0)
    signal_hash: Mapped[str] = mapped_column(String(64))
    entry_candle_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    partial_levels_completed: Mapped[list[float]] = mapped_column(JSON, default=list)
    break_even_applied: Mapped[bool] = mapped_column(default=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index("ix_trade_magic_scope", "symbol", "state"),)


class TradeEvent(Base):
    __tablename__ = "trade_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    trade_id: Mapped[int | None] = mapped_column(ForeignKey("trades.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ExecutionRequest(Base):
    __tablename__ = "execution_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    trade_id: Mapped[int | None] = mapped_column(ForeignKey("trades.id"), index=True)
    action: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
