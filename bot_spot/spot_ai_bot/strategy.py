from spot_ai_bot.models import AdvisorOpinion, AllocationPlan, MarketCandidate, TradeProposal
from spot_ai_bot.risk import RiskEngine


class RuleStrategy:
    def __init__(self, risk: RiskEngine):
        self.risk = risk

    def build_proposal(
        self,
        candidate: MarketCandidate,
        allocation: AllocationPlan,
        advisor: AdvisorOpinion,
        market_regime: dict | None = None,
    ) -> TradeProposal | None:
        if candidate.trend_score < 0.65 or candidate.liquidity_score < 0.70:
            return None

        group_budget = float(allocation.allocation.get(candidate.group, 0))
        amount_usd = round(group_budget * 0.20, 2)
        risk_notes = self.risk.check(candidate, allocation, amount_usd)
        risk_notes.extend(_market_regime_notes(market_regime))
        risk_notes.extend(_anti_pump_notes(candidate))
        proposal = TradeProposal(
            group=candidate.group,
            symbol=candidate.symbol,
            action="BUY",
            amount_usd=amount_usd,
            price=candidate.price,
            strategy_reason=(
                "RuleStrategy: trade-ready watchlist, trend_score >= 0.65, "
                "liquidity_score >= 0.70, market regime ok, anti-pump guard ok."
            ),
            advisor=advisor,
            risk_notes=risk_notes,
            entry_plan=_entry_plan(candidate),
        )
        return self.risk.approve_or_reject(proposal)

def _market_regime_notes(market_regime: dict | None) -> list[str]:
    if not market_regime or market_regime.get("ok", True):
        return []
    detail = market_regime.get("reason") or "Market regime is not supportive."
    return [f"Market regime guard blocked new buy: {detail}"]

def _anti_pump_notes(candidate: MarketCandidate) -> list[str]:
    metadata = candidate.metadata or {}
    change_pct = _to_float(metadata.get("change_pct"))
    drawdown = metadata.get("drawdown_from_resistance_pct")
    drawdown_pct = _to_float(drawdown) if drawdown is not None else None
    max_change_pct = _to_float(metadata.get("anti_pump_max_24h_change_pct"), 6.0)
    near_resistance_pct = _to_float(metadata.get("anti_pump_near_resistance_pct"), -1.5)
    if change_pct >= max_change_pct:
        return [f"Anti-pump guard blocked chase: 24h change {change_pct:.2f}% >= {max_change_pct:.2f}%."]
    if drawdown_pct is not None and drawdown_pct >= near_resistance_pct and change_pct > 0:
        return [
            "Anti-pump guard blocked buy near resistance: "
            f"drawdown {drawdown_pct:.2f}% >= {near_resistance_pct:.2f}%."
        ]
    return []

def _entry_plan(candidate: MarketCandidate) -> dict:
    metadata = candidate.metadata or {}
    price = candidate.price
    support = metadata.get("support_usdt")
    resistance = metadata.get("resistance_usdt")
    invalidation = support if support else round(price * 0.94, 8)
    first_take_profit = resistance if resistance and resistance > price else round(price * 1.08, 8)
    second_take_profit = round(price * 1.16, 8)
    return {
        "entry_price_usdt": price,
        "support_usdt": support,
        "resistance_usdt": resistance,
        "invalidation_price_usdt": invalidation,
        "take_profit_zones_usdt": [first_take_profit, second_take_profit],
        "position_rule": "No automatic sell; requires position management proposal and approval.",
        "thesis": (
            f"Trend {candidate.trend_score:.2f}, liquidity {candidate.liquidity_score:.2f}, "
            f"volatility {candidate.volatility_score:.2f}."
        ),
    }

def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
