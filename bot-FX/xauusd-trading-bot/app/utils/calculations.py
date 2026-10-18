"""Pure price and volume calculations."""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP


def normalize_price(price: float, digits: int) -> float:
    quantum = Decimal(1).scaleb(-digits)
    return float(Decimal(str(price)).quantize(quantum, rounding=ROUND_HALF_UP))


def normalize_volume(volume: float, volume_min: float, volume_max: float, volume_step: float) -> float:
    if volume_step <= 0 or volume_min <= 0 or volume_max < volume_min:
        raise ValueError("invalid broker volume constraints")
    if volume < volume_min:
        return 0.0
    steps = (Decimal(str(min(volume, volume_max))) / Decimal(str(volume_step))).to_integral_value(rounding=ROUND_DOWN)
    normalized = steps * Decimal(str(volume_step))
    if normalized < Decimal(str(volume_min)):
        return 0.0
    return float(normalized)


def weighted_average_price(entries: list[tuple[float, float]]) -> float:
    total_volume = sum(volume for _, volume in entries)
    if total_volume <= 0:
        return 0.0
    return sum(price * volume for price, volume in entries) / total_volume


def risk_multiple(side: str, current: float, entry: float, initial_stop: float) -> float:
    risk = abs(entry - initial_stop)
    if risk <= 0:
        return 0.0
    reward = current - entry if side == "BUY" else entry - current
    return reward / risk
