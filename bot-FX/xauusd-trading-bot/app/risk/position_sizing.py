"""Position sizing from actual broker tick size/value and equity risk."""

from __future__ import annotations

from dataclasses import dataclass

from app.broker.mt5_client import SymbolSpec
from app.utils.calculations import normalize_volume
from app.utils.exceptions import OrderValidationError


@dataclass(frozen=True, slots=True)
class SizingResult:
    volume: float
    raw_volume: float
    risk_amount: float
    loss_per_lot: float
    ticks_to_stop: float


class PositionSizer:
    """Never clamps a too-small risk lot upward to the broker minimum."""

    @staticmethod
    def calculate(equity: float, risk_percent: float, entry: float, stop_loss: float, spec: SymbolSpec, max_lot: float | None) -> SizingResult:
        if equity <= 0 or risk_percent <= 0:
            raise OrderValidationError("Equity and risk percent must be positive")
        if spec.trade_tick_size <= 0 or spec.trade_tick_value <= 0:
            raise OrderValidationError("Broker tick size/value is invalid")
        price_distance = abs(entry - stop_loss)
        if price_distance <= 0:
            raise OrderValidationError("Entry and stop loss cannot be equal")
        ticks_to_stop = price_distance / spec.trade_tick_size
        loss_per_lot = ticks_to_stop * spec.trade_tick_value
        if loss_per_lot <= 0:
            raise OrderValidationError("Calculated loss per lot is invalid")
        risk_amount = equity * risk_percent / 100
        raw_volume = risk_amount / loss_per_lot
        volume_cap = spec.volume_max if max_lot is None else min(max_lot, spec.volume_max)
        volume = normalize_volume(min(raw_volume, volume_cap), spec.volume_min, spec.volume_max, spec.volume_step)
        if volume <= 0:
            raise OrderValidationError("Risk-based volume is below broker minimum")
        actual_risk = volume * loss_per_lot
        if actual_risk > risk_amount + max(0.01, risk_amount * 0.001):
            raise OrderValidationError("Normalized volume exceeds requested risk")
        return SizingResult(volume, raw_volume, risk_amount, loss_per_lot, ticks_to_stop)
