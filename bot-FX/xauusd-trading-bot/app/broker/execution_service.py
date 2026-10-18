"""Idempotent, audited and broker-aware order execution."""

from __future__ import annotations

import json
import logging
import math
import re
import time
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.broker.mt5_client import BrokerClient, BrokerOrderRequest, BrokerPosition, BrokerResult, SymbolSpec
from app.config.settings import TradingConfig
from app.database import Database
from app.models.trade import ExecutionRequest, Trade, TradeEvent
from app.risk.margin_guard import MarginGuard
from app.risk.position_sizing import SizingResult
from app.risk.risk_manager import PricePlan
from app.utils.calculations import normalize_price, normalize_volume
from app.utils.enums import OrderAction, TradeState, TradingMode


@dataclass(frozen=True, slots=True)
class OrderIntent:
    symbol: str
    idempotency_key: str
    signal_hash: str
    entry_candle_time: datetime
    basket_id: int | None
    basket_external_id: str
    entry_number: int
    price_plan: PricePlan
    sizing: SizingResult
    atr: float


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    success: bool
    trade_id: int | None
    broker_ticket: int | None
    reason: str
    duplicate: bool = False
    broker_result: BrokerResult | None = None


class ExecutionService:
    """The only service authorized to mutate broker positions."""

    MAX_TICK_AGE_SECONDS = 30
    TICK_REFRESH_ATTEMPTS = 3
    TICK_REFRESH_DELAY_SECONDS = 1.0

    def __init__(self, broker: BrokerClient, database: Database, config: TradingConfig, live_enabled: bool = False) -> None:
        self.broker = broker
        self.database = database
        self.config = config
        self.live_enabled = live_enabled
        self.margin_guard = MarginGuard(broker, config.risk)
        self.log = logging.getLogger("execution")

    @staticmethod
    def _json_safe(value: Any) -> dict[str, Any]:
        return json.loads(json.dumps(value, default=str))

    def _comment(self, basket_id: str, entry_number: int, signal_hash: str) -> str:
        prefix = self.config.broker.order_comment_prefix[:12]
        raw = f"{prefix}_b{basket_id[:6]}_e{entry_number}_s{signal_hash[:4]}"
        # Some MT5 brokers reject punctuation such as ``|`` and ``=`` even
        # though the terminal API accepts the Python string. Keep the broker
        # comment deliberately conservative and within MT5's 31-char limit.
        return re.sub(r"[^A-Za-z0-9_]", "_", raw)[:31]

    def _reserve(self, intent: OrderIntent) -> tuple[Trade | None, ExecutionRequest | None, ExecutionOutcome | None]:
        with self.database.transaction() as session:
            existing_request = session.scalar(select(ExecutionRequest).where(ExecutionRequest.idempotency_key == intent.idempotency_key))
            if existing_request is not None:
                trade = session.get(Trade, existing_request.trade_id) if existing_request.trade_id else None
                success = bool(trade and trade.state in (TradeState.OPEN.value, TradeState.PARTIALLY_CLOSED.value, TradeState.CLOSED.value))
                return None, None, ExecutionOutcome(success, trade.id if trade else None, trade.broker_ticket if trade else None, "DUPLICATE_IDEMPOTENCY_KEY", True)
            trade = Trade(
                basket_id=intent.basket_id, idempotency_key=intent.idempotency_key, symbol=intent.symbol,
                side=intent.price_plan.side.value, state=TradeState.PLANNED.value, volume=intent.sizing.volume,
                initial_volume=intent.sizing.volume, entry_price=intent.price_plan.entry,
                stop_loss=intent.price_plan.stop_loss, initial_stop_loss=intent.price_plan.stop_loss,
                take_profit=intent.price_plan.take_profit, signal_hash=intent.signal_hash,
                entry_number=intent.entry_number, initial_risk_amount=intent.sizing.loss_per_lot * intent.sizing.volume,
                max_adverse_profit=0, max_favorable_profit=0, max_adverse_r=0, max_favorable_r=0,
                entry_candle_time=intent.entry_candle_time, partial_levels_completed=[],
            )
            session.add(trade)
            session.flush()
            request = ExecutionRequest(
                idempotency_key=intent.idempotency_key, trade_id=trade.id, action=OrderAction.OPEN.value,
                status="PENDING", request_payload=self._json_safe(asdict(intent)), response_payload={},
            )
            session.add(request)
            session.flush()
            trade_id, request_id = trade.id, request.id
        with self.database.transaction() as session:
            return session.get(Trade, trade_id), session.get(ExecutionRequest, request_id), None

    def _finalize(self, trade_id: int, request_id: int, trade_state: TradeState, status: str, reason: str, result: BrokerResult | None = None, attempts: int = 0) -> None:
        with self.database.transaction() as session:
            trade = session.get(Trade, trade_id)
            request = session.get(ExecutionRequest, request_id)
            if trade is None or request is None:
                return
            trade.state = trade_state.value
            request.status = status
            request.attempt_count = attempts
            request.error_message = None if status == "SUCCESS" else reason
            request.response_payload = self._json_safe(result.raw if result else {"reason": reason})
            request.completed_at = datetime.now(UTC)
            if result and result.success:
                trade.broker_ticket = result.order_ticket or result.deal_ticket
                trade.entry_price = result.price or trade.entry_price
                trade.volume = result.volume or trade.volume
                trade.opened_at = datetime.now(UTC)
            session.add(TradeEvent(trade_id=trade.id, event_type=f"EXECUTION_{status}", details={"reason": reason, "retcode": result.retcode if result else None, "attempts": attempts}))

    def _validate(self, intent: OrderIntent, spec: SymbolSpec) -> tuple[bool, str, float]:
        if intent.symbol != spec.name or intent.symbol not in self.config.symbol.allowed_aliases:
            return False, "SYMBOL_NOT_APPROVED", 0
        if spec.trade_mode in (0, 3) or (spec.trade_mode == 1 and intent.price_plan.side.value == "SELL") or (spec.trade_mode == 2 and intent.price_plan.side.value == "BUY"):
            return False, "SYMBOL_NOT_TRADEABLE_FOR_SIDE", 0
        if self.config.bot.mode == TradingMode.LIVE and not self.live_enabled:
            return False, "LIVE_TRADING_ENV_NOT_ENABLED", 0
        tick = self.broker.tick(intent.symbol)
        age = (datetime.now(UTC) - tick.time).total_seconds()
        for attempt in range(self.TICK_REFRESH_ATTEMPTS):
            if -5 <= age <= self.MAX_TICK_AGE_SECONDS:
                break
            self.log.warning(
                "Broker tick is stale before order validation; retrying tick refresh",
                extra={
                    "event_type": "STALE_TICK_REFRESH",
                    "symbol": intent.symbol,
                    "context": {
                        "attempt": attempt + 1,
                        "age_seconds": age,
                        "maximum_age_seconds": self.MAX_TICK_AGE_SECONDS,
                    },
                },
            )
            time.sleep(self.TICK_REFRESH_DELAY_SECONDS)
            tick = self.broker.tick(intent.symbol)
            age = (datetime.now(UTC) - tick.time).total_seconds()
        if age < -5 or age > self.MAX_TICK_AGE_SECONDS:
            return False, f"STALE_TICK:{age:.1f}s", 0
        price = tick.ask if intent.price_plan.side.value == "BUY" else tick.bid
        drift = abs(price - intent.price_plan.entry) / spec.point
        if drift > self.config.execution.reject_if_price_changed_points:
            return False, f"PRICE_CHANGED:{drift:.1f}", price
        spread_points = (tick.ask - tick.bid) / spec.point
        spread_atr_ratio = (tick.ask - tick.bid) / intent.atr if intent.atr > 0 else float("inf")
        spread_cfg = self.config.spread_guard
        if spread_cfg.enabled and (spread_points > spread_cfg.maximum_spread_points or spread_atr_ratio > spread_cfg.maximum_spread_atr_ratio):
            return False, f"SPREAD_TOO_HIGH:{spread_points:.1f}", price
        stop_distance = abs(price - intent.price_plan.stop_loss)
        if stop_distance < spec.trade_stops_level * spec.point:
            return False, "BROKER_STOP_LEVEL_VIOLATION", price
        geometry_ok = intent.price_plan.stop_loss < price < intent.price_plan.take_profit if intent.price_plan.side.value == "BUY" else intent.price_plan.take_profit < price < intent.price_plan.stop_loss
        if not geometry_ok:
            return False, "INVALID_SL_TP_GEOMETRY", price
        actual_reward = abs(intent.price_plan.take_profit - price)
        actual_rr = actual_reward / stop_distance if stop_distance > 0 else 0
        if actual_rr + 1e-12 < self.config.take_profit.minimum_risk_reward:
            return False, f"RISK_REWARD_CHANGED:{actual_rr:.3f}", price
        actual_risk = stop_distance / spec.trade_tick_size * spec.trade_tick_value * intent.sizing.volume
        if actual_risk > intent.sizing.risk_amount + max(0.01, intent.sizing.risk_amount * 0.001):
            return False, f"RISK_AMOUNT_CHANGED:{actual_risk:.2f}", price
        volume_cap = spec.volume_max if self.config.risk.max_lot_per_entry is None else min(spec.volume_max, self.config.risk.max_lot_per_entry)
        normalized_volume = normalize_volume(intent.sizing.volume, spec.volume_min, volume_cap, spec.volume_step)
        if normalized_volume <= 0 or abs(normalized_volume - intent.sizing.volume) > 1e-10:
            return False, "INVALID_NORMALIZED_VOLUME", price
        margin = self.margin_guard.validate(intent.price_plan.side.value, intent.symbol, intent.sizing.volume, price, self.broker.account())
        if not margin.passed:
            return False, "INSUFFICIENT_MARGIN", price
        return True, "VALIDATED", price

    def submit(self, intent: OrderIntent) -> ExecutionOutcome:
        trade, audit, duplicate = self._reserve(intent)
        if duplicate is not None:
            return duplicate
        assert trade is not None and audit is not None
        spec = self.broker.symbol_spec(intent.symbol)
        passed, reason, price = self._validate(intent, spec)
        if not passed:
            self.log.warning("Order rejected before send", extra={"event_type": "ORDER_VALIDATION_REJECTED", "symbol": intent.symbol, "trade_id": trade.id, "context": {"reason": reason}})
            self._finalize(trade.id, audit.id, TradeState.REJECTED, "REJECTED", reason)
            return ExecutionOutcome(False, trade.id, None, reason)

        with self.database.transaction() as session:
            db_trade, db_request = session.get(Trade, trade.id), session.get(ExecutionRequest, audit.id)
            if db_trade:
                db_trade.state = TradeState.SUBMITTED.value
            if db_request:
                db_request.status = "SUBMITTED"

        request = BrokerOrderRequest(
            symbol=intent.symbol, side=intent.price_plan.side.value, volume=intent.sizing.volume,
            price=normalize_price(price, spec.digits), stop_loss=normalize_price(intent.price_plan.stop_loss, spec.digits),
            take_profit=normalize_price(intent.price_plan.take_profit, spec.digits),
            deviation_points=self.config.execution.deviation_points, magic=self.config.broker.magic_number,
            comment=self._comment(intent.basket_external_id, intent.entry_number, intent.signal_hash),
        )
        last_result: BrokerResult | None = None
        maximum_attempts = self.config.execution.maximum_retries + 1
        for attempt in range(1, maximum_attempts + 1):
            current = self.broker.tick(intent.symbol)
            current_price = current.ask if request.side == "BUY" else current.bid
            current_spread = (current.ask - current.bid) / spec.point
            if abs(current_price - request.price) / spec.point > self.config.execution.reject_if_price_changed_points:
                reason = "PRICE_MOVED_DURING_RETRY"
                break
            if current_spread > self.config.spread_guard.maximum_spread_points:
                reason = "SPREAD_CHANGED_DURING_RETRY"
                break
            request = BrokerOrderRequest(**{**asdict(request), "price": normalize_price(current_price, spec.digits)})
            self.log.info("Sending broker order", extra={"event_type": "ORDER_SEND", "symbol": intent.symbol, "trade_id": trade.id, "context": {"attempt": attempt, "spread_points": current_spread, "price": current_price, "volume": request.volume}})
            last_result = self.broker.place_market_order(request)
            if last_result.success:
                confirmation_tick = self.broker.tick(intent.symbol)
                candidates = self.broker.positions(intent.symbol, self.config.broker.magic_number)
                returned_tickets = {value for value in (last_result.order_ticket, last_result.deal_ticket) if value is not None}
                matched = next((item for item in candidates if item.ticket in returned_tickets), None)
                if matched is None:
                    comments = [item for item in candidates if item.comment == request.comment and item.side == request.side]
                    matched = max(comments, key=lambda item: item.opened_at, default=None)
                raw = {
                    **last_result.raw,
                    "spread_points_pre_send": current_spread,
                    "spread_points_broker_confirmation": (confirmation_tick.ask - confirmation_tick.bid) / spec.point,
                    "confirmed_position_ticket": matched.ticket if matched else None,
                }
                if matched is None:
                    unconfirmed = replace(last_result, raw=raw)
                    reason = "ORDER_FILLED_BUT_POSITION_CONFIRMATION_MISSING"
                    self.log.error("Filled order could not be matched to a position", extra={"event_type": "ORDER_CONFIRMATION_MISSING", "symbol": intent.symbol, "trade_id": trade.id, "context": raw})
                    self._finalize(trade.id, audit.id, TradeState.SUBMITTED, "UNCONFIRMED", reason, unconfirmed, attempt)
                    return ExecutionOutcome(False, trade.id, last_result.order_ticket or last_result.deal_ticket, reason, False, unconfirmed)
                confirmed = replace(last_result, order_ticket=matched.ticket, price=matched.entry_price, volume=matched.volume, raw=raw)
                self.log.info("Broker position confirmed", extra={"event_type": "ORDER_CONFIRMED", "symbol": intent.symbol, "trade_id": trade.id, "context": {"position_ticket": matched.ticket, "spread_points": raw["spread_points_broker_confirmation"]}})
                self._finalize(trade.id, audit.id, TradeState.OPEN, "SUCCESS", "ORDER_FILLED", confirmed, attempt)
                return ExecutionOutcome(True, trade.id, matched.ticket, "ORDER_FILLED", False, confirmed)
            # A transport timeout can hide a successful fill. Reconcile by the
            # unique broker comment before any retry to avoid a duplicate order.
            ambiguous_matches = [
                item for item in self.broker.positions(intent.symbol, self.config.broker.magic_number)
                if item.comment == request.comment and item.side == request.side
            ]
            if ambiguous_matches:
                matched = max(ambiguous_matches, key=lambda item: item.opened_at)
                confirmation_tick = self.broker.tick(intent.symbol)
                recovered = BrokerResult(
                    True, last_result.retcode, matched.ticket, last_result.deal_ticket,
                    matched.entry_price, matched.volume, "position confirmed after ambiguous broker response",
                    {**last_result.raw, "ambiguous_response": True, "confirmed_position_ticket": matched.ticket,
                     "spread_points_broker_confirmation": (confirmation_tick.ask - confirmation_tick.bid) / spec.point},
                )
                self._finalize(trade.id, audit.id, TradeState.OPEN, "SUCCESS", "ORDER_CONFIRMED_AFTER_AMBIGUOUS_RESPONSE", recovered, attempt)
                return ExecutionOutcome(True, trade.id, matched.ticket, "ORDER_CONFIRMED_AFTER_AMBIGUOUS_RESPONSE", False, recovered)
            reason = f"BROKER_RETCODE:{last_result.retcode}:{last_result.comment}"
            if attempt < maximum_attempts:
                time.sleep(self.config.execution.retry_delay_seconds)
        self._finalize(trade.id, audit.id, TradeState.FAILED, "FAILED", reason, last_result, maximum_attempts)
        return ExecutionOutcome(False, trade.id, None, reason, False, last_result)

    def _management_audit(self, key: str, action: OrderAction, ticket: int, payload: dict[str, Any]) -> tuple[int | None, bool]:
        with self.database.transaction() as session:
            existing = session.scalar(select(ExecutionRequest).where(ExecutionRequest.idempotency_key == key))
            if existing:
                return existing.id, True
            trade = session.scalar(select(Trade).where(Trade.broker_ticket == ticket))
            audit = ExecutionRequest(idempotency_key=key, trade_id=trade.id if trade else None, action=action.value, status="PENDING", request_payload=self._json_safe(payload), response_payload={})
            session.add(audit)
            session.flush()
            return audit.id, False

    def _finish_management(self, audit_id: int, result: BrokerResult, estimated_profit: float | None = None) -> None:
        with self.database.transaction() as session:
            audit = session.get(ExecutionRequest, audit_id)
            if audit:
                audit.status = "SUCCESS" if result.success else "FAILED"
                audit.attempt_count = 1
                audit.response_payload = self._json_safe(result.raw)
                audit.error_message = None if result.success else result.comment
                audit.completed_at = datetime.now(UTC)
                trade = session.get(Trade, audit.trade_id) if audit.trade_id else None
                if trade and result.success:
                    if audit.action == OrderAction.MODIFY.value:
                        trade.stop_loss = float(audit.request_payload["new_stop"])
                    elif audit.action == OrderAction.PARTIAL_CLOSE.value:
                        trade.volume = max(0.0, trade.volume - float(audit.request_payload["volume"]))
                        trade.state = TradeState.PARTIALLY_CLOSED.value
                    elif audit.action == OrderAction.CLOSE.value:
                        trade.volume = 0
                        trade.state = TradeState.CLOSED.value
                        trade.closed_at = datetime.now(UTC)
                        trade.close_reason = str(audit.request_payload.get("reason", "CLOSE"))
                        trade.floating_profit = 0
                    if audit.action in (OrderAction.PARTIAL_CLOSE.value, OrderAction.CLOSE.value) and estimated_profit is not None:
                        trade.realized_profit += estimated_profit
                        session.add(TradeEvent(
                            trade_id=trade.id,
                            event_type="BROKER_EXIT_ESTIMATED",
                            details={
                                "ticket": trade.broker_ticket,
                                "monetary": estimated_profit,
                                "volume": audit.request_payload.get("volume"),
                                "price": result.price,
                                "source": "management_close_result",
                                "closed_at": datetime.now(UTC).isoformat(),
                            },
                        ))

    def modify_stop(self, position: BrokerPosition, new_stop: float, take_profit: float, spec: SymbolSpec, idempotency_key: str) -> BrokerResult | None:
        normalized = normalize_price(new_stop, spec.digits)
        improves = normalized > position.stop_loss if position.side == "BUY" else (position.stop_loss == 0 or normalized < position.stop_loss)
        tick = self.broker.tick(position.symbol)
        market_price = tick.bid if position.side == "BUY" else tick.ask
        distance_ok = abs(market_price - normalized) >= spec.trade_stops_level * spec.point
        if not improves or not distance_ok:
            return None
        audit_id, duplicate = self._management_audit(idempotency_key, OrderAction.MODIFY, position.ticket, {"new_stop": normalized, "take_profit": take_profit})
        if duplicate or audit_id is None:
            return None
        result = self.broker.modify_position(position.ticket, position.symbol, normalized, normalize_price(take_profit, spec.digits))
        self._finish_management(audit_id, result)
        return result

    @staticmethod
    def _estimate_close_profit(position: BrokerPosition, volume: float, spec: SymbolSpec, result: BrokerResult) -> float | None:
        if not result.success:
            return None
        raw_value = result.raw.get("realized_profit") if isinstance(result.raw, dict) else None
        if raw_value is not None:
            try:
                value = float(raw_value)
                if math.isfinite(value):
                    return value
            except (TypeError, ValueError):
                pass
        if result.price is None or spec.trade_tick_size <= 0 or spec.trade_tick_value <= 0:
            return None
        movement = result.price - position.entry_price if position.side == "BUY" else position.entry_price - result.price
        value = movement / spec.trade_tick_size * spec.trade_tick_value * volume
        return value if math.isfinite(value) else None

    def close(self, position: BrokerPosition, volume: float, spec: SymbolSpec, idempotency_key: str, reason: str) -> BrokerResult | None:
        normalized = normalize_volume(volume, spec.volume_min, position.volume, spec.volume_step)
        if normalized <= 0:
            return None
        audit_id, duplicate = self._management_audit(idempotency_key, OrderAction.CLOSE if abs(normalized - position.volume) < 1e-10 else OrderAction.PARTIAL_CLOSE, position.ticket, {"volume": normalized, "reason": reason})
        if duplicate or audit_id is None:
            return None
        result = self.broker.close_position(position, normalized, self.config.execution.deviation_points, reason[:31])
        self._finish_management(audit_id, result, self._estimate_close_profit(position, normalized, spec, result))
        return result
