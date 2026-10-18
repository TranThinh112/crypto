"""Candlestick pattern recognition used as entry confirmation.

The detector intentionally returns pattern names and direction only. It does
not decide trades by itself; the signal engine still requires trend, pullback,
momentum, spread and risk checks before any broker order is sent.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.utils.enums import SignalSide


@dataclass(frozen=True, slots=True)
class CandlePatternResult:
    supportive: tuple[str, ...]
    opposing: tuple[str, ...]
    neutral: tuple[str, ...]

    @property
    def confirmed(self) -> bool:
        return bool(self.supportive)


def _body(candle: pd.Series) -> float:
    return abs(float(candle.close) - float(candle.open))


def _range(candle: pd.Series) -> float:
    return max(float(candle.high) - float(candle.low), 1e-12)


def _upper_wick(candle: pd.Series) -> float:
    return float(candle.high) - max(float(candle.open), float(candle.close))


def _lower_wick(candle: pd.Series) -> float:
    return min(float(candle.open), float(candle.close)) - float(candle.low)


def _midpoint(candle: pd.Series) -> float:
    return (float(candle.open) + float(candle.close)) / 2


def _bullish(candle: pd.Series) -> bool:
    return float(candle.close) > float(candle.open)


def _bearish(candle: pd.Series) -> bool:
    return float(candle.close) < float(candle.open)


def _average_body(frame: pd.DataFrame) -> float:
    if "average_body" in frame.columns and pd.notna(frame.iloc[-1].average_body):
        return max(float(frame.iloc[-1].average_body), 1e-12)
    return max(float((frame["close"] - frame["open"]).abs().tail(20).mean()), 1e-12)


def _average_range(frame: pd.DataFrame) -> float:
    if "average_candle_range" in frame.columns and pd.notna(frame.iloc[-1].average_candle_range):
        return max(float(frame.iloc[-1].average_candle_range), 1e-12)
    return max(float((frame["high"] - frame["low"]).tail(20).mean()), 1e-12)


def _inside_body(inner: pd.Series, outer: pd.Series) -> bool:
    inner_low, inner_high = sorted((float(inner.open), float(inner.close)))
    outer_low, outer_high = sorted((float(outer.open), float(outer.close)))
    return inner_low >= outer_low and inner_high <= outer_high


def _near(first: float, second: float, tolerance: float) -> bool:
    return abs(first - second) <= tolerance


def detect_candlestick_patterns(frame: pd.DataFrame, side: SignalSide) -> CandlePatternResult:
    if len(frame) < 3 or side not in (SignalSide.BUY, SignalSide.SELL):
        return CandlePatternResult((), (), ())

    c1, prev, curr = frame.iloc[-3], frame.iloc[-2], frame.iloc[-1]
    avg_body = _average_body(frame)
    avg_range = _average_range(frame)
    body = _body(curr)
    candle_range = _range(curr)
    upper = _upper_wick(curr)
    lower = _lower_wick(curr)
    recent = frame.iloc[-11:-1] if len(frame) >= 11 else frame.iloc[:-1]
    tolerance = max(avg_range * 0.08, candle_range * 0.05)

    bullish: list[str] = []
    bearish: list[str] = []
    neutral: list[str] = []

    is_doji = body <= candle_range * 0.10
    is_spinning_top = body <= candle_range * 0.35 and upper >= body and lower >= body
    if is_doji:
        neutral.append("DOJI")
    elif is_spinning_top:
        neutral.append("SPINNING_TOP")

    if body >= candle_range * 0.75 and upper <= candle_range * 0.10 and lower <= candle_range * 0.10:
        (bullish if _bullish(curr) else bearish).append("MARUBOZU")

    if lower >= max(body * 2, candle_range * 0.45) and upper <= candle_range * 0.25 and body <= candle_range * 0.45:
        bullish.append("HAMMER")
    if upper >= max(body * 2, candle_range * 0.45) and lower <= candle_range * 0.25 and body <= candle_range * 0.45:
        bearish.append("SHOOTING_STAR")
        bullish.append("INVERTED_HAMMER")

    if _bullish(curr) and _bearish(prev) and float(curr.open) <= float(prev.close) and float(curr.close) >= float(prev.open):
        bullish.append("BULLISH_ENGULFING")
    if _bearish(curr) and _bullish(prev) and float(curr.open) >= float(prev.close) and float(curr.close) <= float(prev.open):
        bearish.append("BEARISH_ENGULFING")

    if _bearish(prev) and _bullish(curr) and _inside_body(curr, prev):
        bullish.append("BULLISH_HARAMI")
    if _bullish(prev) and _bearish(curr) and _inside_body(curr, prev):
        bearish.append("BEARISH_HARAMI")

    if _bearish(prev) and _bullish(curr) and float(curr.open) < float(prev.close) and float(curr.close) > _midpoint(prev) and float(curr.close) < float(prev.open):
        bullish.append("PIERCING_LINE")
    if _bullish(prev) and _bearish(curr) and float(curr.open) > float(prev.close) and float(curr.close) < _midpoint(prev) and float(curr.close) > float(prev.open):
        bearish.append("DARK_CLOUD_COVER")

    if _near(float(prev.low), float(curr.low), tolerance) and _bearish(prev) and _bullish(curr):
        bullish.append("TWEEZERS_BOTTOM")
    if _near(float(prev.high), float(curr.high), tolerance) and _bullish(prev) and _bearish(curr):
        bearish.append("TWEEZERS_TOP")

    c1_long = _body(c1) >= avg_body * 1.1
    curr_strong = body >= avg_body
    if _bearish(c1) and c1_long and _body(prev) <= avg_body * 0.7 and _bullish(curr) and curr_strong and float(curr.close) > _midpoint(c1):
        bullish.append("MORNING_STAR")
    if _bullish(c1) and c1_long and _body(prev) <= avg_body * 0.7 and _bearish(curr) and curr_strong and float(curr.close) < _midpoint(c1):
        bearish.append("EVENING_STAR")

    last_three = frame.iloc[-3:]
    if all(_bullish(row) for _, row in last_three.iterrows()) and float(last_three.close.iloc[-1]) > float(last_three.close.iloc[-2]) > float(last_three.close.iloc[-3]):
        bullish.append("THREE_WHITE_SOLDIERS")
    if all(_bearish(row) for _, row in last_three.iterrows()) and float(last_three.close.iloc[-1]) < float(last_three.close.iloc[-2]) < float(last_three.close.iloc[-3]):
        bearish.append("THREE_BLACK_CROWS")

    if not recent.empty:
        if float(curr.close) > float(recent.high.max()):
            bullish.append("BREAKOUT")
        if float(curr.close) < float(recent.low.min()):
            bearish.append("BREAKDOWN")

    if body > avg_body * 1.2:
        (bullish if _bullish(curr) else bearish).append("LARGE_BODY")

    bullish_tuple = tuple(dict.fromkeys(bullish))
    bearish_tuple = tuple(dict.fromkeys(bearish))
    neutral_tuple = tuple(dict.fromkeys(neutral))
    if side is SignalSide.BUY:
        return CandlePatternResult(bullish_tuple, bearish_tuple, neutral_tuple)
    return CandlePatternResult(bearish_tuple, bullish_tuple, neutral_tuple)
