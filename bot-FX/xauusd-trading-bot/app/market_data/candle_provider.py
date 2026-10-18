"""Closed-candle-only market data provider."""

from __future__ import annotations

import pandas as pd

from app.broker.mt5_client import BrokerClient


class CandleProvider:
    def __init__(self, client: BrokerClient) -> None:
        self.client = client

    def closed_candles(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        # MT5 position zero is the running candle; start at one to prevent look-ahead.
        return self.client.candles(symbol, timeframe, count, start_pos=1).copy()

    def latest_closed_time(self, symbol: str, timeframe: str) -> pd.Timestamp:
        return self.closed_candles(symbol, timeframe, 1).iloc[-1]["time"]
