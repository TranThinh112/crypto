"""Basket persistence."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.basket import Basket, BasketEvent


class BasketRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, basket: Basket) -> Basket:
        self.session.add(basket)
        self.session.flush()
        return basket

    def active(self, symbol: str) -> Basket | None:
        return self.session.scalar(select(Basket).where(Basket.symbol == symbol, Basket.status.in_(("ACTIVE", "CLOSING"))))

    def get_external(self, external_id: str) -> Basket | None:
        return self.session.scalar(select(Basket).where(Basket.external_id == external_id))

    def event(self, basket_id: int, event_type: str, details: dict) -> None:
        self.session.add(BasketEvent(basket_id=basket_id, event_type=event_type, details=details))
