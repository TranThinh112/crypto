"""Coordinates stop management and partial closes for every bot position."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pandas as pd
from sqlalchemy import delete, select

from app.broker.execution_service import ExecutionService
from app.broker.mt5_client import BrokerPosition, SymbolSpec
from app.config.settings import TradingConfig
from app.database import Database
from app.models.trade import Trade, TradeEvent
from app.positions.break_even_manager import BreakEvenManager
from app.positions.partial_close_manager import PartialCloseManager
from app.positions.position_revalidator import PositionRevalidator
from app.positions.trailing_stop_manager import TrailingStopManager
from app.strategy.signal_engine import SignalEvaluation
from app.strategy.trend_detector import TrendAssessment
from app.utils.enums import TradeState


@dataclass(frozen=True, slots=True)
class ManagementSummary:
    inspected: int
    stops_modified: int
    partial_closes: int
    skipped_untracked: int


@dataclass(frozen=True, slots=True)
class RevalidationSummary:
    inspected: int
    closed: int
    kept: int
    skipped_untracked: int


class PositionManager:
    def __init__(self, database: Database, execution: ExecutionService, config: TradingConfig, spec: SymbolSpec) -> None:
        self.database = database
        self.execution = execution
        self.config = config
        self.spec = spec
        self.break_even = BreakEvenManager(config.break_even)
        self.trailing = TrailingStopManager(config.trailing_stop)
        self.partial = PartialCloseManager(config.partial_close)
        self.revalidator = PositionRevalidator(config.position_revalidation, config.strategy)
        self._last_keep_cleanup_at: datetime | None = None

    def _cleanup_old_revalidation_kept_events(self) -> None:
        retention = self.config.position_revalidation.keep_event_retention_minutes
        interval = self.config.position_revalidation.keep_event_cleanup_interval_seconds
        now = datetime.now(UTC)
        if self._last_keep_cleanup_at is not None and now - self._last_keep_cleanup_at < timedelta(seconds=interval):
            return
        self._last_keep_cleanup_at = now
        cutoff = now - timedelta(minutes=retention)
        with self.database.transaction() as session:
            session.execute(
                delete(TradeEvent).where(
                    TradeEvent.event_type == "POSITION_REVALIDATION_KEPT",
                    TradeEvent.timestamp < cutoff,
                )
            )

    def revalidate(
        self,
        positions: list[BrokerPosition],
        trend: TrendAssessment,
        m15: pd.DataFrame,
        m5: pd.DataFrame,
        rotation: SignalEvaluation,
        decision_key: str,
    ) -> RevalidationSummary:
        self._cleanup_old_revalidation_kept_events()
        closed = kept = skipped = 0
        for position in positions:
            with self.database.transaction() as session:
                trade = session.scalar(select(Trade).where(Trade.broker_ticket == position.ticket))
                if trade is None:
                    skipped += 1
                    continue
                trade_id = trade.id
                opened_at = trade.opened_at
                initial_risk_amount = trade.initial_risk_amount
                max_favorable_profit = trade.max_favorable_profit
            decision = self.revalidator.evaluate(
                position,
                trend,
                m15,
                m5,
                rotation,
                opened_at=opened_at,
                initial_risk_amount=initial_risk_amount,
                max_favorable_profit=max_favorable_profit,
            )
            if not decision.should_close:
                kept += 1
                with self.database.transaction() as session:
                    session.add(TradeEvent(trade_id=trade_id, event_type="POSITION_REVALIDATION_KEPT", details={"reason": decision.reason, **decision.details}))
                continue
            key = f"revalidate:{position.ticket}:{decision_key}:{trend.direction.value}"
            result = self.execution.close(position, position.volume, self.spec, key, "POSITION_REVALIDATION")
            if result and result.success:
                closed += 1
                with self.database.transaction() as session:
                    trade = session.get(Trade, trade_id)
                    if trade:
                        trade.close_reason = "POSITION_REVALIDATION"
                    session.add(TradeEvent(trade_id=trade_id, event_type="POSITION_REVALIDATION_CLOSED", details={"reason": decision.reason, **decision.details}))
        return RevalidationSummary(len(positions), closed, kept, skipped)

    def manage(self, positions: list[BrokerPosition], atr: float) -> ManagementSummary:
        modified = partials = skipped = 0
        for position in positions:
            with self.database.transaction() as session:
                trade = session.scalar(select(Trade).where(Trade.broker_ticket == position.ticket))
                if trade is None:
                    skipped += 1
                    continue
                trade_data = {
                    "id": trade.id, "initial_stop": trade.initial_stop_loss, "initial_volume": trade.initial_volume,
                    "break_even": trade.break_even_applied, "levels": tuple(trade.partial_levels_completed or []),
                }
            be = self.break_even.evaluate(position, trade_data["initial_stop"], self.spec, trade_data["break_even"])
            trailing = self.trailing.evaluate(position, trade_data["initial_stop"], atr, self.spec)
            candidates = [decision.new_stop for decision in (be, trailing) if decision.should_update and decision.new_stop is not None]
            if candidates:
                new_stop = max(candidates) if position.side == "BUY" else min(candidates)
                key = f"stop:{position.ticket}:{new_stop:.{self.spec.digits}f}"
                result = self.execution.modify_stop(position, new_stop, position.take_profit, self.spec, key)
                if result and result.success:
                    modified += 1
                    with self.database.transaction() as session:
                        trade = session.get(Trade, trade_data["id"])
                        if trade:
                            trade.stop_loss = new_stop
                            if be.should_update and be.new_stop == new_stop:
                                trade.break_even_applied = True
                            session.add(TradeEvent(trade_id=trade.id, event_type="STOP_ADVANCED", details={"new_stop": new_stop, "break_even": be.should_update, "trailing": trailing.should_update}))
                    position = BrokerPosition(**{**position.__dict__, "stop_loss": new_stop}) if hasattr(position, "__dict__") else position
            close = self.partial.evaluate(position, trade_data["initial_volume"], trade_data["initial_stop"], trade_data["levels"], self.spec)
            if close.should_close and close.trigger_r is not None:
                key = f"partial:{position.ticket}:R{close.trigger_r:g}"
                result = self.execution.close(position, close.volume, self.spec, key, f"PARTIAL_R_{close.trigger_r:g}")
                if result and result.success:
                    partials += 1
                    with self.database.transaction() as session:
                        trade = session.get(Trade, trade_data["id"])
                        if trade:
                            levels = list(trade.partial_levels_completed or [])
                            if close.trigger_r not in levels:
                                levels.append(close.trigger_r)
                            trade.partial_levels_completed = levels
                            trade.state = TradeState.PARTIALLY_CLOSED.value
                            session.add(TradeEvent(trade_id=trade.id, event_type="PARTIAL_CLOSE", details={"trigger_r": close.trigger_r, "volume": close.volume}))
        return ManagementSummary(len(positions), modified, partials, skipped)
