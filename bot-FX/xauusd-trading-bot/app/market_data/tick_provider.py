"""Current tick access with age and spread calculations."""

from __future__ import annotations

from datetime import UTC, datetime

from app.broker.mt5_client import BrokerClient, TickSnapshot


class TickProvider:
    def __init__(self, client: BrokerClient) -> None:
        self.client = client

    def current(self, symbol: str) -> TickSnapshot:
        return self.client.tick(symbol)

    def age_seconds(self, symbol: str) -> float:
        return max(0.0, (datetime.now(UTC) - self.current(symbol).time).total_seconds())

    def spread_points(self, symbol: str, point: float) -> float:
        if point <= 0:
            raise ValueError("point must be positive")
        return self.current(symbol).spread_price / point
