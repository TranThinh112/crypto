"""Multi-timeframe trend detection with explainable rule results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.config.settings import StrategyConfig
from app.utils.enums import TrendDirection


@dataclass(frozen=True, slots=True)
class RuleResult:
    passed: bool
    reason_code: str
    details: dict[str, Any]
    points: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "reason_code": self.reason_code, "details": self.details, "points": self.points}


@dataclass(frozen=True, slots=True)
class TimeframeTrend:
    timeframe: str
    direction: TrendDirection
    bullish_conditions: int
    bearish_conditions: int
    rules: tuple[RuleResult, ...]


@dataclass(frozen=True, slots=True)
class TrendAssessment:
    direction: TrendDirection
    h4: TimeframeTrend
    h1: TimeframeTrend


class TrendDetector:
    """Classifies H4/H1 trends, with an optional H1-led relaxed Demo profile."""

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    @staticmethod
    def _structure(frame: pd.DataFrame) -> tuple[bool, bool, dict[str, float]]:
        lookback = min(40, len(frame))
        segment = frame.iloc[-lookback:]
        split = max(5, len(segment) // 2)
        older, recent = segment.iloc[:split], segment.iloc[split:]
        old_high, new_high = float(older["high"].max()), float(recent["high"].max())
        old_low, new_low = float(older["low"].min()), float(recent["low"].min())
        return (
            new_high > old_high and new_low > old_low,
            new_high < old_high and new_low < old_low,
            {"old_high": old_high, "new_high": new_high, "old_low": old_low, "new_low": new_low},
        )

    def timeframe(self, timeframe: str, frame: pd.DataFrame) -> TimeframeTrend:
        latest = frame.iloc[-1]
        bull_structure, bear_structure, structure_details = self._structure(frame)
        bullish = [
            (latest.ema20 > latest.ema50, "EMA20_ABOVE_EMA50"),
            (latest.ema50 > latest.ema200, "EMA50_ABOVE_EMA200"),
            (latest.close > latest.ema50, "CLOSE_ABOVE_EMA50"),
            (latest.ema50_slope > 0, "EMA50_SLOPE_UP"),
            (bull_structure, "HIGHER_HIGH_HIGHER_LOW"),
            (latest.adx >= self.config.minimum_adx, "ADX_STRONG"),
        ]
        bearish = [
            (latest.ema20 < latest.ema50, "EMA20_BELOW_EMA50"),
            (latest.ema50 < latest.ema200, "EMA50_BELOW_EMA200"),
            (latest.close < latest.ema50, "CLOSE_BELOW_EMA50"),
            (latest.ema50_slope < 0, "EMA50_SLOPE_DOWN"),
            (bear_structure, "LOWER_HIGH_LOWER_LOW"),
            (latest.adx >= self.config.minimum_adx, "ADX_STRONG"),
        ]
        bull_count, bear_count = sum(bool(value) for value, _ in bullish), sum(bool(value) for value, _ in bearish)
        adx_ok = bool(latest.adx >= self.config.minimum_adx)
        if bull_count >= 4 and adx_ok and bull_count > bear_count:
            direction = TrendDirection.BULLISH
            selected = bullish
        elif bear_count >= 4 and adx_ok and bear_count > bull_count:
            direction = TrendDirection.BEARISH
            selected = bearish
        elif not adx_ok:
            direction = TrendDirection.SIDEWAYS
            selected = bullish if bull_count >= bear_count else bearish
        else:
            direction = TrendDirection.UNCERTAIN
            selected = bullish if bull_count >= bear_count else bearish
        rules = tuple(
            RuleResult(bool(value), f"{timeframe}_{code}", {"timeframe": timeframe, "adx": float(latest.adx), **(structure_details if "HIGHER" in code or "LOWER" in code else {})})
            for value, code in selected
        )
        return TimeframeTrend(timeframe, direction, bull_count, bear_count, rules)

    def detect(self, h4: pd.DataFrame, h1: pd.DataFrame) -> TrendAssessment:
        h4_result = self.timeframe("H4", h4)
        h1_result = self.timeframe("H1", h1)
        if h4_result.direction == h1_result.direction and h4_result.direction in (TrendDirection.BULLISH, TrendDirection.BEARISH):
            direction = h4_result.direction
        elif (
            not self.config.require_h4_h1_alignment
            and h1_result.direction in (TrendDirection.BULLISH, TrendDirection.BEARISH)
            and h4_result.direction in (TrendDirection.SIDEWAYS, TrendDirection.UNCERTAIN)
        ):
            direction = h1_result.direction
        elif (
            not self.config.require_h4_h1_alignment
            and h4_result.direction in (TrendDirection.BULLISH, TrendDirection.BEARISH)
            and h1_result.direction in (TrendDirection.SIDEWAYS, TrendDirection.UNCERTAIN)
        ):
            direction = h4_result.direction
        elif TrendDirection.SIDEWAYS in (h4_result.direction, h1_result.direction):
            direction = TrendDirection.SIDEWAYS
        else:
            direction = TrendDirection.UNCERTAIN
        return TrendAssessment(direction, h4_result, h1_result)
