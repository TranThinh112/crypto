"""Paper execution adapter using live MT5 prices without sending broker orders."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from threading import RLock

import pandas as pd

from app.broker.mt5_client import (
    AccountSnapshot,
    BrokerClient,
    BrokerDeal,
    BrokerOrderRequest,
    BrokerPosition,
    BrokerResult,
    SymbolSpec,
    TickSnapshot,
)


class PaperBrokerClient:
    """Simulates fills/positions while delegating all market data to MT5."""

    PAPER_RETCODE_DONE = 10009

    def __init__(self, market_client: BrokerClient, initial_balance: float = 10_000) -> None:
        self.market = market_client
        self._balance = initial_balance
        self._positions: dict[int, BrokerPosition] = {}
        self._next_ticket = 9_000_000
        self._deals: list[BrokerDeal] = []
        self._lock = RLock()

    def connect(self) -> None:
        self.market.connect()

    def disconnect(self) -> None:
        self.market.disconnect()

    def is_connected(self) -> bool:
        return self.market.is_connected()

    def symbols(self) -> list[str]:
        return self.market.symbols()

    def select_symbol(self, symbol: str) -> bool:
        return self.market.select_symbol(symbol)

    def symbol_spec(self, symbol: str) -> SymbolSpec:
        return self.market.symbol_spec(symbol)

    def tick(self, symbol: str) -> TickSnapshot:
        return self.market.tick(symbol)

    def candles(self, symbol: str, timeframe: str, count: int, start_pos: int = 1) -> pd.DataFrame:
        return self.market.candles(symbol, timeframe, count, start_pos)

    def _profit(self, position: BrokerPosition, price: float) -> float:
        spec = self.symbol_spec(position.symbol)
        movement = price - position.entry_price if position.side == "BUY" else position.entry_price - price
        return movement / spec.trade_tick_size * spec.trade_tick_value * position.volume

    def _refresh(self, symbol: str | None = None) -> None:
        for ticket, position in list(self._positions.items()):
            if symbol is not None and position.symbol != symbol:
                continue
            tick = self.tick(position.symbol)
            exit_price = tick.bid if position.side == "BUY" else tick.ask
            stop_hit = position.stop_loss > 0 and (exit_price <= position.stop_loss if position.side == "BUY" else exit_price >= position.stop_loss)
            target_hit = position.take_profit > 0 and (exit_price >= position.take_profit if position.side == "BUY" else exit_price <= position.take_profit)
            if stop_hit or target_hit:
                realized = self._profit(position, exit_price)
                self._balance += realized
                self._record_exit(position, position.volume, exit_price, realized)
                del self._positions[ticket]
            else:
                self._positions[ticket] = replace(position, current_price=exit_price, profit=self._profit(position, exit_price))

    def account(self) -> AccountSnapshot:
        with self._lock:
            self._refresh()
            floating = sum(position.profit for position in self._positions.values())
            margin = 0.0
            for position in self._positions.values():
                required = self.calculate_margin(position.side, position.symbol, position.volume, position.current_price)
                margin += required or 0
            equity = self._balance + floating
            free = equity - margin
            level = equity / margin * 100 if margin > 0 else 0
            return AccountSnapshot(equity, self._balance, margin, free, level, "USD")

    def positions(self, symbol: str, magic: int) -> list[BrokerPosition]:
        with self._lock:
            self._refresh(symbol)
            return [position for position in self._positions.values() if position.symbol == symbol and position.magic == magic]

    def deals(self, start: datetime, end: datetime, symbol: str, magic: int) -> list[BrokerDeal]:
        with self._lock:
            return [item for item in self._deals if start <= item.time <= end and item.symbol == symbol]

    def _record_exit(self, position: BrokerPosition, volume: float, price: float, profit: float) -> None:
        self._next_ticket += 1
        self._deals.append(BrokerDeal(
            ticket=self._next_ticket, position_id=position.ticket, symbol=position.symbol, side=position.side,
            volume=volume, price=price, profit=profit, commission=0, swap=0, entry="OUT", time=datetime.now(UTC),
        ))

    def calculate_margin(self, side: str, symbol: str, volume: float, price: float) -> float | None:
        value = self.market.calculate_margin(side, symbol, volume, price)
        if value is not None:
            return value
        spec = self.symbol_spec(symbol)
        return price * spec.trade_contract_size * volume / 100

    def place_market_order(self, request: BrokerOrderRequest) -> BrokerResult:
        with self._lock:
            tick = self.tick(request.symbol)
            fill = tick.ask if request.side == "BUY" else tick.bid
            self._next_ticket += 1
            ticket = self._next_ticket
            position = BrokerPosition(
                ticket=ticket, symbol=request.symbol, side=request.side, volume=request.volume,
                entry_price=fill, current_price=fill, stop_loss=request.stop_loss, take_profit=request.take_profit,
                profit=0, magic=request.magic, comment=request.comment, opened_at=datetime.now(UTC),
            )
            self._positions[ticket] = position
            raw = {"mode": "PAPER", "ticket": ticket, "fill": fill, "spread": tick.ask - tick.bid}
            return BrokerResult(True, self.PAPER_RETCODE_DONE, ticket, ticket, fill, request.volume, "paper fill", raw)

    def modify_position(self, ticket: int, symbol: str, stop_loss: float, take_profit: float) -> BrokerResult:
        with self._lock:
            position = self._positions.get(ticket)
            if position is None or position.symbol != symbol:
                return BrokerResult(False, 10036, None, None, None, None, "paper position not found", {"mode": "PAPER"})
            self._positions[ticket] = replace(position, stop_loss=stop_loss, take_profit=take_profit)
            return BrokerResult(True, self.PAPER_RETCODE_DONE, ticket, None, position.current_price, position.volume, "paper modify", {"mode": "PAPER"})

    def close_position(self, position: BrokerPosition, volume: float, deviation_points: int, comment: str) -> BrokerResult:
        with self._lock:
            current = self._positions.get(position.ticket)
            if current is None or volume <= 0 or volume > current.volume + 1e-12:
                return BrokerResult(False, 10036, None, None, None, None, "paper close rejected", {"mode": "PAPER"})
            tick = self.tick(current.symbol)
            fill = tick.bid if current.side == "BUY" else tick.ask
            closed_fraction = volume / current.volume
            realized = self._profit(current, fill) * closed_fraction
            self._balance += realized
            self._record_exit(current, volume, fill, realized)
            remaining = current.volume - volume
            if remaining < self.symbol_spec(current.symbol).volume_min - 1e-12:
                del self._positions[current.ticket]
                remaining = 0
            else:
                self._positions[current.ticket] = replace(current, volume=remaining, current_price=fill, profit=self._profit(replace(current, volume=remaining), fill))
            return BrokerResult(True, self.PAPER_RETCODE_DONE, current.ticket, current.ticket, fill, volume, "paper close", {"mode": "PAPER", "realized_profit": realized, "remaining_volume": remaining, "comment": comment})

    def restore_position(self, position: BrokerPosition) -> None:
        """Rehydrates an open paper position from the database after restart."""
        with self._lock:
            self._positions[position.ticket] = position
            self._next_ticket = max(self._next_ticket, position.ticket)

    def restore_deal(self, deal: BrokerDeal) -> None:
        """Restores persisted paper deal history without duplicating tickets."""
        with self._lock:
            if all(item.ticket != deal.ticket for item in self._deals):
                self._deals.append(deal)
                self._next_ticket = max(self._next_ticket, deal.ticket)

    def restore_balance(self, balance: float) -> None:
        with self._lock:
            self._balance = balance
