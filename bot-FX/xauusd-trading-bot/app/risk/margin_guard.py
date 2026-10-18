"""Pre-trade margin validation."""

from dataclasses import dataclass

from app.broker.mt5_client import AccountSnapshot, BrokerClient
from app.config.settings import RiskConfig
from app.strategy.trend_detector import RuleResult


@dataclass(frozen=True, slots=True)
class MarginValidation:
    passed: bool
    required_margin: float | None
    projected_free_margin_percent: float
    rule: RuleResult


class MarginGuard:
    def __init__(self, client: BrokerClient, config: RiskConfig) -> None:
        self.client = client
        self.config = config

    def validate(self, side: str, symbol: str, volume: float, price: float, account: AccountSnapshot) -> MarginValidation:
        required = self.client.calculate_margin(side, symbol, volume, price)
        projected_free = account.margin_free - (required or 0)
        percent = projected_free / account.equity * 100 if account.equity > 0 else 0
        passed = required is not None and required >= 0 and required <= account.margin_free and percent >= self.config.minimum_free_margin_percent
        rule = RuleResult(passed, "MARGIN_AVAILABLE", {"required": required, "free_before": account.margin_free, "free_percent_after": percent, "minimum_percent": self.config.minimum_free_margin_percent})
        return MarginValidation(passed, required, percent, rule)
