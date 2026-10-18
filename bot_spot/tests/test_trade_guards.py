from datetime import datetime, timedelta, timezone

from spot_ai_bot.config import Settings
from spot_ai_bot.main import _market_regime, _risk_based_amount, _watchlist_readiness
from spot_ai_bot.models import AdvisorOpinion, AllocationPlan, AssetGroup, MarketCandidate
from spot_ai_bot.risk import RiskEngine
from spot_ai_bot.strategy import RuleStrategy
from spot_ai_bot.trade_thesis import build_trade_thesis


def _allocation() -> AllocationPlan:
    return AllocationPlan(
        total_budget_usd=100,
        allocation={
            AssetGroup.crypto: 60,
            AssetGroup.stocks: 20,
            AssetGroup.commodities: 10,
            AssetGroup.cash: 10,
        },
        reason="test",
    )


def _opinion(symbol: str = "BTCUSDT") -> AdvisorOpinion:
    return AdvisorOpinion(
        group=AssetGroup.crypto,
        symbol=symbol,
        opinion="bullish",
        confidence=0.8,
        suggested_action="consider_buy",
        reason="test",
    )


def test_watchlist_readiness_requires_confirmation_or_age():
    settings = Settings(shortlist_min_observations_for_trade=2, shortlist_min_age_minutes_for_trade=30)
    now = datetime(2026, 7, 29, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    fresh = {"created_at": now - timedelta(minutes=10), "observation_count": 1}
    confirmed = {"created_at": now - timedelta(minutes=10), "observation_count": 2}
    aged = {"created_at": now - timedelta(minutes=31), "observation_count": 1}

    assert _watchlist_readiness(settings, fresh, now)["trade_ready"] is False
    assert _watchlist_readiness(settings, confirmed, now)["trade_ready"] is True
    assert _watchlist_readiness(settings, aged, now)["trade_ready"] is True


def test_market_regime_blocks_when_btc_and_eth_are_weak():
    settings = Settings(market_regime_min_trend=0.45, market_regime_min_liquidity=0.65)
    candidates = [
        MarketCandidate(group=AssetGroup.crypto, symbol="BTCUSDT", price=100, trend_score=0.2, liquidity_score=0.9, volatility_score=0.2),
        MarketCandidate(group=AssetGroup.crypto, symbol="ETHUSDT", price=100, trend_score=0.3, liquidity_score=0.5, volatility_score=0.2),
    ]

    regime = _market_regime(settings, candidates)

    assert regime["ok"] is False
    assert regime["reason"] == "all_regime_symbols_weak"


def test_strategy_blocks_pump_chase_and_records_entry_plan():
    candidate = MarketCandidate(
        group=AssetGroup.crypto,
        symbol="PUMPUSDT",
        price=10,
        trend_score=0.9,
        liquidity_score=0.9,
        volatility_score=0.3,
        metadata={
            "change_pct": 8.5,
            "support_usdt": 9,
            "resistance_usdt": 10.2,
            "drawdown_from_resistance_pct": -0.5,
            "anti_pump_max_24h_change_pct": 6,
            "anti_pump_near_resistance_pct": -1.5,
        },
    )

    proposal = RuleStrategy(RiskEngine()).build_proposal(
        candidate,
        _allocation(),
        _opinion("PUMPUSDT"),
        market_regime={"ok": True, "reason": "test"},
    )

    assert proposal is not None
    assert proposal.status == "rejected_by_risk"
    assert any("Anti-pump guard" in note for note in proposal.risk_notes)
    assert proposal.entry_plan["invalidation_price_usdt"] == 9


def test_strategy_blocks_new_buy_when_market_regime_is_bad():
    candidate = MarketCandidate(
        group=AssetGroup.crypto,
        symbol="BTCUSDT",
        price=100,
        trend_score=0.9,
        liquidity_score=0.9,
        volatility_score=0.3,
        metadata={"change_pct": 1},
    )

    proposal = RuleStrategy(RiskEngine()).build_proposal(
        candidate,
        _allocation(),
        _opinion(),
        market_regime={"ok": False, "reason": "all_regime_symbols_weak"},
    )

    assert proposal is not None
    assert proposal.status == "rejected_by_risk"
    assert any("Market regime guard" in note for note in proposal.risk_notes)


def test_trade_thesis_marks_buy_zone_near_support():
    settings = Settings(buy_zone_support_buffer_pct=3)
    candidate = MarketCandidate(
        group=AssetGroup.crypto,
        symbol="BTCUSDT",
        price=102,
        trend_score=0.8,
        liquidity_score=0.9,
        volatility_score=0.25,
        metadata={"support_usdt": 100, "resistance_usdt": 120, "change_pct": 1},
    )

    thesis = build_trade_thesis(settings, candidate, {"observation_count": 2})

    assert thesis["status"] == "buy_zone"
    assert thesis["buy_zone"]["reason"] == "near_support_pullback"
    assert thesis["invalidation_price_usdt"] == 100


def test_trade_thesis_invalidates_below_support():
    settings = Settings()
    candidate = MarketCandidate(
        group=AssetGroup.crypto,
        symbol="BTCUSDT",
        price=98,
        trend_score=0.8,
        liquidity_score=0.9,
        volatility_score=0.25,
        metadata={"support_usdt": 100, "resistance_usdt": 120, "change_pct": -2},
    )

    thesis = build_trade_thesis(settings, candidate, {"observation_count": 2})

    assert thesis["status"] == "invalidated"


def test_risk_based_amount_caps_notional_by_invalidation_distance():
    settings = Settings(user_total_budget_usd=100, risk_per_trade_pct_of_budget=1, max_live_trade_usd=25)
    candidate = MarketCandidate(
        group=AssetGroup.crypto,
        symbol="BTCUSDT",
        price=100,
        trend_score=0.8,
        liquidity_score=0.9,
        volatility_score=0.25,
    )

    amount = _risk_based_amount(
        settings,
        candidate,
        _allocation(),
        {"invalidation_price_usdt": 90},
        default_amount=50,
    )

    assert amount == 10
