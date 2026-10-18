"""ATR trailing stop that only ever reduces risk."""

from app.broker.mt5_client import BrokerPosition, SymbolSpec
from app.config.settings import TrailingStopConfig
from app.positions.break_even_manager import StopUpdateDecision
from app.utils.calculations import normalize_price, risk_multiple


class TrailingStopManager:
    def __init__(self, config: TrailingStopConfig) -> None:
        self.config = config

    def evaluate(self, position: BrokerPosition, initial_stop: float, atr: float, spec: SymbolSpec) -> StopUpdateDecision:
        if not self.config.enabled:
            return StopUpdateDecision(False, None, "TRAILING_DISABLED")
        r_value = risk_multiple(position.side, position.current_price, position.entry_price, initial_stop)
        if r_value < self.config.activation_r_multiple:
            return StopUpdateDecision(False, None, "TRAILING_TRIGGER_NOT_REACHED")
        if atr <= 0:
            return StopUpdateDecision(False, None, "TRAILING_INVALID_ATR")
        candidate = position.current_price - atr * self.config.atr_multiplier if position.side == "BUY" else position.current_price + atr * self.config.atr_multiplier
        candidate = normalize_price(candidate, spec.digits)
        minimum_step = self.config.update_step_points * spec.point
        improvement = candidate - position.stop_loss if position.side == "BUY" else (position.stop_loss - candidate if position.stop_loss else float("inf"))
        if improvement + 1e-12 < minimum_step:
            return StopUpdateDecision(False, None, "TRAILING_UPDATE_STEP_NOT_REACHED")
        if abs(position.current_price - candidate) < spec.trade_stops_level * spec.point:
            return StopUpdateDecision(False, None, "TRAILING_BROKER_STOP_LEVEL")
        return StopUpdateDecision(True, candidate, "TRAILING_STOP_ADVANCED")
