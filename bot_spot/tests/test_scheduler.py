import asyncio
from unittest.mock import patch

from spot_ai_bot.config import Settings
from spot_ai_bot.scheduler import run_scheduled_scan


def test_scheduled_scan_skips_new_market_scan_when_spot_capital_is_low():
    settings = Settings(min_new_trade_capital_usdt=1)

    with patch(
        "spot_ai_bot.scheduler.spot_portfolio",
        return_value={"spot_capital_usdt": 0.5, "assets": []},
    ), patch("spot_ai_bot.scheduler.scan_market") as scan_market, patch(
        "spot_ai_bot.scheduler.insert_doc"
    ):
        result = asyncio.run(run_scheduled_scan(settings))

    assert result["data_source"] == "skipped"
    assert result["fallback_reason"] == "insufficient_spot_capital_for_new_trade"
    scan_market.assert_not_called()
