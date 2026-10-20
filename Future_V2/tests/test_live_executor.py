from types import SimpleNamespace
import asyncio
import pytest

from app.config import TradingMode
from app.execution.live import CONFIRMATION, LiveFuturesExecutor


def settings(**overrides):
    values = {
        "trading_mode": TradingMode.live,
        "enable_live_trading": True,
        "live_execution_enabled": True,
        "live_execution_confirmation": CONFIRMATION,
        "live_dry_run": True,
        "live_margin_mode": "isolated",
        "live_max_leverage": 20,
        "target_margin_usdt": 5.0,
        "target_leverage": 20,
        "okx_read_only": False,
        "okx_demo_trading": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def proposal(action="buy"):
    return {
        "symbol": "BTC-USDT",
        "entry_price": 84000.0,
        "stop_loss": 83496.0 if action == "buy" else 84504.0,
        "take_profit_ladder": {"tp1": 84336.0},
    }


def test_live_executor_returns_dry_run_plan_without_order_submission():
    executor = LiveFuturesExecutor(object(), settings())
    result = asyncio.run(executor.submit(proposal(), {"approved": True, "action": "buy"}))
    assert result["status"] == "dry_run"
    assert result["plan"]["instId"] == "BTC-USDT-SWAP"
    assert result["plan"]["target_notional_usdt"] == 100.0
    assert result["plan"]["posSide"] == "long"


def test_live_executor_fails_closed_without_confirmation():
    executor = LiveFuturesExecutor(object(), settings(live_execution_confirmation=""))
    with pytest.raises(PermissionError, match="live_confirmation_missing"):
        executor.plan(proposal(), {"approved": True, "action": "buy"})


def test_live_executor_rejects_unapproved_or_unsafe_orders():
    executor = LiveFuturesExecutor(object(), settings())
    with pytest.raises(ValueError, match="consensus_not_approved"):
        executor.plan(proposal(), {"approved": False, "action": "buy"})
    with pytest.raises(ValueError, match="invalid_protective_stop"):
        executor.plan({**proposal(), "stop_loss": 85000.0}, {"approved": True, "action": "buy"})


def test_live_executor_submits_swap_order_when_not_dry_run():
    class MockOKXClient:
        def __init__(self):
            self.leverage_set = None
            self.order_created = None
        async def set_swap_leverage(self, symbol, leverage, margin_mode):
            self.leverage_set = (symbol, leverage, margin_mode)
        async def create_swap_order(self, body):
            self.order_created = body
            return {"code": "0", "data": [{"ordId": "12345"}]}

    client = MockOKXClient()
    executor = LiveFuturesExecutor(client, settings(live_dry_run=False))
    result = asyncio.run(executor.submit(proposal(), {"approved": True, "action": "buy"}))
    assert result["status"] == "submitted"
    assert client.leverage_set == ("BTC-USDT-SWAP", 20, "isolated")
    assert client.order_created["instId"] == "BTC-USDT-SWAP"
    assert client.order_created["clOrdId"].startswith("bot")


def test_live_executor_contract_sizes_and_decimals():
    class MockOKXClient:
        def __init__(self):
            self.orders = []
        async def set_swap_leverage(self, symbol, leverage, margin_mode, pos_side=None):
            pass
        async def create_swap_order(self, body):
            self.orders.append(body)
            return {"code": "0", "data": [{"ordId": "123", "sCode": "0"}]}

    client = MockOKXClient()
    executor = LiveFuturesExecutor(client, settings(live_dry_run=False, target_margin_usdt=3.5, target_leverage=20))

    # SOL: entry $180, ctVal 1.0, notional $70 -> 70 / 180 = 0.3888 -> 0.39 contracts, decimals = 2
    asyncio.run(executor.submit({"symbol": "SOL-USDT", "entry_price": 180.0, "stop_loss": 178.2, "take_profit": 183.6}, {"approved": True, "action": "buy"}))
    assert client.orders[-1]["instId"] == "SOL-USDT-SWAP"
    assert client.orders[-1]["sz"] == "0.39"
    assert client.orders[-1]["attachAlgoOrds"][0]["slTriggerPx"] == "178.2"

    # BNB: entry $600, ctVal 0.01, notional $70 -> notional_per_ct = 6 -> 70 / 6 = 11.66 -> round to 12 integer contracts, decimals = 1
    asyncio.run(executor.submit({"symbol": "BNB-USDT", "entry_price": 600.0, "stop_loss": 594.0, "take_profit": 612.0}, {"approved": True, "action": "buy"}))
    assert client.orders[-1]["instId"] == "BNB-USDT-SWAP"
    assert client.orders[-1]["sz"] == "12"
    assert client.orders[-1]["attachAlgoOrds"][0]["slTriggerPx"] == "594.0"

    # XRP: entry $0.60, ctVal 100, notional $70 -> notional_per_ct = 60 -> 70 / 60 = 1.166 -> 1.17 contracts, decimals = 4
    asyncio.run(executor.submit({"symbol": "XRP-USDT", "entry_price": 0.60, "stop_loss": 0.5940, "take_profit": 0.6120}, {"approved": True, "action": "buy"}))
    assert client.orders[-1]["instId"] == "XRP-USDT-SWAP"
    assert client.orders[-1]["sz"] == "1.17"
    assert client.orders[-1]["attachAlgoOrds"][0]["slTriggerPx"] == "0.594"
