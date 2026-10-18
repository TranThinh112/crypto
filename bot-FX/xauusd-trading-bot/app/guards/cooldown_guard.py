"""Database-backed cooldown creation and evaluation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.config.settings import CooldownConfig
from app.database import Database
from app.models.bot_state import Cooldown
from app.utils.enums import CloseReason
from app.utils.time_utils import ensure_utc


class CooldownGuard:
    def __init__(self, database: Database, config: CooldownConfig, symbol: str) -> None:
        self.database = database
        self.config = config
        self.symbol = symbol

    def _minutes(self, reason: CloseReason) -> int:
        return {
            CloseReason.TAKE_PROFIT: self.config.after_take_profit_minutes,
            CloseReason.STOP_LOSS: self.config.after_stop_loss_minutes,
            CloseReason.MANUAL: self.config.after_manual_close_minutes,
            CloseReason.TREND_REVERSAL: self.config.after_trend_reversal_minutes,
            CloseReason.PROFIT_PROTECTION: self.config.after_take_profit_minutes,
            CloseReason.WEEKEND: self.config.after_manual_close_minutes,
            CloseReason.BROKER_EXIT: self.config.after_manual_close_minutes,
        }[reason]

    def activate(self, reason: CloseReason, basket_external_id: str | None = None, now: datetime | None = None) -> Cooldown | None:
        if not self.config.enabled:
            return None
        starts = now or datetime.now(UTC)
        expires = starts + timedelta(minutes=self._minutes(reason))
        with self.database.transaction() as session:
            session.execute(update(Cooldown).where(Cooldown.symbol == self.symbol, Cooldown.active.is_(True)).values(active=False))
            value = Cooldown(symbol=self.symbol, reason=reason.value, starts_at=starts, expires_at=expires, basket_external_id=basket_external_id, active=True)
            session.add(value)
            session.flush()
            return value

    def active(self, now: datetime | None = None) -> Cooldown | None:
        current = now or datetime.now(UTC)
        with self.database.transaction() as session:
            candidates = list(session.scalars(select(Cooldown).where(Cooldown.symbol == self.symbol, Cooldown.active.is_(True)).order_by(Cooldown.expires_at.desc())))
            for value in candidates:
                if ensure_utc(value.expires_at) > ensure_utc(current):
                    return value
                value.active = False
            return None
