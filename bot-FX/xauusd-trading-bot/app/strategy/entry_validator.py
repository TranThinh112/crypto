"""Cross-cutting entry invariants, independent from broker/API code."""

from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import PositionControlConfig, RiskConfig
from app.strategy.trend_detector import RuleResult
from app.utils.enums import SignalSide


@dataclass(frozen=True, slots=True)
class EntryContext:
    side: SignalSide
    open_position_sides: tuple[str, ...]
    open_position_count: int
    same_side_count: int
    basket_floating_profit: float
    total_open_risk_percent: float
    proposed_risk_percent: float
    total_open_lot: float
    proposed_lot: float
    entry_distance_atr: float | None
    new_setup_candle: bool
    entry_cooldown_clear: bool
    cooldown_active: bool
    daily_risk_locked: bool
    idempotency_key_exists: bool


@dataclass(frozen=True, slots=True)
class EntryValidation:
    passed: bool
    rules: tuple[RuleResult, ...]

    @property
    def rejection_reason(self) -> str | None:
        failed = [rule.reason_code for rule in self.rules if not rule.passed]
        return None if not failed else ",".join(failed)


class EntryValidator:
    def __init__(self, position: PositionControlConfig, risk: RiskConfig) -> None:
        self.position = position
        self.risk = risk

    def validate(self, context: EntryContext) -> EntryValidation:
        opposite = "SELL" if context.side is SignalSide.BUY else "BUY"
        side_limit = self.position.max_buy_positions if context.side is SignalSide.BUY else self.position.max_sell_positions
        open_count_ok = self.position.max_open_positions is None or context.open_position_count < self.position.max_open_positions
        side_count_ok = side_limit is None or context.same_side_count < side_limit
        opposite_ok = self.position.allow_opposite_positions or opposite not in context.open_position_sides
        basket_risk_ok = self.risk.max_basket_risk_percent is None or (
            context.total_open_risk_percent + context.proposed_risk_percent <= self.risk.max_basket_risk_percent + 1e-12
        )
        total_lot_ok = self.risk.max_total_lot is None or (
            context.total_open_lot + context.proposed_lot <= self.risk.max_total_lot + 1e-12
        )
        distance_ok = context.open_position_count == 0 or (
            context.entry_distance_atr is not None and context.entry_distance_atr >= self.position.minimum_entry_distance_atr
        )
        rules = (
            RuleResult(context.side in (SignalSide.BUY, SignalSide.SELL), "VALID_TRADE_SIDE", {"side": context.side.value}),
            RuleResult(opposite_ok, "NO_OPPOSITE_BASKET", {"existing": context.open_position_sides, "allow_opposite": self.position.allow_opposite_positions}),
            RuleResult(open_count_ok, "MAX_OPEN_POSITIONS", {"current": context.open_position_count, "maximum": self.position.max_open_positions}),
            RuleResult(side_count_ok, "MAX_SIDE_POSITIONS", {"current": context.same_side_count, "maximum": side_limit}),
            RuleResult(not (self.position.prohibit_adding_to_losing_basket and context.open_position_count and context.basket_floating_profit < 0), "NOT_ADDING_TO_LOSING_BASKET", {"basket_profit": context.basket_floating_profit}),
            RuleResult(basket_risk_ok, "BASKET_RISK_LIMIT", {"current": context.total_open_risk_percent, "proposed": context.proposed_risk_percent, "maximum": self.risk.max_basket_risk_percent}),
            RuleResult(total_lot_ok, "TOTAL_LOT_LIMIT", {"after": context.total_open_lot + context.proposed_lot, "maximum": self.risk.max_total_lot}),
            RuleResult(distance_ok, "MINIMUM_ENTRY_DISTANCE", {"distance_atr": context.entry_distance_atr, "minimum": self.position.minimum_entry_distance_atr}),
            RuleResult(context.new_setup_candle, "NEW_SETUP_CANDLE", {}),
            RuleResult(context.entry_cooldown_clear, "ENTRY_COOLDOWN_CLEAR", {}),
            RuleResult(not context.cooldown_active, "COOLDOWN_CLEAR", {}),
            RuleResult(not context.daily_risk_locked, "DAILY_RISK_CLEAR", {}),
            RuleResult(not context.idempotency_key_exists, "IDEMPOTENCY_KEY_UNIQUE", {}),
        )
        return EntryValidation(all(rule.passed for rule in rules), rules)
