"""Trade persistence and duplicate-key checks."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.trade import Trade, TradeEvent


class TradeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, trade: Trade) -> Trade:
        self.session.add(trade)
        self.session.flush()
        return trade

    def by_idempotency_key(self, key: str) -> Trade | None:
        return self.session.scalar(select(Trade).where(Trade.idempotency_key == key))

    def open_trades(self, symbol: str) -> list[Trade]:
        states = ("SUBMITTED", "OPEN", "PARTIALLY_CLOSED")
        return list(self.session.scalars(select(Trade).where(Trade.symbol == symbol, Trade.state.in_(states))))

    def event(self, trade_id: int | None, event_type: str, details: dict) -> None:
        self.session.add(TradeEvent(trade_id=trade_id, event_type=event_type, details=details))
