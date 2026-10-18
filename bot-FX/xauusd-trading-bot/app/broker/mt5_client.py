"""Thin, mockable MetaTrader 5 adapter with no trading-domain decisions."""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import pandas as pd

from app.utils.exceptions import BrokerConnectionError, MarketDataError


@dataclass(frozen=True, slots=True)
class SymbolSpec:
    name: str
    digits: int
    point: float
    trade_tick_size: float
    trade_tick_value: float
    trade_contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    spread: int
    trade_stops_level: int
    trade_mode: int
    margin_initial: float
    visible: bool


@dataclass(frozen=True, slots=True)
class TickSnapshot:
    symbol: str
    bid: float
    ask: float
    last: float
    time: datetime

    @property
    def spread_price(self) -> float:
        return self.ask - self.bid


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    equity: float
    balance: float
    margin: float
    margin_free: float
    margin_level: float
    currency: str


@dataclass(frozen=True, slots=True)
class TradingStatus:
    server: str
    trade_mode: int
    terminal_trade_allowed: bool
    terminal_tradeapi_disabled: bool
    account_trade_allowed: bool
    account_trade_expert: bool


@dataclass(frozen=True, slots=True)
class BrokerPosition:
    ticket: int
    symbol: str
    side: str
    volume: float
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    profit: float
    magic: int
    comment: str
    opened_at: datetime


@dataclass(frozen=True, slots=True)
class BrokerDeal:
    ticket: int
    position_id: int
    symbol: str
    side: str
    volume: float
    price: float
    profit: float
    commission: float
    swap: float
    entry: str
    time: datetime


@dataclass(frozen=True, slots=True)
class BrokerOrderRequest:
    symbol: str
    side: str
    volume: float
    price: float
    stop_loss: float
    take_profit: float
    deviation_points: int
    magic: int
    comment: str


@dataclass(frozen=True, slots=True)
class BrokerResult:
    success: bool
    retcode: int
    order_ticket: int | None
    deal_ticket: int | None
    price: float | None
    volume: float | None
    comment: str
    raw: dict[str, Any]


class BrokerClient(Protocol):
    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def is_connected(self) -> bool: ...
    def symbols(self) -> list[str]: ...
    def select_symbol(self, symbol: str) -> bool: ...
    def symbol_spec(self, symbol: str) -> SymbolSpec: ...
    def tick(self, symbol: str) -> TickSnapshot: ...
    def candles(self, symbol: str, timeframe: str, count: int, start_pos: int = 1) -> pd.DataFrame: ...
    def account(self) -> AccountSnapshot: ...
    def positions(self, symbol: str, magic: int) -> list[BrokerPosition]: ...
    def deals(self, start: datetime, end: datetime, symbol: str, magic: int) -> list[BrokerDeal]: ...
    def calculate_margin(self, side: str, symbol: str, volume: float, price: float) -> float | None: ...
    def place_market_order(self, request: BrokerOrderRequest) -> BrokerResult: ...
    def modify_position(self, ticket: int, symbol: str, stop_loss: float, take_profit: float) -> BrokerResult: ...
    def close_position(self, position: BrokerPosition, volume: float, deviation_points: int, comment: str) -> BrokerResult: ...


class SynchronizedBrokerClient:
    """Serializes broker calls for MT5's process-wide Python adapter."""

    def __init__(self, inner: BrokerClient) -> None:
        self.inner = inner
        self._lock = threading.RLock()

    def connect(self) -> None:
        with self._lock:
            return self.inner.connect()

    def disconnect(self) -> None:
        with self._lock:
            return self.inner.disconnect()

    def is_connected(self) -> bool:
        with self._lock:
            return self.inner.is_connected()

    def symbols(self) -> list[str]:
        with self._lock:
            return self.inner.symbols()

    def select_symbol(self, symbol: str) -> bool:
        with self._lock:
            return self.inner.select_symbol(symbol)

    def symbol_spec(self, symbol: str) -> SymbolSpec:
        with self._lock:
            return self.inner.symbol_spec(symbol)

    def tick(self, symbol: str) -> TickSnapshot:
        with self._lock:
            return self.inner.tick(symbol)

    def candles(self, symbol: str, timeframe: str, count: int, start_pos: int = 1) -> pd.DataFrame:
        with self._lock:
            return self.inner.candles(symbol, timeframe, count, start_pos)

    def account(self) -> AccountSnapshot:
        with self._lock:
            return self.inner.account()

    def positions(self, symbol: str, magic: int) -> list[BrokerPosition]:
        with self._lock:
            return self.inner.positions(symbol, magic)

    def deals(self, start: datetime, end: datetime, symbol: str, magic: int) -> list[BrokerDeal]:
        with self._lock:
            return self.inner.deals(start, end, symbol, magic)

    def calculate_margin(self, side: str, symbol: str, volume: float, price: float) -> float | None:
        with self._lock:
            return self.inner.calculate_margin(side, symbol, volume, price)

    def place_market_order(self, request: BrokerOrderRequest) -> BrokerResult:
        with self._lock:
            return self.inner.place_market_order(request)

    def modify_position(self, ticket: int, symbol: str, stop_loss: float, take_profit: float) -> BrokerResult:
        with self._lock:
            return self.inner.modify_position(ticket, symbol, stop_loss, take_profit)

    def close_position(self, position: BrokerPosition, volume: float, deviation_points: int, comment: str) -> BrokerResult:
        with self._lock:
            return self.inner.close_position(position, volume, deviation_points, comment)


class MT5Client:
    """MetaTrader5 package wrapper; import is lazy so tests need no terminal."""

    TIMEFRAME_NAMES = {
        "M1": "TIMEFRAME_M1",
        "M5": "TIMEFRAME_M5",
        "M15": "TIMEFRAME_M15",
        "M30": "TIMEFRAME_M30",
        "H1": "TIMEFRAME_H1",
        "H4": "TIMEFRAME_H4",
    }

    def __init__(
        self,
        login: int | None = None,
        password: str | None = None,
        server: str | None = None,
        terminal_path: str | None = None,
        server_time_offset_hours: int = 0,
        module: Any | None = None,
    ) -> None:
        self.login = login
        self.password = password
        self.server = server
        self.terminal_path = terminal_path
        self.server_time_offset = timedelta(hours=server_time_offset_hours)
        self._mt5 = module

    def _utc_time(self, timestamp: float) -> datetime:
        return datetime.fromtimestamp(timestamp, UTC) - self.server_time_offset

    @property
    def module(self) -> Any:
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5
            except ImportError as exc:
                raise BrokerConnectionError("MetaTrader5 package is not installed") from exc
            self._mt5 = mt5
        return self._mt5

    def connect(self) -> None:
        kwargs: dict[str, Any] = {}
        if self.terminal_path:
            kwargs["path"] = self.terminal_path
        if self.login is not None:
            kwargs.update(login=self.login, password=self.password, server=self.server)
        if not self.module.initialize(**kwargs):
            raise BrokerConnectionError(f"MT5 initialize failed: {self.module.last_error()}")

    def disconnect(self) -> None:
        self.module.shutdown()

    def is_connected(self) -> bool:
        try:
            return self.module.terminal_info() is not None and self.module.account_info() is not None
        except Exception:
            return False

    def symbols(self) -> list[str]:
        values = self.module.symbols_get()
        if values is None:
            raise BrokerConnectionError(f"Unable to read MT5 symbols: {self.module.last_error()}")
        return [item.name for item in values]

    def select_symbol(self, symbol: str) -> bool:
        return bool(self.module.symbol_select(symbol, True))

    def symbol_spec(self, symbol: str) -> SymbolSpec:
        info = self.module.symbol_info(symbol)
        if info is None:
            raise MarketDataError(f"No symbol metadata for {symbol}")
        return SymbolSpec(
            name=info.name, digits=int(info.digits), point=float(info.point),
            trade_tick_size=float(info.trade_tick_size), trade_tick_value=float(info.trade_tick_value),
            trade_contract_size=float(info.trade_contract_size), volume_min=float(info.volume_min),
            volume_max=float(info.volume_max), volume_step=float(info.volume_step), spread=int(info.spread),
            trade_stops_level=int(info.trade_stops_level), trade_mode=int(info.trade_mode),
            margin_initial=float(getattr(info, "margin_initial", 0) or 0), visible=bool(info.visible),
        )

    def tick(self, symbol: str) -> TickSnapshot:
        value = self.module.symbol_info_tick(symbol)
        if value is None:
            raise MarketDataError(f"No current tick for {symbol}")
        timestamp = getattr(value, "time_msc", 0) / 1000 or value.time
        return TickSnapshot(symbol, float(value.bid), float(value.ask), float(value.last), self._utc_time(timestamp))

    def candles(self, symbol: str, timeframe: str, count: int, start_pos: int = 1) -> pd.DataFrame:
        if timeframe not in self.TIMEFRAME_NAMES:
            raise MarketDataError(f"Unsupported timeframe: {timeframe}")
        mt5_timeframe = getattr(self.module, self.TIMEFRAME_NAMES[timeframe])
        rates = self.module.copy_rates_from_pos(symbol, mt5_timeframe, start_pos, count)
        if rates is None or len(rates) == 0:
            raise MarketDataError(f"No {timeframe} candles for {symbol}: {self.module.last_error()}")
        frame = pd.DataFrame(rates)
        frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True) - pd.Timedelta(self.server_time_offset)
        frame = frame.rename(columns={"tick_volume": "volume"})
        if "real_volume" in frame and frame["real_volume"].fillna(0).sum() > 0:
            frame["volume"] = frame["real_volume"]
        return frame[["time", "open", "high", "low", "close", "volume", "spread"]].sort_values("time").reset_index(drop=True)

    def account(self) -> AccountSnapshot:
        value = self.module.account_info()
        if value is None:
            raise BrokerConnectionError(f"No MT5 account information: {self.module.last_error()}")
        return AccountSnapshot(float(value.equity), float(value.balance), float(value.margin), float(value.margin_free), float(value.margin_level or 0), str(value.currency))

    def trading_status(self) -> TradingStatus:
        """Return broker/terminal permissions without exposing account credentials."""
        account = self.module.account_info()
        terminal = self.module.terminal_info()
        if account is None or terminal is None:
            raise BrokerConnectionError(f"No MT5 trading status: {self.module.last_error()}")
        return TradingStatus(
            server=str(account.server),
            trade_mode=int(account.trade_mode),
            terminal_trade_allowed=bool(terminal.trade_allowed),
            terminal_tradeapi_disabled=bool(terminal.tradeapi_disabled),
            account_trade_allowed=bool(account.trade_allowed),
            account_trade_expert=bool(account.trade_expert),
        )

    def positions(self, symbol: str, magic: int) -> list[BrokerPosition]:
        values = self.module.positions_get(symbol=symbol)
        if values is None:
            raise BrokerConnectionError(f"Unable to read positions: {self.module.last_error()}")
        buy_type = self.module.POSITION_TYPE_BUY
        return [
            BrokerPosition(
                ticket=int(item.ticket), symbol=item.symbol, side="BUY" if item.type == buy_type else "SELL",
                volume=float(item.volume), entry_price=float(item.price_open), current_price=float(item.price_current),
                stop_loss=float(item.sl), take_profit=float(item.tp), profit=float(item.profit), magic=int(item.magic),
                comment=str(item.comment), opened_at=self._utc_time(item.time),
            )
            for item in values if int(item.magic) == magic
        ]

    def deals(self, start: datetime, end: datetime, symbol: str, magic: int) -> list[BrokerDeal]:
        values = self.module.history_deals_get(start, end, group=f"*{symbol}*")
        if values is None:
            raise BrokerConnectionError(f"Unable to read deal history: {self.module.last_error()}")
        buy_type = self.module.DEAL_TYPE_BUY
        entry_names = {
            getattr(self.module, "DEAL_ENTRY_IN", 0): "IN",
            getattr(self.module, "DEAL_ENTRY_OUT", 1): "OUT",
            getattr(self.module, "DEAL_ENTRY_INOUT", 2): "INOUT",
            getattr(self.module, "DEAL_ENTRY_OUT_BY", 3): "OUT_BY",
        }
        return [
            BrokerDeal(
                ticket=int(item.ticket), position_id=int(item.position_id), symbol=item.symbol,
                side="BUY" if item.type == buy_type else "SELL", volume=float(item.volume),
                price=float(item.price), profit=float(item.profit), commission=float(item.commission),
                swap=float(item.swap), entry=entry_names.get(int(item.entry), str(item.entry)),
                time=self._utc_time(item.time),
            )
            for item in values if int(item.magic) == magic and item.symbol == symbol
        ]

    def calculate_margin(self, side: str, symbol: str, volume: float, price: float) -> float | None:
        order_type = self.module.ORDER_TYPE_BUY if side == "BUY" else self.module.ORDER_TYPE_SELL
        value = self.module.order_calc_margin(order_type, symbol, volume, price)
        return None if value is None else float(value)

    def _result(self, value: Any) -> BrokerResult:
        if value is None:
            return BrokerResult(False, -1, None, None, None, None, str(self.module.last_error()), {})
        success_codes = {self.module.TRADE_RETCODE_DONE, getattr(self.module, "TRADE_RETCODE_DONE_PARTIAL", -999)}
        raw = value._asdict() if hasattr(value, "_asdict") else {"value": str(value)}
        return BrokerResult(
            int(value.retcode) in success_codes, int(value.retcode), int(value.order) or None,
            int(value.deal) or None, float(value.price) or None, float(value.volume) or None,
            str(value.comment), raw,
        )

    def place_market_order(self, request: BrokerOrderRequest) -> BrokerResult:
        order_type = self.module.ORDER_TYPE_BUY if request.side == "BUY" else self.module.ORDER_TYPE_SELL
        info = self.module.symbol_info(request.symbol)
        filling_flags = int(getattr(info, "filling_mode", 0) or 0) if info is not None else 0
        if filling_flags & int(getattr(self.module, "SYMBOL_FILLING_IOC", 2)):
            filling = self.module.ORDER_FILLING_IOC
        elif filling_flags & int(getattr(self.module, "SYMBOL_FILLING_FOK", 1)):
            filling = self.module.ORDER_FILLING_FOK
        else:
            filling = self.module.ORDER_FILLING_RETURN
        payload = {
            "action": self.module.TRADE_ACTION_DEAL, "symbol": request.symbol, "volume": request.volume,
            "type": order_type, "price": request.price, "sl": request.stop_loss, "tp": request.take_profit,
            "deviation": request.deviation_points, "magic": request.magic, "comment": request.comment,
            "type_time": self.module.ORDER_TIME_GTC, "type_filling": filling,
        }
        checked = self.module.order_check(payload)
        if checked is None:
            return BrokerResult(False, -1, None, None, None, request.volume, f"order_check failed: {self.module.last_error()}", {})
        if int(checked.retcode) != 0:
            raw = checked._asdict() if hasattr(checked, "_asdict") else {"value": str(checked)}
            return BrokerResult(False, int(checked.retcode), None, None, None, request.volume, str(checked.comment), raw)
        return self._result(self.module.order_send(payload))

    def modify_position(self, ticket: int, symbol: str, stop_loss: float, take_profit: float) -> BrokerResult:
        payload = {"action": self.module.TRADE_ACTION_SLTP, "position": ticket, "symbol": symbol, "sl": stop_loss, "tp": take_profit}
        return self._result(self.module.order_send(payload))

    def close_position(self, position: BrokerPosition, volume: float, deviation_points: int, comment: str) -> BrokerResult:
        tick = self.tick(position.symbol)
        is_buy = position.side == "BUY"
        info = self.module.symbol_info(position.symbol)
        filling_flags = int(getattr(info, "filling_mode", 0) or 0) if info is not None else 0
        if filling_flags & int(getattr(self.module, "SYMBOL_FILLING_IOC", 2)):
            filling = self.module.ORDER_FILLING_IOC
        elif filling_flags & int(getattr(self.module, "SYMBOL_FILLING_FOK", 1)):
            filling = self.module.ORDER_FILLING_FOK
        else:
            filling = self.module.ORDER_FILLING_RETURN
        payload = {
            "action": self.module.TRADE_ACTION_DEAL, "position": position.ticket, "symbol": position.symbol,
            "volume": volume, "type": self.module.ORDER_TYPE_SELL if is_buy else self.module.ORDER_TYPE_BUY,
            "price": tick.bid if is_buy else tick.ask, "deviation": deviation_points, "magic": position.magic,
            "comment": comment, "type_time": self.module.ORDER_TIME_GTC, "type_filling": filling,
        }
        return self._result(self.module.order_send(payload))
