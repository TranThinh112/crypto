from spot_ai_bot.config import Settings
from spot_ai_bot.market_data import _scan_okx_market
from spot_ai_bot.okx_market import _classify_crypto_sector, _should_shortlist


def test_market_scan_expand_universe_defaults_on():
    settings = Settings()
    assert settings.market_scan_expand_universe_enabled is True
    assert settings.market_scan_universe_max_symbols == 200
    assert settings.market_scan_shortlist_ttl_hours == 12


def test_shortlist_helper_accepts_noteworthy_coins():
    shortlisted, score, reason = _should_shortlist(0.72, 0.81, 0.22, 6.0)
    assert shortlisted is True
    assert score > 0
    assert reason in {"mat_tinh_hinh_thi_truong_dang_chu_y", "bien_dong_manh_can_theo_doi"}


def test_crypto_sector_classifier_handles_common_groups():
    assert _classify_crypto_sector("ETH-USDT") == "layer1"
    assert _classify_crypto_sector("ARB-USDT") == "layer2"
    assert _classify_crypto_sector("WLD-USDT") == "ai"
