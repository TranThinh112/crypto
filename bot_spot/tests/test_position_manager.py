from spot_ai_bot.config import Settings
from spot_ai_bot.models import MarketCandidate, AssetGroup, PositionOpinion
from spot_ai_bot.position_manager import _final_gate, _rule_evaluate_position
from spot_ai_bot.telegram import format_position_management_item, _looks_corrupted


def test_holder_first_rule_prefers_watch_over_cut_loss_for_moderate_loss():
    settings = Settings()
    asset = {
        "asset": "BTC",
        "quantity": 0.01,
        "price_usdt": 60000,
        "value_usdt": 600,
        "pnl_usdt": -50,
        "pnl_pct": -10,
    }
    candidate = MarketCandidate(
        group=AssetGroup.crypto,
        symbol="BTCUSDT",
        price=60000,
        trend_score=0.4,
        liquidity_score=1,
        volatility_score=0.2,
    )

    proposal = _rule_evaluate_position(settings, asset, candidate)

    assert proposal.final_action == "HOLD"


def test_final_gate_blocks_add_when_market_scores_are_weak():
    settings = Settings()
    proposal = _rule_evaluate_position(
        settings,
        {
            "asset": "BTC",
            "quantity": 0.01,
            "price_usdt": 60000,
            "value_usdt": 600,
            "pnl_usdt": 10,
            "pnl_pct": 2,
        },
        MarketCandidate(
            group=AssetGroup.crypto,
            symbol="BTCUSDT",
            price=60000,
            trend_score=0.4,
            liquidity_score=0.5,
            volatility_score=0.2,
        ),
    )
    proposal.ai_opinion = PositionOpinion(
        symbol="BTCUSDT",
        opinion="buy_more",
        confidence=0.9,
        suggested_action="CONSIDER_ADD",
        reason="test",
    )

    result = _final_gate(settings, proposal)

    assert result.final_action == "HOLD"
    assert result.final_gate_passed is False


def test_rule_does_not_consider_add_without_spot_capital():
    settings = Settings(min_new_trade_capital_usdt=10)
    proposal = _rule_evaluate_position(
        settings,
        {
            "asset": "BTC",
            "quantity": 0.01,
            "price_usdt": 60000,
            "value_usdt": 600,
            "pnl_usdt": 20,
            "pnl_pct": 3,
        },
        MarketCandidate(
            group=AssetGroup.crypto,
            symbol="BTCUSDT",
            price=60000,
            trend_score=0.8,
            liquidity_score=1,
            volatility_score=0.2,
        ),
        spot_capital_usdt=1,
    )

    assert proposal.final_action == "HOLD"


def test_position_management_telegram_format_is_vietnamese_safe():
    settings = Settings()
    proposal = _rule_evaluate_position(
        settings,
        {
            "asset": "BTC",
            "quantity": 0.01,
            "price_usdt": 60000,
            "value_usdt": 600,
            "pnl_usdt": 12.345678,
            "pnl_pct": 8.765432,
        },
        MarketCandidate(
            group=AssetGroup.crypto,
            symbol="BTCUSDT",
            price=60000,
            trend_score=0.5,
            liquidity_score=1,
            volatility_score=0.2,
        ),
    )

    message = format_position_management_item(proposal)

    assert "Hành động cuối" in message
    assert "PnL: +12.34568 USDT (+8.76543%)" in message
    assert not _looks_corrupted(message)
