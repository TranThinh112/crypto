from spot_ai_bot.candles import detect_patterns


def test_detects_bullish_engulfing():
    candles = [
        {"open": 10, "high": 10.2, "low": 9.4, "close": 9.5},
        {"open": 9.45, "high": 10.4, "low": 9.4, "close": 10.25},
    ]
    patterns = detect_patterns(candles)
    assert patterns
    assert patterns[0]["pattern"] in {"BULLISH_ENGULFING", "LARGE_BODY"}


def test_detects_doji():
    candles = [
        {"open": 10, "high": 10.8, "low": 9.2, "close": 10.02},
    ]
    patterns = detect_patterns(candles)
    assert patterns
    assert patterns[0]["pattern"] in {"DOJI", "SPINNING_TOP"}
