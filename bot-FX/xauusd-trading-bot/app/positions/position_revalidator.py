"""Re-checks open positions when market direction rotates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from app.broker.mt5_client import BrokerPosition
from app.config.settings import PositionRevalidationConfig, StrategyConfig
from app.strategy.signal_engine import SignalEvaluation
from app.strategy.trend_detector import TrendAssessment
from app.utils.enums import SignalSide, TrendDirection


@dataclass(frozen=True, slots=True)
class RevalidationDecision:
    should_close: bool
    keep_score: int
    reason: str
    details: dict


class PositionRevalidator:
    def __init__(self, config: PositionRevalidationConfig, strategy: StrategyConfig) -> None:
        self.config = config
        self.strategy = strategy

    @staticmethod
    def _side_direction(side: str) -> TrendDirection:
        return TrendDirection.BULLISH if side == SignalSide.BUY.value else TrendDirection.BEARISH

    @staticmethod
    def _opposite_side(side: str) -> SignalSide:
        return SignalSide.SELL if side == SignalSide.BUY.value else SignalSide.BUY

    def evaluate(
        self,
        position: BrokerPosition,
        trend: TrendAssessment,
        m15: pd.DataFrame,
        m5: pd.DataFrame,
        rotation: SignalEvaluation,
        *,
        opened_at: datetime | None = None,
        initial_risk_amount: float | None = None,
        max_favorable_profit: float | None = None,
    ) -> RevalidationDecision:
        if not self.config.enabled or not self.config.close_opposite_positions:
            return RevalidationDecision(False, 0, "REVALIDATION_DISABLED", {})
        if position.side not in (SignalSide.BUY.value, SignalSide.SELL.value):
            return RevalidationDecision(False, 0, "UNSUPPORTED_POSITION_SIDE", {"side": position.side})

        original_direction = self._side_direction(position.side)
        if trend.direction is original_direction:
            return RevalidationDecision(False, 11, "POSITION_STILL_ALIGNED_WITH_TREND", {"trend": trend.direction.value})
        keep_score, keep_rules = self._keep_score(position.side, trend, m15, m5)
        early_loss = self._early_loss_decision(position, opened_at, initial_risk_amount, max_favorable_profit, keep_score, keep_rules, trend)
        if early_loss is not None:
            return early_loss
        if trend.direction not in (TrendDirection.BULLISH, TrendDirection.BEARISH):
            return RevalidationDecision(False, 0, "NO_CLEAR_ROTATION_TREND", {"trend": trend.direction.value})

        expected_rotation_side = self._opposite_side(position.side)
        rotation_trade_ok = (
            rotation.side is expected_rotation_side
            and rotation.score >= self.config.minimum_rotation_score
            and (not self.config.require_rotation_trade_signal or rotation.decision == "TRADE")
        )
        if not rotation_trade_ok:
            return RevalidationDecision(False, 0, "ROTATION_SIGNAL_NOT_STRONG_ENOUGH", {
                "position_side": position.side,
                "rotation_side": rotation.side.value,
                "rotation_score": rotation.score,
                "minimum": self.config.minimum_rotation_score,
                "decision": rotation.decision,
            })

        should_close = keep_score < self.config.minimum_keep_score
        return RevalidationDecision(should_close, keep_score, "OPPOSITE_ROTATION_INVALIDATED_POSITION" if should_close else "POSITION_STILL_HAS_RECOVERY_EVIDENCE", {
            "position_side": position.side,
            "trend": trend.direction.value,
            "rotation_side": rotation.side.value,
            "rotation_score": rotation.score,
            "keep_score": keep_score,
            "minimum_keep_score": self.config.minimum_keep_score,
            "keep_rules": keep_rules,
        })

    def _early_loss_decision(
        self,
        position: BrokerPosition,
        opened_at: datetime | None,
        initial_risk_amount: float | None,
        max_favorable_profit: float | None,
        keep_score: int,
        keep_rules: dict[str, bool],
        trend: TrendAssessment,
    ) -> RevalidationDecision | None:
        if not self.config.early_loss_protection_enabled:
            return None
        if position.profit >= 0:
            return None
        if opened_at is not None:
            value = opened_at if opened_at.tzinfo else opened_at.replace(tzinfo=UTC)
            age_minutes = (datetime.now(UTC) - value.astimezone(UTC)).total_seconds() / 60
            if age_minutes < self.config.early_loss_min_age_minutes:
                return None
        else:
            age_minutes = None
        risk = float(initial_risk_amount or 0)
        if risk <= 0:
            return None
        adverse_r = abs(float(position.profit)) / risk
        runup_r = max(0.0, float(max_favorable_profit or 0)) / risk
        normal_cut = adverse_r >= self.config.early_loss_adverse_r
        runup_failed = runup_r >= self.config.early_loss_after_runup_r and adverse_r >= self.config.early_loss_after_runup_adverse_r
        unclear_trend = trend.direction not in (TrendDirection.BULLISH, TrendDirection.BEARISH)
        weak_keep = keep_score < self.config.early_loss_minimum_keep_score or (
            self.config.early_loss_close_on_unclear_trend and unclear_trend
        )
        if not weak_keep or not (normal_cut or runup_failed):
            return None
        return RevalidationDecision(True, keep_score, "EARLY_LOSS_PROTECTION", {
            "position_side": position.side,
            "trend": trend.direction.value,
            "profit": position.profit,
            "initial_risk_amount": risk,
            "adverse_r": adverse_r,
            "threshold_r": self.config.early_loss_adverse_r,
            "runup_r": runup_r,
            "runup_threshold_r": self.config.early_loss_after_runup_r,
            "age_minutes": age_minutes,
            "keep_score": keep_score,
            "minimum_keep_score": self.config.early_loss_minimum_keep_score,
            "keep_rules": keep_rules,
        })

    def _keep_score(self, side: str, trend: TrendAssessment, m15: pd.DataFrame, m5: pd.DataFrame) -> tuple[int, dict[str, bool]]:
        latest15 = m15.iloc[-1]
        latest5, previous5 = m5.iloc[-1], m5.iloc[-2]
        is_buy = side == SignalSide.BUY.value
        desired = TrendDirection.BULLISH if is_buy else TrendDirection.BEARISH

        h4_aligned = trend.h4.direction is desired
        h1_aligned = trend.h1.direction is desired
        ema_aligned = bool(latest15.ema20 >= latest15.ema50) if is_buy else bool(latest15.ema20 <= latest15.ema50)
        price_side_ok = bool(latest15.close >= latest15.ema50) if is_buy else bool(latest15.close <= latest15.ema50)
        rsi_ok = bool(float(latest15.rsi) >= self.strategy.rsi_buy_min) if is_buy else bool(float(latest15.rsi) <= self.strategy.rsi_sell_max)
        macd_ok = bool(latest5.macd_hist >= previous5.macd_hist) if is_buy else bool(latest5.macd_hist <= previous5.macd_hist)
        invalidation_ok = bool(latest15.close > latest15.last_swing_low) if is_buy else bool(latest15.close < latest15.last_swing_high)
        rules = {
            "h4_aligned": h4_aligned,
            "h1_aligned": h1_aligned,
            "ema_aligned": ema_aligned,
            "price_side_ok": price_side_ok,
            "rsi_ok": rsi_ok,
            "macd_ok": macd_ok,
            "invalidation_ok": invalidation_ok,
        }
        score = (
            (2 if h4_aligned else 0)
            + (2 if h1_aligned else 0)
            + (1 if ema_aligned else 0)
            + (2 if price_side_ok else 0)
            + (1 if rsi_ok else 0)
            + (1 if macd_ok else 0)
            + (2 if invalidation_ok else 0)
        )
        return score, rules
