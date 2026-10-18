"""Stop-loss, take-profit and risk/reward planning."""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.broker.mt5_client import SymbolSpec
from app.config.settings import StopLossConfig, TakeProfitConfig
from app.utils.calculations import normalize_price
from app.utils.enums import SignalSide
from app.utils.exceptions import OrderValidationError


@dataclass(frozen=True, slots=True)
class PricePlan:
    side: SignalSide
    entry: float
    stop_loss: float
    take_profit: float
    stop_distance: float
    stop_atr_multiple: float
    risk_reward: float


class RiskManager:
    def __init__(self, stop: StopLossConfig, take_profit: TakeProfitConfig) -> None:
        self.stop = stop
        self.take_profit = take_profit

    def plan(
        self,
        side: SignalSide,
        entry: float,
        atr: float,
        swing_low: float,
        swing_high: float,
        spec: SymbolSpec,
        maximum_atr_multiplier: float | None = None,
    ) -> PricePlan:
        if side not in (SignalSide.BUY, SignalSide.SELL):
            raise OrderValidationError("A price plan requires BUY or SELL")
        if atr <= 0 or not all(math.isfinite(value) for value in (entry, atr, swing_low, swing_high)):
            raise OrderValidationError("ATR, entry and swing values must be finite and positive")
        is_buy = side is SignalSide.BUY
        raw_stop = swing_low - atr * self.stop.atr_buffer_multiplier if is_buy else swing_high + atr * self.stop.atr_buffer_multiplier
        raw_distance = entry - raw_stop if is_buy else raw_stop - entry
        minimum = atr * self.stop.minimum_atr_multiplier
        if raw_distance < minimum:
            raw_stop = entry - minimum if is_buy else entry + minimum
            raw_distance = minimum
        maximum = atr * (maximum_atr_multiplier or self.stop.maximum_atr_multiplier)
        if raw_distance > maximum:
            raise OrderValidationError("Stop loss exceeds configured maximum ATR distance")
        broker_minimum = spec.trade_stops_level * spec.point
        if raw_distance + 1e-12 < broker_minimum:
            raise OrderValidationError("Stop loss violates broker stop level")
        stop_loss = normalize_price(raw_stop, spec.digits)
        distance = abs(entry - stop_loss)
        if distance <= 0:
            raise OrderValidationError("Normalized stop distance is zero")
        rr = self.take_profit.default_risk_reward
        take_profit = normalize_price(entry + distance * rr if is_buy else entry - distance * rr, spec.digits)
        actual_rr = abs(take_profit - entry) / distance
        if actual_rr + 1e-9 < self.take_profit.minimum_risk_reward:
            raise OrderValidationError("Risk/reward is below configured minimum")
        return PricePlan(side, normalize_price(entry, spec.digits), stop_loss, take_profit, distance, distance / atr, actual_rr)
