from spot_ai_bot.models import AllocationPlan, MarketCandidate, TradeProposal


class RiskEngine:
    def __init__(self, max_trade_pct_of_group: float = 0.35):
        self.max_trade_pct_of_group = max_trade_pct_of_group

    def check(self, candidate: MarketCandidate, allocation: AllocationPlan, amount_usd: float) -> list[str]:
        notes: list[str] = []
        group_budget = float(allocation.allocation.get(candidate.group, 0))
        if group_budget <= 0:
            notes.append("Group has no allocated budget.")
        if amount_usd > group_budget * self.max_trade_pct_of_group:
            notes.append("Trade amount exceeds max trade percentage of group allocation.")
        if candidate.liquidity_score < 0.60:
            notes.append("Liquidity score is too low.")
        if candidate.volatility_score > 0.80:
            notes.append("Volatility score is too high.")
        return notes

    def approve_or_reject(self, proposal: TradeProposal) -> TradeProposal:
        if proposal.risk_notes:
            proposal.status = "rejected_by_risk"
        return proposal

