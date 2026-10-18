"""Persistent bot state and cooldown access."""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bot_state import BotStateRecord, Cooldown, DailyStatistic


class StateRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def set_state(self, state: str, reason: str | None = None, details: dict | None = None) -> BotStateRecord:
        record = BotStateRecord(state=state, reason=reason, details=details or {})
        self.session.add(record)
        self.session.flush()
        return record

    def current_state(self) -> BotStateRecord | None:
        return self.session.scalar(select(BotStateRecord).order_by(BotStateRecord.timestamp.desc(), BotStateRecord.id.desc()).limit(1))

    def active_cooldown(self, symbol: str, now: datetime) -> Cooldown | None:
        return self.session.scalar(select(Cooldown).where(Cooldown.symbol == symbol, Cooldown.active.is_(True), Cooldown.expires_at > now).order_by(Cooldown.expires_at.desc()).limit(1))

    def daily(self, trading_date: date) -> DailyStatistic | None:
        return self.session.scalar(select(DailyStatistic).where(DailyStatistic.trading_date == trading_date))
