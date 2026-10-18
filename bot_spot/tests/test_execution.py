import asyncio
from unittest.mock import patch

from spot_ai_bot.config import Settings
from spot_ai_bot.execution import LiveExecution, PaperExecution
from spot_ai_bot.models import AdvisorOpinion, AssetGroup, TradeProposal


def proposal() -> TradeProposal:
    return TradeProposal(
        group=AssetGroup.crypto,
        symbol="BTCUSDT",
        action="BUY",
        amount_usd=9,
        price=100,
        strategy_reason="test",
        advisor=AdvisorOpinion(
            group=AssetGroup.crypto,
            symbol="BTCUSDT",
            opinion="bullish",
            confidence=0.8,
            suggested_action="consider_buy",
            reason="test",
        ),
    )


def test_paper_execution_sets_quantity():
    filled = asyncio.run(PaperExecution().execute(proposal()))

    assert filled.status == "paper_filled"
    assert filled.quantity == 0.09


def test_live_execution_requires_safety_phrase():
    settings = Settings(live_trading_enabled=True, okx_api_key="key", okx_secret="secret")

    result = asyncio.run(LiveExecution(settings).execute(proposal()))

    assert result.status == "blocked_live_guard"
    assert "LIVE_TRADING_CONFIRM" in result.execution_error


def test_live_execution_blocks_large_trade():
    settings = Settings(
        live_trading_enabled=True,
        live_trading_confirm="I_UNDERSTAND_LIVE_TRADING_RISK",
        max_live_trade_usd=5,
        okx_api_key="key",
        okx_secret="secret",
    )

    result = asyncio.run(LiveExecution(settings).execute(proposal()))

    assert result.status == "blocked_live_guard"
    assert "MAX_LIVE_TRADE_USD" in result.execution_error


def test_live_execution_does_not_use_unified_futures_balance_for_spot():
    settings = Settings(
        live_trading_enabled=True,
        live_trading_confirm="I_UNDERSTAND_LIVE_TRADING_RISK",
        max_live_trade_usd=25,
        okx_api_key="key",
        okx_secret="secret",
        okx_passphrase="pass",
        spot_only_trading=True,
    )

    with patch("spot_ai_bot.execution.okx_funding_available", return_value=0):
        result = asyncio.run(LiveExecution(settings).execute(proposal()))

    assert result.status == "blocked_live_guard"
    assert "will not use unified/futures account balance" in result.execution_error


def test_live_execution_transfers_funding_before_spot_order():
    settings = Settings(
        live_trading_enabled=True,
        live_trading_confirm="I_UNDERSTAND_LIVE_TRADING_RISK",
        max_live_trade_usd=25,
        okx_api_key="key",
        okx_secret="secret",
        okx_passphrase="pass",
        spot_only_trading=True,
    )

    async def fake_transfer(*args, **kwargs):
        return {"code": "0", "data": [{"transId": "test"}]}

    class FakeClient:
        def __init__(self, settings):
            pass

        async def market_buy(self, symbol, amount_usd, price):
            return {"id": "order-1", "amount": 0.00001}

        async def close(self):
            pass

    with patch("spot_ai_bot.execution.okx_funding_available", return_value=10), patch(
        "spot_ai_bot.execution.okx_transfer_funding_to_trading", side_effect=fake_transfer
    ) as transfer, patch(
        "spot_ai_bot.execution.okx_order_detail",
        return_value={"data": [{"avgPx": "101", "accFillSz": "0.089", "fillNotionalUsd": "9"}]},
    ), patch(
        "spot_ai_bot.execution.next_buy_sequence",
        return_value={"label": "#1", "main": 1, "sub": 0},
    ), patch("spot_ai_bot.execution.ExchangeClient", FakeClient):
        result = asyncio.run(LiveExecution(settings).execute(proposal()))

    assert result.status == "live_filled"
    assert result.exchange_order_id == "order-1"
    assert result.average_price == 101
    assert result.quantity == 0.089
    assert result.filled_notional_usd == 9
    assert result.buy_sequence == "#1"
    transfer.assert_called_once()
