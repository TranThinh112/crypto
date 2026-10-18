"""Rule-based trend reversal exit signal."""

from app.strategy.trend_detector import RuleResult, TrendAssessment
from app.utils.enums import SignalSide, TrendDirection


class ExitSignalEngine:
    def trend_reversal(self, basket_side: str, trend: TrendAssessment) -> RuleResult:
        if basket_side not in (SignalSide.BUY.value, SignalSide.SELL.value):
            return RuleResult(False, "TREND_REVERSAL_EXIT", {"basket_side": basket_side, "trend": trend.direction.value})
        reversed_direction = TrendDirection.BEARISH if basket_side == SignalSide.BUY.value else TrendDirection.BULLISH
        passed = trend.direction is reversed_direction
        return RuleResult(passed, "TREND_REVERSAL_EXIT", {"basket_side": basket_side, "trend": trend.direction.value})
