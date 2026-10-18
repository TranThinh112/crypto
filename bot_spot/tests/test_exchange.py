from spot_ai_bot.config import Settings
from spot_ai_bot.exchange import ExchangeClient


def test_okx_spot_only_orders_use_cash_trade_mode():
    settings = Settings(exchange_name="okx", spot_only_trading=True)
    client = ExchangeClient(settings)
    try:
        assert client.order_params() == {"tdMode": "cash"}
    finally:
        # No network session is opened until an async request is made.
        pass


def test_order_params_empty_when_spot_only_disabled():
    settings = Settings(exchange_name="okx", spot_only_trading=False)
    client = ExchangeClient(settings)
    try:
        assert client.order_params() == {}
    finally:
        pass
