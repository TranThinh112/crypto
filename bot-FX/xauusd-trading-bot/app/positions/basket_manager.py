"""Basket metrics, exit rules and serialized basket closing."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from app.broker.execution_service import ExecutionService
from app.broker.mt5_client import BrokerClient, BrokerPosition, SymbolSpec
from app.config.settings import TradingConfig
from app.database import Database
from app.models.basket import Basket, BasketEvent
from app.models.trade import Trade, TradeEvent
from app.utils.calculations import weighted_average_price
from app.utils.enums import BasketProfitMode, BasketState, BasketStopLossMode, CloseReason, TradeState
from app.utils.time_utils import ensure_utc


@dataclass(frozen=True, slots=True)
class BasketMetrics:
    position_count: int
    total_volume: float
    weighted_average_entry: float
    floating_profit: float
    realized_profit: float
    combined_profit: float


@dataclass(frozen=True, slots=True)
class BasketExitDecision:
    should_close: bool
    reason: CloseReason | None
    current_profit: float
    threshold: float | None


class BasketManager:
    _locks_guard = threading.Lock()
    _locks: dict[str, threading.Lock] = {}

    def __init__(self, database: Database, broker: BrokerClient, execution: ExecutionService, config: TradingConfig, symbol: str, spec: SymbolSpec) -> None:
        self.database = database
        self.broker = broker
        self.execution = execution
        self.config = config
        self.symbol = symbol
        self.spec = spec

    @classmethod
    def _lock_for(cls, basket_id: str) -> threading.Lock:
        with cls._locks_guard:
            return cls._locks.setdefault(basket_id, threading.Lock())

    @staticmethod
    def metrics(positions: list[BrokerPosition], realized_profit: float = 0) -> BasketMetrics:
        entries = [(item.entry_price, item.volume) for item in positions]
        floating = sum(item.profit for item in positions)
        return BasketMetrics(len(positions), sum(item.volume for item in positions), weighted_average_price(entries), floating, realized_profit, floating + realized_profit)

    def basket_stop_loss_threshold(self, account_equity: float) -> float | None:
        stop = self.config.basket_stop_loss
        if not stop.enabled:
            return None
        if stop.mode is BasketStopLossMode.FIXED_USD:
            threshold = stop.maximum_loss_usd
            return min(threshold, stop.hard_max_loss_usd) if stop.hard_max_loss_usd is not None else threshold
        daily = self.config.daily_risk
        daily_budget = daily.max_daily_loss_usd if daily.max_daily_loss_usd is not None else account_equity * daily.max_daily_loss_percent / 100
        threshold = max(stop.balanced_minimum_loss_usd, daily_budget * stop.balanced_daily_loss_ratio)
        return min(threshold, stop.hard_max_loss_usd) if stop.hard_max_loss_usd is not None else threshold

    def _basket_is_fast_only(self, basket_external_id: str | None) -> bool:
        if not basket_external_id:
            return False
        with self.database.transaction() as session:
            basket = session.scalar(select(Basket).where(Basket.external_id == basket_external_id))
            if basket is None:
                return False
            keys = [item.idempotency_key for item in session.scalars(select(Trade).where(Trade.basket_id == basket.id))]
        fast_keys = [key for key in keys if key and "_M1_" in key]
        slow_keys = [key for key in keys if key and "_M5_" in key]
        return bool(fast_keys) and not slow_keys

    def _profit_protection_snapshot(self, basket_external_id: str | None) -> tuple[float, bool]:
        if not basket_external_id:
            return 0.0, False
        with self.database.transaction() as session:
            basket = session.scalar(select(Basket).where(Basket.external_id == basket_external_id))
            if basket is None:
                return 0.0, False
            break_even_applied = bool(session.scalar(
                select(Trade.id).where(Trade.basket_id == basket.id, Trade.break_even_applied.is_(True)).limit(1)
            ))
            return float(basket.maximum_floating_profit or 0.0), break_even_applied

    def active_baskets(self) -> list[Basket]:
        with self.database.transaction() as session:
            return list(session.scalars(select(Basket).where(
                Basket.symbol == self.symbol,
                Basket.status.in_((BasketState.ACTIVE.value, BasketState.CLOSING.value, BasketState.CLOSE_FAILED.value)),
            )))

    def basket_positions(self, basket_external_id: str, positions: list[BrokerPosition] | None = None) -> list[BrokerPosition]:
        positions = positions if positions is not None else self.broker.positions(self.symbol, self.config.broker.magic_number)
        with self.database.transaction() as session:
            basket = session.scalar(select(Basket).where(Basket.external_id == basket_external_id))
            if basket is None:
                return []
            tickets = {
                item
                for item in session.scalars(select(Trade.broker_ticket).where(Trade.basket_id == basket.id, Trade.broker_ticket.is_not(None)))
            }
        return [position for position in positions if position.ticket in tickets]

    def ensure_active(self, side: str, initial_risk_amount: float) -> Basket:
        with self.database.transaction() as session:
            active_statuses = (BasketState.PENDING.value, BasketState.ACTIVE.value, BasketState.CLOSING.value)
            same_side = session.scalar(select(Basket).where(
                Basket.symbol == self.symbol,
                Basket.direction.in_((side, "MIXED")),
                Basket.status.in_(active_statuses),
            ))
            if same_side:
                return same_side
            opposite = session.scalar(select(Basket).where(Basket.symbol == self.symbol, Basket.status.in_(active_statuses)))
            if opposite:
                if not self.config.position_control.allow_opposite_positions:
                    raise ValueError("An opposite-direction basket is already active")
            basket = Basket(
                external_id=str(uuid.uuid4()), symbol=self.symbol, direction=side,
                status=BasketState.ACTIVE.value, opened_at=datetime.now(UTC), initial_risk_amount=initial_risk_amount,
            )
            session.add(basket)
            session.flush()
            session.add(BasketEvent(basket_id=basket.id, event_type="BASKET_OPENED", details={"initial_risk_amount": initial_risk_amount}))
            return basket

    def add_initial_risk(self, basket_external_id: str, risk_amount: float) -> None:
        with self.database.transaction() as session:
            basket = session.scalar(select(Basket).where(Basket.external_id == basket_external_id))
            if basket is None:
                raise ValueError("Basket not found")
            basket.initial_risk_amount += risk_amount
            session.add(BasketEvent(basket_id=basket.id, event_type="BASKET_RISK_ADDED", details={"risk_amount": risk_amount, "total": basket.initial_risk_amount}))

    def discard_if_empty(self, basket_external_id: str, reason: str) -> None:
        if self.basket_positions(basket_external_id):
            return
        with self.database.transaction() as session:
            basket = session.scalar(select(Basket).where(Basket.external_id == basket_external_id))
            if basket and basket.position_count == 0 and basket.status in (BasketState.PENDING.value, BasketState.ACTIVE.value):
                basket.status = BasketState.CLOSED.value
                basket.closed_at = datetime.now(UTC)
                basket.close_reason = reason
                session.add(BasketEvent(basket_id=basket.id, event_type="EMPTY_BASKET_DISCARDED", details={"reason": reason}))

    def finalize_empty(self, basket_external_id: str, reason: CloseReason = CloseReason.TAKE_PROFIT) -> bool:
        if self.basket_positions(basket_external_id):
            return False
        with self.database.transaction() as session:
            basket = session.scalar(select(Basket).where(Basket.external_id == basket_external_id))
            if basket is None or basket.status == BasketState.CLOSED.value:
                return False
            trades = list(session.scalars(select(Trade).where(Trade.basket_id == basket.id)))
            if any(trade.state in (TradeState.PLANNED.value, TradeState.SUBMITTED.value) for trade in trades):
                # The order-submission thread still owns this basket. It will
                # either confirm the position or discard the basket on error.
                return False
            was_ever_confirmed = any(
                trade.broker_ticket is not None
                or trade.opened_at is not None
                or trade.state in (TradeState.OPEN.value, TradeState.PARTIALLY_CLOSED.value, TradeState.CLOSED.value)
                for trade in trades
            )
            if not was_ever_confirmed:
                basket.status = BasketState.CLOSED.value
                basket.closed_at = datetime.now(UTC)
                basket.position_count = 0
                basket.total_volume = 0
                basket.close_reason = "NO_CONFIRMED_BROKER_POSITION"
                session.add(BasketEvent(
                    basket_id=basket.id,
                    event_type="EMPTY_BASKET_DISCARDED",
                    details={"reason": "NO_CONFIRMED_BROKER_POSITION"},
                ))
                # False is intentional: callers must not start a profit/loss
                # cooldown for a basket which never contained a real position.
                return False
            basket.status = BasketState.CLOSED.value
            basket.closed_at = datetime.now(UTC)
            basket.position_count = 0
            basket.total_volume = 0
            basket.close_reason = reason.value
            session.add(BasketEvent(basket_id=basket.id, event_type="BASKET_EMPTY_AFTER_BROKER_EXITS", details={"reason": reason.value}))
            return True

    def synchronize(self, basket_external_id: str) -> BasketMetrics:
        all_positions = self.broker.positions(self.symbol, self.config.broker.magic_number)
        with self.database.transaction() as session:
            basket = session.scalar(select(Basket).where(Basket.external_id == basket_external_id))
            if basket is None:
                raise ValueError("Basket not found")
            now = datetime.now(UTC)
            tracked = list(session.scalars(select(Trade).where(Trade.basket_id == basket.id)))
            tracked_tickets = {item.broker_ticket for item in tracked if item.broker_ticket is not None}
            positions = [position for position in all_positions if position.ticket in tracked_tickets]
            trade_by_ticket = {item.broker_ticket: item for item in tracked if item.broker_ticket is not None}
            try:
                deals = self.broker.deals(ensure_utc(basket.opened_at) if basket.opened_at else now, now, self.symbol, self.config.broker.magic_number)
            except Exception:
                deals = []
            trade_ids = [item.id for item in tracked]
            events = list(session.scalars(select(TradeEvent).where(TradeEvent.trade_id.in_(trade_ids), TradeEvent.event_type == "BROKER_DEAL_RECONCILED"))) if trade_ids else []
            estimate_events = list(session.scalars(select(TradeEvent).where(TradeEvent.trade_id.in_(trade_ids), TradeEvent.event_type == "BROKER_EXIT_ESTIMATED"))) if trade_ids else []
            seen_deals = {int(item.details["deal_ticket"]) for item in events if "deal_ticket" in item.details}
            estimated_by_trade: dict[int, float] = {}
            for event in estimate_events:
                if event.trade_id is not None:
                    estimated_by_trade[event.trade_id] = estimated_by_trade.get(event.trade_id, 0.0) + float(event.details.get("monetary", 0.0))
            actual_by_trade = {
                event.trade_id
                for event in events
                if str(event.details.get("entry", "")).upper() not in ("IN", "ENTRY_IN")
            }
            open_tickets = {item.ticket for item in positions}
            for deal in deals:
                trade = trade_by_ticket.get(deal.position_id)
                if trade is None or deal.ticket in seen_deals:
                    continue
                is_exit_deal = str(deal.entry).upper() not in ("IN", "ENTRY_IN")
                monetary = deal.profit + deal.commission + deal.swap
                if is_exit_deal and trade.id in estimated_by_trade and trade.id not in actual_by_trade:
                    trade.realized_profit -= estimated_by_trade[trade.id]
                    session.add(TradeEvent(trade_id=trade.id, event_type="BROKER_EXIT_ESTIMATE_REPLACED", details={
                        "estimated_monetary": estimated_by_trade[trade.id],
                        "replacement_deal_ticket": deal.ticket,
                    }))
                    actual_by_trade.add(trade.id)
                if is_exit_deal:
                    trade.realized_profit += monetary
                session.add(TradeEvent(trade_id=trade.id, event_type="BROKER_DEAL_RECONCILED", details={
                    "deal_ticket": deal.ticket, "position_id": deal.position_id, "symbol": deal.symbol,
                    "side": deal.side, "volume": deal.volume, "price": deal.price, "profit": deal.profit,
                    "commission": deal.commission, "swap": deal.swap, "entry": deal.entry,
                    "time": deal.time.isoformat(),
                }))
                seen_deals.add(deal.ticket)
            for trade in tracked:
                if trade.broker_ticket not in open_tickets and trade.state in (TradeState.OPEN.value, TradeState.PARTIALLY_CLOSED.value):
                    trade.state = TradeState.CLOSED.value
                    trade.closed_at = now
                    trade.close_reason = trade.close_reason or "BROKER_SIDE_EXIT"
                    if trade.id not in actual_by_trade and trade.id not in estimated_by_trade and abs(trade.realized_profit) < 1e-9 and abs(trade.floating_profit) > 1e-9:
                        trade.realized_profit = trade.floating_profit
                        session.add(TradeEvent(trade_id=trade.id, event_type="BROKER_EXIT_ESTIMATED", details={
                            "ticket": trade.broker_ticket,
                            "monetary": trade.floating_profit,
                            "source": "last_floating_profit",
                            "closed_at": now.isoformat(),
                        }))
            realized = sum(item.realized_profit for item in tracked)
            basket.total_realized_profit = realized
            metrics = self.metrics(positions, realized)
            basket.position_count = metrics.position_count
            basket.total_volume = metrics.total_volume
            basket.weighted_average_entry = metrics.weighted_average_entry
            basket.total_floating_profit = metrics.floating_profit
            basket.maximum_floating_profit = max(basket.maximum_floating_profit, metrics.combined_profit)
            basket.maximum_drawdown = max(basket.maximum_drawdown, max(0.0, basket.maximum_floating_profit - metrics.combined_profit))
            for position in positions:
                trade = session.scalar(select(Trade).where(Trade.broker_ticket == position.ticket))
                if trade:
                    trade.volume = position.volume
                    trade.floating_profit = position.profit
                    trade.max_adverse_profit = min(float(trade.max_adverse_profit or 0.0), float(position.profit))
                    trade.max_favorable_profit = max(float(trade.max_favorable_profit or 0.0), float(position.profit))
                    risk = float(trade.initial_risk_amount or 0.0)
                    if risk > 0:
                        trade.max_adverse_r = max(float(trade.max_adverse_r or 0.0), abs(min(0.0, float(trade.max_adverse_profit))) / risk)
                        trade.max_favorable_r = max(float(trade.max_favorable_r or 0.0), max(0.0, float(trade.max_favorable_profit)) / risk)
                    trade.stop_loss = position.stop_loss
                    trade.take_profit = position.take_profit
            session.add(BasketEvent(basket_id=basket.id, event_type="BASKET_SNAPSHOT", details={"position_count": metrics.position_count, "floating_profit": metrics.floating_profit, "combined_profit": metrics.combined_profit}))
            return metrics

    def exit_decision(self, metrics: BasketMetrics, initial_risk: float, account_equity: float, basket_external_id: str | None = None) -> BasketExitDecision:
        profit = metrics.combined_profit
        take = self.config.basket_take_profit
        if take.enabled:
            if self._basket_is_fast_only(basket_external_id):
                target = take.fast_target_fixed_usd
            elif take.mode is BasketProfitMode.R_MULTIPLE:
                target = initial_risk * take.target_r_multiple
            elif take.mode is BasketProfitMode.FIXED_USD:
                target = take.target_fixed_usd
            else:
                target = account_equity * take.target_equity_percent / 100
            if profit >= target:
                return BasketExitDecision(True, CloseReason.TAKE_PROFIT, profit, target)
        protection = self.config.profit_protection
        if protection.enabled:
            peak_profit, break_even_applied = self._profit_protection_snapshot(basket_external_id)
            if not protection.require_break_even_applied or break_even_applied:
                giveback = max(0.0, peak_profit - profit)
                giveback_limit = peak_profit * protection.giveback_percent / 100
                gave_back_too_much = peak_profit >= protection.minimum_peak_profit_usd and giveback >= giveback_limit
                hit_hard_floor = peak_profit >= protection.hard_peak_profit_usd and profit <= protection.hard_floor_profit_usd
                if gave_back_too_much or hit_hard_floor:
                    threshold = max(0.0, peak_profit - giveback_limit)
                    return BasketExitDecision(True, CloseReason.PROFIT_PROTECTION, profit, threshold)
        stop = self.config.basket_stop_loss
        if stop.enabled:
            usd_threshold = self.basket_stop_loss_threshold(account_equity)
            if usd_threshold is not None and profit <= -usd_threshold:
                return BasketExitDecision(True, CloseReason.STOP_LOSS, profit, usd_threshold)
            if stop.mode is BasketStopLossMode.FIXED_USD:
                percent_threshold = account_equity * stop.maximum_loss_percent / 100
                if profit <= -percent_threshold:
                    return BasketExitDecision(True, CloseReason.STOP_LOSS, profit, min(stop.maximum_loss_usd, percent_threshold))
        return BasketExitDecision(False, None, profit, None)

    def close_basket(self, basket_external_id: str, reason: CloseReason) -> bool:
        lock = self._lock_for(basket_external_id)
        if not lock.acquire(blocking=False):
            return False
        try:
            with self.database.transaction() as session:
                basket = session.scalar(select(Basket).where(Basket.external_id == basket_external_id))
                if basket is None or basket.status == BasketState.CLOSED.value:
                    return basket is not None
                close_attempt_offset = basket.close_attempts
                basket.status = BasketState.CLOSING.value
                session.add(BasketEvent(basket_id=basket.id, event_type="BASKET_CLOSING", details={"reason": reason.value}))
            maximum_attempts = self.config.execution.maximum_retries + 1
            for attempt in range(1, maximum_attempts + 1):
                positions = self.basket_positions(basket_external_id)
                if not positions:
                    break
                for position in positions:
                    key = f"basket-close:{basket_external_id}:{position.ticket}:{close_attempt_offset + attempt}"
                    self.execution.close(position, position.volume, self.spec, key, reason.value)
            remaining = self.basket_positions(basket_external_id)
            if not remaining:
                self.synchronize(basket_external_id)
            with self.database.transaction() as session:
                basket = session.scalar(select(Basket).where(Basket.external_id == basket_external_id))
                if basket is None:
                    return False
                basket.close_attempts += maximum_attempts
                if remaining:
                    basket.status = BasketState.CLOSE_FAILED.value
                    session.add(BasketEvent(
                        basket_id=basket.id,
                        event_type="BASKET_CLOSE_FAILED",
                        details={"reason": reason.value, "remaining_tickets": [item.ticket for item in remaining]},
                    ))
                    return False
                basket.status = BasketState.CLOSED.value
                basket.closed_at = datetime.now(UTC)
                basket.position_count = 0
                basket.total_volume = 0
                basket.close_reason = reason.value
                trades = list(session.scalars(select(Trade).where(Trade.basket_id == basket.id, Trade.state.in_((TradeState.OPEN.value, TradeState.PARTIALLY_CLOSED.value)))))
                for trade in trades:
                    trade.state = TradeState.CLOSED.value
                    trade.closed_at = datetime.now(UTC)
                    trade.close_reason = reason.value
                session.add(BasketEvent(basket_id=basket.id, event_type="BASKET_CLOSED", details={"reason": reason.value}))
                return True
        finally:
            lock.release()
