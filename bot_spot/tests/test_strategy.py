from spot_ai_bot.models import AdvisorOpinion, AllocationPlan, AssetGroup, MarketCandidate
from spot_ai_bot.risk import RiskEngine
from spot_ai_bot.strategy import RuleStrategy


def test_group_ai_opinion_does_not_execute_trade():
    allocation = AllocationPlan(
        total_budget_usd=100,
        allocation={
            AssetGroup.crypto: 45,
            AssetGroup.stocks: 30,
            AssetGroup.commodities: 15,
            AssetGroup.cash: 10,
        },
        reason="test",
    )
    candidate = MarketCandidate(
        group=AssetGroup.crypto,
        symbol="BTCUSDT",
        price=118000,
        trend_score=0.72,
        liquidity_score=0.96,
        volatility_score=0.42,
    )
    opinion = AdvisorOpinion(
        group=AssetGroup.crypto,
        symbol="BTCUSDT",
        opinion="bullish",
        confidence=0.72,
        suggested_action="consider_buy",
        reason="test advisor only",
    )

    proposal = RuleStrategy(RiskEngine()).build_proposal(candidate, allocation, opinion)

    assert proposal is not None
    assert proposal.status == "pending"
    assert proposal.advisor == opinion
    assert proposal.price == candidate.price
    assert proposal.strategy_reason.startswith("RuleStrategy")
