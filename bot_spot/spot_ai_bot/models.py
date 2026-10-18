from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AssetGroup(str, Enum):
    crypto = "crypto"
    stocks = "stocks"
    commodities = "commodities"
    cash = "cash"


class AdvisorOpinion(BaseModel):
    group: AssetGroup
    symbol: str
    opinion: str
    confidence: float = Field(ge=0, le=1)
    suggested_action: str
    reason: str
    risks: list[str] = Field(default_factory=list)


class AllocationPlan(BaseModel):
    total_budget_usd: float
    allocation: dict[AssetGroup, float]
    reason: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MarketCandidate(BaseModel):
    group: AssetGroup
    symbol: str
    price: float
    trend_score: float = Field(ge=0, le=1)
    liquidity_score: float = Field(ge=0, le=1)
    volatility_score: float = Field(ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TradeProposal(BaseModel):
    group: AssetGroup
    symbol: str
    action: str
    amount_usd: float
    status: str = "pending"
    strategy_reason: str
    advisor: AdvisorOpinion | None = None
    risk_notes: list[str] = Field(default_factory=list)
    price: float | None = None
    quantity: float | None = None
    average_price: float | None = None
    filled_notional_usd: float | None = None
    buy_sequence: str | None = None
    exchange_order_id: str | None = None
    execution_error: str | None = None
    entry_plan: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class PositionOpinion(BaseModel):
    symbol: str
    opinion: str
    confidence: float = Field(ge=0, le=1)
    suggested_action: str
    reason: str
    risks: list[str] = Field(default_factory=list)

class PositionManagementProposal(BaseModel):
    symbol: str
    asset: str
    quantity: float
    price_usdt: float | None = None
    value_usdt: float | None = None
    pnl_usdt: float | None = None
    pnl_pct: float | None = None
    trend_score: float | None = None
    liquidity_score: float | None = None
    volatility_score: float | None = None
    support_usdt: float | None = None
    resistance_usdt: float | None = None
    drawdown_from_resistance_pct: float | None = None
    position_weight_pct: float | None = None
    proposed_size_pct: float | None = None
    approval_status: str = "analysis_only"
    recommended_action: str = "HOLD"
    final_action: str = "HOLD"
    rule_reason: str
    final_gate_passed: bool = True
    ai_called: bool = False
    ai_opinion: PositionOpinion | None = None
    risk_notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
