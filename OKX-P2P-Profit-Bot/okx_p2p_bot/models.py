from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Order:
    order_id: str = ""
    side: str = ""
    status: str = ""
    time_text: str = ""
    usdt: Optional[float] = None
    vnd: Optional[float] = None
    unit_price: Optional[float] = None
    source: str = ""
    raw_text: str = ""
    needs_review: bool = False
    merged_into: bool = False
    warnings: list[str] = field(default_factory=list)
    timestamp: Optional[datetime] = None


@dataclass
class SaleResult:
    time_text: str
    order_id: str
    usdt: Optional[float]
    vnd: Optional[float]
    sell_price: Optional[float]
    applied_buy_price: Optional[float]
    spread: Optional[float]
    profit: Optional[float]
    check_status: str
    buy_price_source: str = ""
