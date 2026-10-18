from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Candle:
    open: float
    high: float
    low: float
    close: float

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return max(self.high - self.low, 0.0)

    @property
    def upper_wick(self) -> float:
        return max(self.high - max(self.open, self.close), 0.0)

    @property
    def lower_wick(self) -> float:
        return max(min(self.open, self.close) - self.low, 0.0)

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open


PATTERN_ORDER = [
    "BREAKOUT",
    "BREAKDOWN",
    "MORNING_STAR",
    "EVENING_STAR",
    "THREE_WHITE_SOLDIERS",
    "THREE_BLACK_CROWS",
    "BULLISH_ENGULFING",
    "BEARISH_ENGULFING",
    "BULLISH_HARAMI",
    "BEARISH_HARAMI",
    "PIERCING_LINE",
    "DARK_CLOUD_COVER",
    "TWEEZERS_BOTTOM",
    "TWEEZERS_TOP",
    "HAMMER",
    "SHOOTING_STAR",
    "INVERTED_HAMMER",
    "MARUBOZU",
    "DOJI",
    "SPINNING_TOP",
    "LARGE_BODY",
]


def detect_patterns(candles: Iterable[dict | Candle], support: float | None = None, resistance: float | None = None) -> list[dict]:
    seq = [_normalize_candle(candle) for candle in candles]
    if len(seq) < 1:
        return []

    last = seq[-1]
    prev = seq[-2] if len(seq) >= 2 else None
    prev2 = seq[-3] if len(seq) >= 3 else None
    prior_trend = _trend(seq[:-1])
    body_ratio = _body_ratio(last)
    signal: list[dict] = []

    if _is_doji(last):
        signal.append(_emit("DOJI", "neutral", 0.65))
    if _is_spinning_top(last):
        signal.append(_emit("SPINNING_TOP", "neutral", 0.60))
    if _is_marubozu(last):
        signal.append(_emit("MARUBOZU", "bullish" if last.is_bullish else "bearish", 0.80))
    if _is_hammer(last):
        signal.append(_emit("HAMMER", "bullish", 0.82))
    if _is_shooting_star(last):
        signal.append(_emit("SHOOTING_STAR", "bearish", 0.82))
    if _is_inverted_hammer(last):
        signal.append(_emit("INVERTED_HAMMER", "bullish", 0.80))
    if prev and _bullish_engulfing(prev, last):
        signal.append(_emit("BULLISH_ENGULFING", "bullish", 0.88))
    if prev and _bearish_engulfing(prev, last):
        signal.append(_emit("BEARISH_ENGULFING", "bearish", 0.88))
    if prev and _bullish_harami(prev, last):
        signal.append(_emit("BULLISH_HARAMI", "bullish", 0.76))
    if prev and _bearish_harami(prev, last):
        signal.append(_emit("BEARISH_HARAMI", "bearish", 0.76))
    if prev and _piercing_line(prev, last):
        signal.append(_emit("PIERCING_LINE", "bullish", 0.78))
    if prev and _dark_cloud_cover(prev, last):
        signal.append(_emit("DARK_CLOUD_COVER", "bearish", 0.78))
    if prev and _tweezers_bottom(prev, last):
        signal.append(_emit("TWEEZERS_BOTTOM", "bullish", 0.74))
    if prev and _tweezers_top(prev, last):
        signal.append(_emit("TWEEZERS_TOP", "bearish", 0.74))
    if len(seq) >= 3 and _morning_star(seq[-3], seq[-2], seq[-1]):
        signal.append(_emit("MORNING_STAR", "bullish", 0.86))
    if len(seq) >= 3 and _evening_star(seq[-3], seq[-2], seq[-1]):
        signal.append(_emit("EVENING_STAR", "bearish", 0.86))
    if len(seq) >= 3 and _three_white_soldiers(seq[-3], seq[-2], seq[-1]):
        signal.append(_emit("THREE_WHITE_SOLDIERS", "bullish", 0.90))
    if len(seq) >= 3 and _three_black_crows(seq[-3], seq[-2], seq[-1]):
        signal.append(_emit("THREE_BLACK_CROWS", "bearish", 0.90))

    if resistance is not None and last.close > resistance * 1.003 and prior_trend in {"up", "flat"}:
        signal.append(_emit("BREAKOUT", "bullish", 0.92))
    if support is not None and last.close < support * 0.997 and prior_trend in {"down", "flat"}:
        signal.append(_emit("BREAKDOWN", "bearish", 0.92))
    if body_ratio >= 0.70:
        signal.append(_emit("LARGE_BODY", "bullish" if last.is_bullish else "bearish", 0.70))

    signal.sort(key=lambda item: (item["confidence"], -PATTERN_ORDER.index(item["pattern"])), reverse=True)
    return signal


def primary_pattern(candles: Iterable[dict | Candle], support: float | None = None, resistance: float | None = None) -> dict | None:
    patterns = detect_patterns(candles, support=support, resistance=resistance)
    return patterns[0] if patterns else None


def _normalize_candle(candle: dict | Candle) -> Candle:
    if isinstance(candle, Candle):
        return candle
    return Candle(
        open=_to_float(candle[1] if isinstance(candle, (list, tuple)) and len(candle) > 1 else candle.get("open")),
        high=_to_float(candle[2] if isinstance(candle, (list, tuple)) and len(candle) > 2 else candle.get("high")),
        low=_to_float(candle[3] if isinstance(candle, (list, tuple)) and len(candle) > 3 else candle.get("low")),
        close=_to_float(candle[4] if isinstance(candle, (list, tuple)) and len(candle) > 4 else candle.get("close")),
    )


def _trend(candles: list[Candle]) -> str:
    if len(candles) < 3:
        return "flat"
    closes = [c.close for c in candles[-6:] if c.close > 0]
    if len(closes) < 3:
        return "flat"
    first = closes[0]
    last = closes[-1]
    change = (last - first) / first if first else 0
    if change > 0.015:
        return "up"
    if change < -0.015:
        return "down"
    return "flat"


def _body_ratio(candle: Candle) -> float:
    return (candle.body / candle.range) if candle.range else 0.0


def _is_doji(candle: Candle) -> bool:
    return candle.range > 0 and candle.body / candle.range <= 0.12


def _is_spinning_top(candle: Candle) -> bool:
    return candle.range > 0 and 0.12 < candle.body / candle.range <= 0.35 and candle.upper_wick > candle.body * 0.8 and candle.lower_wick > candle.body * 0.8


def _is_marubozu(candle: Candle) -> bool:
    return candle.range > 0 and candle.body / candle.range >= 0.85 and candle.upper_wick <= candle.body * 0.10 and candle.lower_wick <= candle.body * 0.10


def _is_hammer(candle: Candle) -> bool:
    return candle.range > 0 and candle.lower_wick >= candle.body * 2 and candle.upper_wick <= candle.body * 0.6 and candle.body / candle.range <= 0.4


def _is_shooting_star(candle: Candle) -> bool:
    return candle.range > 0 and candle.upper_wick >= candle.body * 2 and candle.lower_wick <= candle.body * 0.6 and candle.body / candle.range <= 0.4


def _is_inverted_hammer(candle: Candle) -> bool:
    return _is_shooting_star(candle) and candle.is_bullish


def _bullish_engulfing(prev: Candle, last: Candle) -> bool:
    return prev.is_bearish and last.is_bullish and last.open <= prev.close and last.close >= prev.open


def _bearish_engulfing(prev: Candle, last: Candle) -> bool:
    return prev.is_bullish and last.is_bearish and last.open >= prev.close and last.close <= prev.open


def _bullish_harami(prev: Candle, last: Candle) -> bool:
    return prev.is_bearish and last.is_bullish and last.open > prev.close and last.close < prev.open and last.body < prev.body * 0.6


def _bearish_harami(prev: Candle, last: Candle) -> bool:
    return prev.is_bullish and last.is_bearish and last.open < prev.close and last.close > prev.open and last.body < prev.body * 0.6


def _piercing_line(prev: Candle, last: Candle) -> bool:
    midpoint = (prev.open + prev.close) / 2
    return prev.is_bearish and last.is_bullish and last.open < prev.low * 1.01 and last.close > midpoint and last.close < prev.open


def _dark_cloud_cover(prev: Candle, last: Candle) -> bool:
    midpoint = (prev.open + prev.close) / 2
    return prev.is_bullish and last.is_bearish and last.open > prev.high * 0.99 and last.close < midpoint and last.close > prev.close


def _tweezers_bottom(prev: Candle, last: Candle) -> bool:
    return prev.is_bearish and last.is_bullish and abs(prev.low - last.low) / max(prev.low, last.low, 1e-9) <= 0.003


def _tweezers_top(prev: Candle, last: Candle) -> bool:
    return prev.is_bullish and last.is_bearish and abs(prev.high - last.high) / max(prev.high, last.high, 1e-9) <= 0.003


def _morning_star(c1: Candle, c2: Candle, c3: Candle) -> bool:
    return (
        c1.is_bearish
        and _body_ratio(c1) >= 0.5
        and _body_ratio(c2) <= 0.35
        and c3.is_bullish
        and c3.close > (c1.open + c1.close) / 2
    )


def _evening_star(c1: Candle, c2: Candle, c3: Candle) -> bool:
    return (
        c1.is_bullish
        and _body_ratio(c1) >= 0.5
        and _body_ratio(c2) <= 0.35
        and c3.is_bearish
        and c3.close < (c1.open + c1.close) / 2
    )


def _three_white_soldiers(c1: Candle, c2: Candle, c3: Candle) -> bool:
    return (
        c1.is_bullish
        and c2.is_bullish
        and c3.is_bullish
        and c2.close > c1.close
        and c3.close > c2.close
        and _body_ratio(c1) >= 0.45
        and _body_ratio(c2) >= 0.45
        and _body_ratio(c3) >= 0.45
    )


def _three_black_crows(c1: Candle, c2: Candle, c3: Candle) -> bool:
    return (
        c1.is_bearish
        and c2.is_bearish
        and c3.is_bearish
        and c2.close < c1.close
        and c3.close < c2.close
        and _body_ratio(c1) >= 0.45
        and _body_ratio(c2) >= 0.45
        and _body_ratio(c3) >= 0.45
    )


def _emit(pattern: str, bias: str, confidence: float) -> dict:
    return {"pattern": pattern, "bias": bias, "confidence": round(confidence, 4)}


def _to_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
