"""Database-backed idempotency and same-candle guard."""

from datetime import datetime

from sqlalchemy import select

from app.database import Database
from app.models.trade import ExecutionRequest, Trade


class DuplicateOrderGuard:
    def __init__(self, database: Database) -> None:
        self.database = database

    def key_exists(self, key: str) -> bool:
        with self.database.transaction() as session:
            return session.scalar(select(ExecutionRequest.id).where(ExecutionRequest.idempotency_key == key)) is not None

    def candle_has_entry(self, symbol: str, candle_time: datetime, side: str | None = None) -> bool:
        with self.database.transaction() as session:
            query = select(Trade.id).where(Trade.symbol == symbol, Trade.entry_candle_time == candle_time)
            if side is not None:
                query = query.where(Trade.side == side)
            return session.scalar(query.limit(1)) is not None
