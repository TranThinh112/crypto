from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from app.market_data.indicator_service import IndicatorService
from app.strategy.candlestick_patterns import detect_candlestick_patterns
from app.strategy.signal_engine import SignalEngine
from app.strategy.trend_detector import RuleResult, TimeframeTrend, TrendAssessment, TrendDetector
from app.utils.enums import SignalSide, TrendDirection


def candles(direction: float = 1.0, count: int = 260) -> pd.DataFrame:
    close = 1900 + direction * np.linspace(0, 150, count) + np.sin(np.arange(count) / 5)
    return pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=count, freq="h", tz="UTC"),
        "open": close - direction * 0.4, "high": close + 1, "low": close - 1,
        "close": close, "volume": 1000.0, "spread": 20,
    })


def test_indicators_and_bullish_bearish_trends(config):
    service = IndicatorService(config.strategy)
    up, down = service.calculate(candles(1)), service.calculate(candles(-1))
    required = ["ema20", "ema50", "ema200", "rsi", "atr", "adx", "macd_hist", "last_swing_high", "last_swing_low"]
    assert up[required].iloc[-1].notna().all()
    detector = TrendDetector(config.strategy)
    assert detector.detect(up, up).direction is TrendDirection.BULLISH
    assert detector.detect(down, down).direction is TrendDirection.BEARISH
    assert detector.detect(up, down).direction is TrendDirection.UNCERTAIN


def test_indicator_prefix_does_not_change_past_values(config):
    service = IndicatorService(config.strategy)
    raw = candles(1, 280)
    prefix = service.calculate(raw.iloc[:260])
    full = service.calculate(raw)
    columns = ["ema20", "ema50", "ema200", "rsi", "atr", "adx", "macd_hist", "last_swing_high", "last_swing_low"]
    np.testing.assert_allclose(prefix[columns].iloc[-1], full[columns].iloc[259], equal_nan=True)


def test_signal_scoring_is_explainable_and_reaches_100(config):
    tf = TimeframeTrend("H4", TrendDirection.BULLISH, 6, 1, (RuleResult(True, "H4_HIGHER_HIGH_HIGHER_LOW", {}),))
    trend = TrendAssessment(TrendDirection.BULLISH, tf, TimeframeTrend("H1", TrendDirection.BULLISH, 6, 1, (RuleResult(True, "H1_HIGHER_HIGH_HIGHER_LOW", {}),)))
    times = pd.date_range("2026-07-01", periods=12, freq="5min", tz="UTC")
    m5 = pd.DataFrame({
        "time": times, "open": [99.0] * 10 + [100.0, 98.5], "high": [99.5] * 10 + [100.2, 101.5],
        "low": [98.5] * 10 + [98.8, 98.0], "close": [99.1] * 10 + [99.0, 101.0],
        "average_body": [0.5] * 12, "macd_hist": [0.0] * 10 + [1.0, 2.0],
    })
    m15 = pd.DataFrame([{
        "time": times[-1], "close": 100.0, "ema20": 100.1, "ema50": 99.9,
        "atr": 2.0, "last_swing_low": 95.0, "last_swing_high": 105.0,
        "rsi": 55.0, "adx": 25.0,
    }])
    result = SignalEngine(config.strategy, config.signal_scoring, config.take_profit).evaluate(trend, m15, m5, 2.0)
    assert result.side is SignalSide.BUY
    assert result.score == 100
    assert all(set(rule.as_dict()) == {"passed", "reason_code", "details", "points"} for rule in result.rules)


def test_conflicting_timeframes_return_no_trade(config):
    bull = TimeframeTrend("H4", TrendDirection.BULLISH, 6, 0, ())
    bear = TimeframeTrend("H1", TrendDirection.BEARISH, 0, 6, ())
    frame = pd.DataFrame([{"time": datetime.now(UTC), "open": 1, "high": 2, "low": 0, "close": 1, "average_body": 1, "macd_hist": 0, "ema20": 1, "ema50": 1, "atr": 1, "last_swing_low": 0, "last_swing_high": 2, "rsi": 50, "adx": 10}] * 12)
    result = SignalEngine(config.strategy, config.signal_scoring, config.take_profit).evaluate(TrendAssessment(TrendDirection.UNCERTAIN, bull, bear), frame, frame, 2)
    assert result.side is SignalSide.NO_TRADE
    assert result.rejection_reason == "TIMEFRAME_TREND_CONFLICT"


def test_candlestick_detector_reports_supportive_and_opposing_patterns():
    frame = pd.DataFrame({
        "time": pd.date_range("2026-07-01", periods=12, freq="5min", tz="UTC"),
        "open": [100.0] * 9 + [102.0, 101.0, 98.5],
        "high": [101.0] * 9 + [103.0, 101.5, 103.2],
        "low": [99.0] * 9 + [100.0, 97.8, 98.0],
        "close": [100.2] * 9 + [100.5, 99.0, 102.6],
        "average_body": [1.0] * 12,
        "average_candle_range": [3.0] * 12,
    })
    buy = detect_candlestick_patterns(frame, SignalSide.BUY)
    sell = detect_candlestick_patterns(frame, SignalSide.SELL)
    assert "BULLISH_ENGULFING" in buy.supportive
    assert "LARGE_BODY" in buy.supportive
    assert "BULLISH_ENGULFING" in sell.opposing
    assert buy.confirmed


def test_relaxed_profile_can_follow_h1_when_h4_is_sideways(config, monkeypatch):
    detector = TrendDetector(config.strategy)
    trends = iter((
        TimeframeTrend("H4", TrendDirection.SIDEWAYS, 3, 2, ()),
        TimeframeTrend("H1", TrendDirection.BEARISH, 1, 5, ()),
    ))
    monkeypatch.setattr(detector, "timeframe", lambda *_: next(trends))
    assessment = detector.detect(pd.DataFrame(), pd.DataFrame())
    assert not config.strategy.require_h4_h1_alignment
    assert assessment.h1.direction is TrendDirection.BEARISH
    assert assessment.direction is TrendDirection.BEARISH


def test_relaxed_profile_can_follow_h4_when_h1_is_sideways(config, monkeypatch):
    detector = TrendDetector(config.strategy)
    trends = iter((
        TimeframeTrend("H4", TrendDirection.BULLISH, 5, 1, ()),
        TimeframeTrend("H1", TrendDirection.SIDEWAYS, 3, 2, ()),
    ))
    monkeypatch.setattr(detector, "timeframe", lambda *_: next(trends))
    assessment = detector.detect(pd.DataFrame(), pd.DataFrame())
    assert not config.strategy.require_h4_h1_alignment
    assert assessment.h4.direction is TrendDirection.BULLISH
    assert assessment.direction is TrendDirection.BULLISH
