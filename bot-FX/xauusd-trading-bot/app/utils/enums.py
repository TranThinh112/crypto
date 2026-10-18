"""Domain enumerations used instead of scattered booleans."""

from enum import Enum


class TradingMode(str, Enum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE = "LIVE"


class TrendDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    SIDEWAYS = "SIDEWAYS"
    UNCERTAIN = "UNCERTAIN"


class SignalSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NO_TRADE = "NO_TRADE"


class BotState(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    ENTRY_PAUSED = "ENTRY_PAUSED"
    RISK_PAUSED = "RISK_PAUSED"
    COOLDOWN = "COOLDOWN"
    CLOSING_BASKET = "CLOSING_BASKET"
    ERROR = "ERROR"


class BasketState(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    CLOSE_FAILED = "CLOSE_FAILED"


class TradeState(str, Enum):
    PLANNED = "PLANNED"
    SUBMITTED = "SUBMITTED"
    OPEN = "OPEN"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class BasketProfitMode(str, Enum):
    R_MULTIPLE = "R_MULTIPLE"
    FIXED_USD = "FIXED_USD"
    EQUITY_PERCENT = "EQUITY_PERCENT"


class BasketStopLossMode(str, Enum):
    FIXED_USD = "FIXED_USD"
    BALANCED_DAILY = "BALANCED_DAILY"


class StopLossMethod(str, Enum):
    SWING_ATR = "SWING_ATR"
    ATR = "ATR"


class TakeProfitMethod(str, Enum):
    RISK_REWARD = "RISK_REWARD"
    SWING = "SWING"
    ATR = "ATR"


class CloseReason(str, Enum):
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    MANUAL = "MANUAL"
    TREND_REVERSAL = "TREND_REVERSAL"
    PROFIT_PROTECTION = "PROFIT_PROTECTION"
    WEEKEND = "WEEKEND"
    BROKER_EXIT = "BROKER_EXIT"


class OrderAction(str, Enum):
    OPEN = "OPEN"
    MODIFY = "MODIFY"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    CLOSE = "CLOSE"
