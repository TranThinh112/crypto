"""Application-specific exceptions."""


class TradingBotError(Exception):
    """Base class for expected bot errors."""


class ConfigurationError(TradingBotError):
    pass


class BrokerConnectionError(TradingBotError):
    pass


class SymbolResolutionError(TradingBotError):
    pass


class MarketDataError(TradingBotError):
    pass


class OrderValidationError(TradingBotError):
    pass


class DuplicateOrderError(TradingBotError):
    pass


class ReconciliationError(TradingBotError):
    pass
