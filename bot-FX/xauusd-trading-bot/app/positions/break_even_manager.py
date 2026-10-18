"""One-way break-even stop calculation."""

from dataclasses import dataclass

from app.broker.mt5_client import BrokerPosition, SymbolSpec
from app.config.settings import BreakEvenConfig
from app.utils.calculations import normalize_price, risk_multiple


@dataclass(frozen=True, slots=True)
class StopUpdateDecision:
    should_update: bool
    new_stop: float | None
    reason: str


class BreakEvenManager:
    def __init__(self, config: BreakEvenConfig) -> None:
        self.config = config

    def evaluate(self, position: BrokerPosition, initial_stop: float, spec: SymbolSpec, already_applied: bool) -> StopUpdateDecision:
        if not self.config.enabled:
            return StopUpdateDecision(False, None, "BREAK_EVEN_DISABLED")
        if self.config.apply_once and already_applied:
            return StopUpdateDecision(False, None, "BREAK_EVEN_ALREADY_APPLIED")
        r_value = risk_multiple(position.side, position.current_price, position.entry_price, initial_stop)
        if r_value < self.config.trigger_r_multiple:
            return StopUpdateDecision(False, None, "BREAK_EVEN_TRIGGER_NOT_REACHED")
        lock = self.config.lock_profit_points * spec.point
        candidate = position.entry_price + lock if position.side == "BUY" else position.entry_price - lock
        candidate = normalize_price(candidate, spec.digits)
        improves = candidate > position.stop_loss if position.side == "BUY" else (position.stop_loss == 0 or candidate < position.stop_loss)
        market_distance = abs(position.current_price - candidate)
        if not improves:
            return StopUpdateDecision(False, None, "BREAK_EVEN_NOT_AN_IMPROVEMENT")
        if market_distance < spec.trade_stops_level * spec.point:
            return StopUpdateDecision(False, None, "BREAK_EVEN_BROKER_STOP_LEVEL")
        return StopUpdateDecision(True, candidate, "BREAK_EVEN_TRIGGERED")
