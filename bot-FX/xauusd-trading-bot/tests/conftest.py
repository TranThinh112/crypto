from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from app.broker.mt5_client import AccountSnapshot, BrokerDeal, BrokerPosition, SymbolSpec, TickSnapshot
from app.config.settings import TradingConfig, load_trading_config
from app.database import Database


@pytest.fixture
def config() -> TradingConfig:
    return load_trading_config(Path("app/config/trading_config.yaml"))


@pytest.fixture
def spec() -> SymbolSpec:
    return SymbolSpec("XAUUSD", 2, 0.01, 0.01, 1.0, 100.0, 0.01, 100.0, 0.01, 20, 10, 4, 0, True)


@pytest.fixture
def database(tmp_path: Path) -> Database:
    value = Database(f"sqlite:///{tmp_path / 'test.db'}")
    value.create_schema()
    return value


class FakeMarket:
    def __init__(self, spec: SymbolSpec, bid: float = 2000.0, ask: float = 2000.2) -> None:
        self.specification = spec
        self.bid = bid
        self.ask = ask
        self.connected = True
        self.margin = 100.0

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    def symbols(self) -> list[str]:
        return [self.specification.name]

    def select_symbol(self, symbol: str) -> bool:
        return symbol == self.specification.name

    def symbol_spec(self, symbol: str) -> SymbolSpec:
        return self.specification

    def tick(self, symbol: str) -> TickSnapshot:
        return TickSnapshot(symbol, self.bid, self.ask, (self.bid + self.ask) / 2, datetime.now(UTC))

    def candles(self, symbol: str, timeframe: str, count: int, start_pos: int = 1) -> pd.DataFrame:
        return pd.DataFrame()

    def account(self) -> AccountSnapshot:
        return AccountSnapshot(10_000, 10_000, 0, 10_000, 0, "USD")

    def positions(self, symbol: str, magic: int) -> list[BrokerPosition]:
        return []

    def deals(self, start: datetime, end: datetime, symbol: str, magic: int) -> list[BrokerDeal]:
        return []

    def calculate_margin(self, side: str, symbol: str, volume: float, price: float) -> float | None:
        return self.margin
