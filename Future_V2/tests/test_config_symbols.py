import pytest

from app.config import Settings


def test_symbol_allowlist():
    with pytest.raises(ValueError): Settings(allowed_symbols=("SHIB-USDT",))
    all_syms = ("BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT", "DOGE-USDT", "ADA-USDT", "TRX-USDT", "AVAX-USDT", "LINK-USDT", "XAU-USDT")
    settings = Settings(allowed_symbols=all_syms)
    assert set(settings.allowed_symbols) == set(all_syms)
