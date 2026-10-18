from spot_ai_bot.portfolio import MIN_DISPLAY_VALUE_USDT, PORTFOLIO_CACHE_SECONDS


def test_portfolio_display_threshold_is_half_cent():
    assert MIN_DISPLAY_VALUE_USDT == 0.005


def test_portfolio_cache_ttl_is_short():
    assert PORTFOLIO_CACHE_SECONDS == 15
