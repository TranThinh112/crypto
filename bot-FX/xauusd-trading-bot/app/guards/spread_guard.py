"""Absolute-point and ATR-relative spread guard."""

from app.broker.mt5_client import TickSnapshot
from app.config.settings import SpreadGuardConfig
from app.strategy.trend_detector import RuleResult


class SpreadGuard:
    def __init__(self, config: SpreadGuardConfig) -> None:
        self.config = config

    def evaluate(self, tick: TickSnapshot, point: float, atr: float) -> RuleResult:
        spread = tick.ask - tick.bid
        points = spread / point if point > 0 else float("inf")
        ratio = spread / atr if atr > 0 else float("inf")
        passed = not self.config.enabled or (points <= self.config.maximum_spread_points and ratio <= self.config.maximum_spread_atr_ratio)
        return RuleResult(passed, "SPREAD_GUARD", {"spread_points": points, "spread_atr_ratio": ratio, "maximum_points": self.config.maximum_spread_points, "maximum_atr_ratio": self.config.maximum_spread_atr_ratio})
