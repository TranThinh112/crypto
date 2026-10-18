"""Explainable 0-100 rule-scoring engine for trend-following pullbacks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.config.settings import SignalScoringConfig, StrategyConfig, TakeProfitConfig
from app.strategy.candlestick_patterns import detect_candlestick_patterns
from app.strategy.trend_detector import RuleResult, TrendAssessment
from app.utils.enums import SignalSide, TrendDirection


@dataclass(frozen=True, slots=True)
class SignalEvaluation:
    side: SignalSide
    score: int
    decision: str
    rejection_reason: str | None
    rules: tuple[RuleResult, ...]
    signal_hash: str
    details: dict[str, Any]


class SignalEngine:
    """Scores static rules; weights and thresholds are configuration only."""

    def __init__(self, strategy: StrategyConfig, weights: SignalScoringConfig, take_profit: TakeProfitConfig) -> None:
        self.strategy = strategy
        self.weights = weights
        self.take_profit = take_profit

    @staticmethod
    def _confirmation(frame: pd.DataFrame, side: SignalSide) -> tuple[bool, list[str]]:
        patterns = detect_candlestick_patterns(frame, side)
        names = list(patterns.supportive)
        return patterns.confirmed, names

    def evaluate(self, trend: TrendAssessment, m15: pd.DataFrame, m5: pd.DataFrame, risk_reward: float) -> SignalEvaluation:
        side = SignalSide.BUY if trend.direction is TrendDirection.BULLISH else SignalSide.SELL if trend.direction is TrendDirection.BEARISH else SignalSide.NO_TRADE
        latest15, latest5 = m15.iloc[-1], m5.iloc[-1]
        if side is SignalSide.NO_TRADE:
            rules = (
                RuleResult(False, "H4_H1_NOT_ALIGNED", {"h4": trend.h4.direction.value, "h1": trend.h1.direction.value}, 0),
            )
            return self._finish(side, rules, {"trend": trend.direction.value}, "TIMEFRAME_TREND_CONFLICT")

        is_buy = side is SignalSide.BUY
        direction = TrendDirection.BULLISH if is_buy else TrendDirection.BEARISH
        atr = float(latest15.atr)
        distance = min(abs(float(latest15.close - latest15.ema20)), abs(float(latest15.close - latest15.ema50)))
        pullback = distance <= atr * self.strategy.pullback_tolerance_atr
        invalidation = float(latest15.last_swing_low if is_buy else latest15.last_swing_high)
        invalidation_ok = bool(latest15.close > invalidation) if is_buy else bool(latest15.close < invalidation)
        candle_patterns = detect_candlestick_patterns(m5, side)
        confirmation, patterns = candle_patterns.confirmed, list(candle_patterns.supportive)
        macd_ok = bool(latest5.macd_hist > m5.iloc[-2].macd_hist) if is_buy else bool(latest5.macd_hist < m5.iloc[-2].macd_hist)
        rsi_min = self.strategy.rsi_buy_min if is_buy else self.strategy.rsi_sell_min
        rsi_max = self.strategy.rsi_buy_max if is_buy else self.strategy.rsi_sell_max
        rsi_ok = rsi_min <= float(latest15.rsi) <= rsi_max
        ema_ok = bool(latest15.ema20 > latest15.ema50) if is_buy else bool(latest15.ema20 < latest15.ema50)
        structure_token = "HIGHER_HIGH_HIGHER_LOW" if is_buy else "LOWER_HIGH_LOWER_LOW"
        structure_ok = all(
            any(rule.passed and structure_token in rule.reason_code for rule in timeframe.rules)
            for timeframe in (trend.h4, trend.h1)
        )
        rules = (
            RuleResult(trend.h4.direction is direction, "H4_TREND_ALIGNMENT", {"actual": trend.h4.direction.value}, self.weights.h4_trend_alignment),
            RuleResult(trend.h1.direction is direction, "H1_TREND_ALIGNMENT", {"actual": trend.h1.direction.value}, self.weights.h1_trend_alignment),
            RuleResult(ema_ok, "M15_EMA_ALIGNMENT", {"ema20": float(latest15.ema20), "ema50": float(latest15.ema50)}, self.weights.ema_alignment),
            RuleResult(structure_ok, "MARKET_STRUCTURE", {"direction": direction.value}, self.weights.market_structure),
            RuleResult(pullback and invalidation_ok, "M15_PULLBACK_QUALITY", {"distance": distance, "atr": atr, "invalidation": invalidation, "invalidation_ok": invalidation_ok}, self.weights.pullback_quality),
            RuleResult(
                confirmation,
                "M5_CANDLE_CONFIRMATION",
                {
                    "patterns": patterns,
                    "supportive": list(candle_patterns.supportive),
                    "opposing": list(candle_patterns.opposing),
                    "neutral": list(candle_patterns.neutral),
                },
                self.weights.candle_confirmation,
            ),
            RuleResult(macd_ok, "M5_MACD_CONFIRMATION", {"current": float(latest5.macd_hist), "previous": float(m5.iloc[-2].macd_hist)}, self.weights.macd_confirmation),
            RuleResult(rsi_ok, "M15_RSI_CONFIRMATION", {"rsi": float(latest15.rsi), "range": [rsi_min, rsi_max]}, self.weights.rsi_confirmation),
            RuleResult(float(latest15.adx) >= self.strategy.minimum_adx, "M15_ADX_STRENGTH", {"adx": float(latest15.adx), "minimum": self.strategy.minimum_adx}, self.weights.adx_strength),
            RuleResult(risk_reward >= self.take_profit.minimum_risk_reward, "RISK_REWARD_QUALITY", {"risk_reward": risk_reward, "minimum": self.take_profit.minimum_risk_reward}, self.weights.risk_reward_quality),
        )
        return self._finish(side, rules, {"atr": atr, "rsi": float(latest15.rsi), "adx": float(latest15.adx), "candle_time": str(latest5.time)}, None)

    def _finish(self, side: SignalSide, rules: tuple[RuleResult, ...], details: dict[str, Any], forced_reason: str | None) -> SignalEvaluation:
        score = sum(rule.points for rule in rules if rule.passed)
        mandatory = {"M15_PULLBACK_QUALITY"}
        if self.strategy.require_h4_h1_alignment:
            mandatory.update(("H4_TREND_ALIGNMENT", "H1_TREND_ALIGNMENT"))
        failed_mandatory = [rule.reason_code for rule in rules if rule.reason_code in mandatory and not rule.passed]
        accepted = side is not SignalSide.NO_TRADE and score >= self.strategy.minimum_signal_score and not failed_mandatory
        reason = forced_reason or (None if accepted else (f"MANDATORY_RULE_FAILED:{','.join(failed_mandatory)}" if failed_mandatory else f"SCORE_BELOW_MINIMUM:{score}"))
        payload = {"side": side.value, "score": score, "rules": [rule.as_dict() for rule in rules], "details": details}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()[:24]
        return SignalEvaluation(side if accepted else SignalSide.NO_TRADE, score, "TRADE" if accepted else "NO_TRADE", reason, rules, digest, details)
