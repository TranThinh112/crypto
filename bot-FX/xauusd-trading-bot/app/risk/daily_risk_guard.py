"""Daily entry lock logic (persistence orchestration is in services)."""

from dataclasses import dataclass

from app.config.settings import DailyRiskConfig
from app.strategy.trend_detector import RuleResult


@dataclass(frozen=True, slots=True)
class DailyRiskSnapshot:
    starting_equity: float
    realized_pnl: float
    floating_pnl: float
    consecutive_losses: int


class DailyRiskGuard:
    def __init__(self, config: DailyRiskConfig) -> None:
        self.config = config

    def loss_limit(self, starting_equity: float) -> float:
        percent_limit = starting_equity * self.config.max_daily_loss_percent / 100
        limits = [percent_limit]
        if self.config.max_daily_loss_usd is not None:
            limits.append(self.config.max_daily_loss_usd)
        return min(limits)

    def profit_target(self, starting_equity: float) -> float:
        percent_target = starting_equity * self.config.daily_profit_target_percent / 100
        targets = [percent_target]
        if self.config.daily_profit_target_usd is not None:
            targets.append(self.config.daily_profit_target_usd)
        return min(targets)

    def evaluate(self, snapshot: DailyRiskSnapshot) -> tuple[bool, tuple[RuleResult, ...]]:
        equity = snapshot.starting_equity
        total_pnl = snapshot.realized_pnl + snapshot.floating_pnl
        loss_limit = self.loss_limit(equity)
        profit_target = self.profit_target(equity)
        rules = (
            RuleResult(total_pnl > -loss_limit, "DAILY_LOSS_LIMIT", {"pnl": total_pnl, "limit": -loss_limit, "fixed_usd": self.config.max_daily_loss_usd}),
            RuleResult(total_pnl < profit_target, "DAILY_PROFIT_TARGET", {"pnl": total_pnl, "target": profit_target, "fixed_usd": self.config.daily_profit_target_usd}),
            RuleResult(snapshot.consecutive_losses < self.config.max_consecutive_losses, "CONSECUTIVE_LOSS_LIMIT", {"current": snapshot.consecutive_losses, "maximum": self.config.max_consecutive_losses}),
        )
        return all(rule.passed for rule in rules), rules
