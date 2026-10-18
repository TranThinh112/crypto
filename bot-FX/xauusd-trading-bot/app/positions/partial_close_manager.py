"""Idempotent partial-close volume planning."""

from dataclasses import dataclass

from app.broker.mt5_client import BrokerPosition, SymbolSpec
from app.config.settings import PartialCloseConfig
from app.utils.calculations import normalize_volume, risk_multiple


@dataclass(frozen=True, slots=True)
class PartialCloseDecision:
    should_close: bool
    trigger_r: float | None
    volume: float
    reason: str


class PartialCloseManager:
    def __init__(self, config: PartialCloseConfig) -> None:
        self.config = config

    def evaluate(self, position: BrokerPosition, initial_volume: float, initial_stop: float, completed_levels: tuple[float, ...], spec: SymbolSpec) -> PartialCloseDecision:
        if not self.config.enabled:
            return PartialCloseDecision(False, None, 0, "PARTIAL_CLOSE_DISABLED")
        current_r = risk_multiple(position.side, position.current_price, position.entry_price, initial_stop)
        completed = set(completed_levels)
        level = next((item for item in self.config.levels if item.trigger_r <= current_r and item.trigger_r not in completed), None)
        if level is None:
            return PartialCloseDecision(False, None, 0, "NO_PARTIAL_LEVEL_DUE")
        requested = initial_volume * level.close_percent / 100
        close_volume = normalize_volume(requested, spec.volume_min, position.volume, spec.volume_step)
        if close_volume <= 0 or close_volume >= position.volume - 1e-12:
            return PartialCloseDecision(False, level.trigger_r, 0, "PARTIAL_VOLUME_INVALID")
        remaining = position.volume - close_volume
        if remaining < spec.volume_min - 1e-12:
            maximum_close = position.volume - spec.volume_min
            close_volume = normalize_volume(maximum_close, spec.volume_min, position.volume, spec.volume_step)
            remaining = position.volume - close_volume
        if close_volume <= 0 or remaining < spec.volume_min - 1e-12:
            return PartialCloseDecision(False, level.trigger_r, 0, "PARTIAL_REMAINDER_BELOW_MINIMUM")
        return PartialCloseDecision(True, level.trigger_r, close_volume, "PARTIAL_LEVEL_TRIGGERED")
