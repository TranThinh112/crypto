"""Deterministic technical indicators calculated only from broker OHLCV data."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.config.settings import StrategyConfig
from app.utils.exceptions import MarketDataError


class IndicatorService:
    """Adds indicators without external signals, prediction or future data."""

    REQUIRED_COLUMNS = {"time", "open", "high", "low", "close", "volume"}

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    def calculate(self, candles: pd.DataFrame) -> pd.DataFrame:
        missing = self.REQUIRED_COLUMNS.difference(candles.columns)
        if missing:
            raise MarketDataError(f"Missing candle columns: {sorted(missing)}")
        if len(candles) < self.config.ema_slow + 10:
            raise MarketDataError(f"At least {self.config.ema_slow + 10} closed candles are required")

        frame = candles.copy().sort_values("time").reset_index(drop=True)
        close, high, low = frame["close"].astype(float), frame["high"].astype(float), frame["low"].astype(float)
        frame["ema20"] = close.ewm(span=self.config.ema_fast, adjust=False).mean()
        frame["ema50"] = close.ewm(span=self.config.ema_mid, adjust=False).mean()
        frame["ema200"] = close.ewm(span=self.config.ema_slow, adjust=False).mean()
        frame["ema50_slope"] = frame["ema50"].diff(5) / 5
        frame["rsi"] = self._rsi(close, self.config.rsi_period)
        frame["atr"] = self._atr(high, low, close, self.config.atr_period)
        frame["adx"] = self._adx(high, low, close, self.config.adx_period)

        macd = close.ewm(span=self.config.macd_fast, adjust=False).mean() - close.ewm(span=self.config.macd_slow, adjust=False).mean()
        frame["macd"] = macd
        frame["macd_signal"] = macd.ewm(span=self.config.macd_signal, adjust=False).mean()
        frame["macd_hist"] = frame["macd"] - frame["macd_signal"]
        window = self.config.swing_window
        frame["highest_high"] = high.rolling(window * 2 + 1, min_periods=window).max()
        frame["lowest_low"] = low.rolling(window * 2 + 1, min_periods=window).min()
        # A pivot is published `window` bars after it happened, once both sides are closed.
        # This placement avoids leaking future pivot knowledge into backtests.
        rolling_high = high.rolling(window * 2 + 1).max()
        rolling_low = low.rolling(window * 2 + 1).min()
        candidate_high = high.shift(window)
        candidate_low = low.shift(window)
        frame["swing_high"] = np.where(candidate_high.eq(rolling_high), candidate_high, np.nan)
        frame["swing_low"] = np.where(candidate_low.eq(rolling_low), candidate_low, np.nan)
        # Strong monotonic trends may have no confirmed pivot. A trailing, past-only
        # range is the deterministic fallback so risk planning never consumes NaN.
        fallback_high = high.rolling(window * 2 + 1, min_periods=window).max()
        fallback_low = low.rolling(window * 2 + 1, min_periods=window).min()
        frame["last_swing_high"] = frame["swing_high"].ffill().fillna(fallback_high)
        frame["last_swing_low"] = frame["swing_low"].ffill().fillna(fallback_low)
        frame["candle_range"] = high - low
        frame["average_candle_range"] = frame["candle_range"].rolling(20, min_periods=5).mean()
        frame["average_body"] = (close - frame["open"]).abs().rolling(20, min_periods=5).mean()
        frame["average_volume"] = frame["volume"].rolling(20, min_periods=5).mean()
        return frame

    @staticmethod
    def _rsi(close: pd.Series, period: int) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        relative_strength = gain / loss.replace(0, np.nan)
        result = 100 - (100 / (1 + relative_strength))
        result = result.where(loss.ne(0), 100).where(gain.ne(0), 0)
        return result.where(~(gain.eq(0) & loss.eq(0)), 50)

    @staticmethod
    def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
        return pd.concat(((high - low), (high - close.shift()).abs(), (low - close.shift()).abs()), axis=1).max(axis=1)

    @classmethod
    def _atr(cls, high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
        return cls._true_range(high, low, close).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    @classmethod
    def _adx(cls, high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index)
        minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index)
        atr = cls._atr(high, low, close, period).replace(0, np.nan)
        plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr
        minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        return dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
