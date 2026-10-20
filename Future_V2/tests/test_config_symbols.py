import pytest

from app.config import Settings


def test_symbol_allowlist():
    with pytest.raises(ValueError): Settings(allowed_symbols=("DOGE-USDT",))
    settings = Settings(allowed_symbols=("BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT"))
    assert set(settings.allowed_symbols) == {"BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT"}
