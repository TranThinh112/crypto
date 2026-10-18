"""Dependency container and lifecycle for API and worker runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select

from app.broker.mt5_client import BrokerClient, MT5Client, SymbolSpec, SynchronizedBrokerClient
from app.broker.paper_client import PaperBrokerClient
from app.broker.symbol_resolver import SymbolResolver
from app.config.settings import AppSettings, BasketStopLossConfig, BasketTakeProfitConfig, FOREX_SYMBOLS, ForexTradingConfig, HardTradeConfig, PositionControlConfig, SymbolConfig, TradingConfig, load_trading_config, save_trading_config
from app.database import Database
from app.models.trade import Trade
from app.services.trading_orchestrator import TradingOrchestrator
from app.utils.enums import TradeState, TradingMode
from app.utils.exceptions import BrokerConnectionError


@dataclass
class Runtime:
    settings: AppSettings
    config: TradingConfig
    database: Database
    project_path: Path
    broker: BrokerClient | None = None
    symbol: str | None = None
    spec: SymbolSpec | None = None
    orchestrator: TradingOrchestrator | None = None
    configs: dict[str, TradingConfig] = field(default_factory=dict)
    symbols: dict[str, str] = field(default_factory=dict)
    specs: dict[str, SymbolSpec] = field(default_factory=dict)
    orchestrators: dict[str, TradingOrchestrator] = field(default_factory=dict)
    initialization_error: str | None = None

    @staticmethod
    def _aliases_for(base_symbol: str) -> tuple[str, ...]:
        if base_symbol == "BTCUSD":
            return ("BTCUSD", "BTCUSDm", "BTCUSD.a", "BTCUSD.pro")
        if base_symbol == "XAUUSD":
            return ("GOLD", "XAUUSD", "XAUUSDm", "XAUUSD.a", "XAUUSD.pro")
        return (base_symbol, f"{base_symbol}m", f"{base_symbol}.a", f"{base_symbol}.pro")

    @staticmethod
    def _is_forex_symbol(base_symbol: str) -> bool:
        return base_symbol in FOREX_SYMBOLS

    def _portfolio_bases(self) -> tuple[str, ...]:
        if self.config.portfolio.enabled and self.config.portfolio.symbols:
            symbols = list(self.config.portfolio.symbols)
        else:
            symbols = [self.config.symbol.base_symbol]
        open_forex_bases = self._open_forex_trade_bases()
        if self.config.forex_trading.enabled:
            symbols.extend(symbol for symbol in self.config.forex_trading.symbols if symbol not in symbols)
        else:
            symbols.extend(symbol for symbol in open_forex_bases if symbol not in symbols)
        return tuple(dict.fromkeys(
            symbol for symbol in symbols
            if not self._is_forex_symbol(symbol) or self.config.forex_trading.enabled or symbol in open_forex_bases
        ))

    def _open_forex_trade_bases(self) -> tuple[str, ...]:
        states = (TradeState.SUBMITTED.value, TradeState.OPEN.value, TradeState.PARTIALLY_CLOSED.value)
        with self.database.transaction() as session:
            rows = list(session.scalars(select(Trade.symbol).where(Trade.state.in_(states))))
        bases: list[str] = []
        for symbol in rows:
            upper = str(symbol).upper()
            for base in FOREX_SYMBOLS:
                if upper.startswith(base) and base not in bases:
                    bases.append(base)
                    break
        return tuple(bases)

    def _config_for_symbol(self, base_symbol: str) -> TradingConfig:
        if base_symbol == self.config.symbol.base_symbol:
            base_config = self.config
        else:
            candidate = self.project_path / "app" / "config" / f"trading_config_{base_symbol.lower().replace('xauusd', 'gold')}.yaml"
            base_config = load_trading_config(candidate) if candidate.exists() else self.config
        symbol = SymbolConfig(base_symbol=base_symbol, auto_detect_alias=True, allowed_aliases=self._aliases_for(base_symbol))
        broker = base_config.broker.model_copy(update={"magic_number": self.config.broker.magic_number})
        session = base_config.session
        if base_symbol != "BTCUSD":
            session = session.model_copy(update={
                "allowed_days": ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"),
                "close_before_weekend": session.close_before_weekend.model_copy(update={"enabled": True}),
            })
        return base_config.model_copy(update={
            "symbol": symbol,
            "broker": broker,
            "hard_trade": self.config.hard_trade,
            "position_control": self.config.position_control,
            "session": session,
        })

    def initialize_broker(self) -> None:
        if not self.settings.broker_startup_enabled or self.config.bot.mode is TradingMode.BACKTEST:
            return
        mt5: MT5Client | None = None
        try:
            mt5 = MT5Client(
                login=self.settings.mt5_login, password=self.settings.mt5_password,
                server=self.settings.mt5_server, terminal_path=self.settings.mt5_terminal_path,
                server_time_offset_hours=self.config.broker.server_time_offset_hours,
            )
            mt5.connect()
            if self.config.bot.mode is TradingMode.LIVE:
                status = mt5.trading_status()
                demo_mode = int(getattr(mt5.module, "ACCOUNT_TRADE_MODE_DEMO", 0))
                if self.settings.require_demo_account and status.trade_mode != demo_mode:
                    raise BrokerConnectionError("Automated broker orders are restricted to an MT5 Demo account")
                if status.terminal_tradeapi_disabled:
                    raise BrokerConnectionError("MT5 Python trading API is disabled in the terminal")
                if not status.terminal_trade_allowed:
                    raise BrokerConnectionError("Enable the Algo Trading button in MT5 before starting automated broker orders")
                if not status.account_trade_allowed or not status.account_trade_expert:
                    raise BrokerConnectionError("The current MT5 account does not allow automated trading")
            raw_broker: BrokerClient = PaperBrokerClient(mt5, self.config.backtest.initial_equity) if self.config.bot.mode is TradingMode.PAPER else mt5
            broker = SynchronizedBrokerClient(raw_broker)
            configs: dict[str, TradingConfig] = {}
            symbols: dict[str, str] = {}
            specs: dict[str, SymbolSpec] = {}
            for base_symbol in self._portfolio_bases():
                symbol_config = self._config_for_symbol(base_symbol)
                resolved = SymbolResolver(broker, symbol_config.symbol).resolve()
                configs[base_symbol] = symbol_config
                symbols[base_symbol] = resolved.name
                specs[base_symbol] = resolved.specification
            portfolio_symbols = tuple(symbols.values())
            orchestrators = {
                base_symbol: TradingOrchestrator(
                    self.database, broker, config, symbols[base_symbol], specs[base_symbol],
                    self.settings.enable_live_trading, self.project_path, portfolio_symbols,
                )
                for base_symbol, config in configs.items()
            }
            primary = next(iter(orchestrators), None)
            self.broker = broker
            self.configs = configs
            self.symbols = symbols
            self.specs = specs
            self.orchestrators = orchestrators
            self.orchestrator = orchestrators.get(primary) if primary else None
            self.symbol = symbols.get(primary) if primary else None
            self.spec = specs.get(primary) if primary else None
            self.initialization_error = None
            if self.settings.auto_start_bot:
                for orchestrator in self.orchestrators.values():
                    orchestrator.start()
        except Exception as exc:
            self.initialization_error = str(exc)
            self.broker = None
            self.symbol = None
            self.spec = None
            self.orchestrator = None
            self.configs = {}
            self.symbols = {}
            self.specs = {}
            self.orchestrators = {}
            if mt5 is not None and mt5.is_connected():
                mt5.disconnect()

    def shutdown(self) -> None:
        if self.orchestrators:
            for orchestrator in self.orchestrators.values():
                if orchestrator.state.value != "STOPPED":
                    orchestrator.stop()
        if self.broker and self.broker.is_connected():
            self.broker.disconnect()

    def start_all(self) -> None:
        for orchestrator in self.orchestrators.values():
            orchestrator.start()

    def stop_all(self) -> None:
        for orchestrator in self.orchestrators.values():
            orchestrator.stop()

    def pause_all(self) -> None:
        for orchestrator in self.orchestrators.values():
            orchestrator.pause_entry()

    def resume_all(self) -> bool:
        return all(orchestrator.resume_entry() for orchestrator in self.orchestrators.values())

    def update_daily_risk_limits(self, daily_profit_target_usd: float | None = None, max_daily_loss_usd: float | None = None) -> TradingConfig:
        updates = {}
        if daily_profit_target_usd is not None:
            updates["daily_profit_target_usd"] = daily_profit_target_usd
        if max_daily_loss_usd is not None:
            updates["max_daily_loss_usd"] = max_daily_loss_usd
        if not updates:
            return self.config

        daily_risk = self.config.daily_risk.model_copy(update=updates)
        self.config = self.config.model_copy(update={"daily_risk": daily_risk})

        if self.configs:
            for key, config in list(self.configs.items()):
                symbol_daily_risk = config.daily_risk.model_copy(update=updates)
                symbol_config = config.model_copy(update={"daily_risk": symbol_daily_risk})
                self.configs[key] = symbol_config
                orchestrator = self.orchestrators.get(key)
                if orchestrator is not None:
                    orchestrator.update_daily_risk(symbol_daily_risk)
        elif self.orchestrator is not None:
            self.orchestrator.update_daily_risk(daily_risk)

        save_trading_config(self.config, self.settings.config_path)
        return self.config

    def update_basket_stop_loss(self, basket_stop_loss: BasketStopLossConfig) -> TradingConfig:
        self.config = self.config.model_copy(update={"basket_stop_loss": basket_stop_loss})

        if self.configs:
            for key, config in list(self.configs.items()):
                symbol_config = config.model_copy(update={"basket_stop_loss": basket_stop_loss})
                self.configs[key] = symbol_config
                orchestrator = self.orchestrators.get(key)
                if orchestrator is not None:
                    orchestrator.update_basket_stop_loss(basket_stop_loss)
        elif self.orchestrator is not None:
            self.orchestrator.update_basket_stop_loss(basket_stop_loss)

        save_trading_config(self.config, self.settings.config_path)
        return self.config

    def update_basket_take_profit(self, basket_take_profit: BasketTakeProfitConfig) -> TradingConfig:
        self.config = self.config.model_copy(update={"basket_take_profit": basket_take_profit})

        if self.configs:
            for key, config in list(self.configs.items()):
                symbol_config = config.model_copy(update={"basket_take_profit": basket_take_profit})
                self.configs[key] = symbol_config
                orchestrator = self.orchestrators.get(key)
                if orchestrator is not None:
                    orchestrator.update_basket_take_profit(basket_take_profit)
        elif self.orchestrator is not None:
            self.orchestrator.update_basket_take_profit(basket_take_profit)

        save_trading_config(self.config, self.settings.config_path)
        return self.config

    def update_hard_trade(self, hard_trade: HardTradeConfig) -> TradingConfig:
        self.config = self.config.model_copy(update={"hard_trade": hard_trade})

        if self.configs:
            for key, config in list(self.configs.items()):
                symbol_config = config.model_copy(update={"hard_trade": hard_trade})
                self.configs[key] = symbol_config
                orchestrator = self.orchestrators.get(key)
                if orchestrator is not None:
                    orchestrator.update_hard_trade(hard_trade)
        elif self.orchestrator is not None:
            self.orchestrator.update_hard_trade(hard_trade)

        save_trading_config(self.config, self.settings.config_path)
        return self.config

    def update_position_control(self, position_control: PositionControlConfig) -> TradingConfig:
        self.config = self.config.model_copy(update={"position_control": position_control})

        if self.configs:
            for key, config in list(self.configs.items()):
                symbol_config = config.model_copy(update={"position_control": position_control})
                self.configs[key] = symbol_config
                orchestrator = self.orchestrators.get(key)
                if orchestrator is not None:
                    orchestrator.update_position_control(position_control)
        elif self.orchestrator is not None:
            self.orchestrator.update_position_control(position_control)

        save_trading_config(self.config, self.settings.config_path)
        return self.config

    def update_forex_trading(self, forex_trading: ForexTradingConfig) -> TradingConfig:
        self.config = self.config.model_copy(update={"forex_trading": forex_trading})
        save_trading_config(self.config, self.settings.config_path)
        return self.config

    def apply_forex_trading(self, forex_trading: ForexTradingConfig) -> TradingConfig:
        previous_config = self.config
        was_running = any(orchestrator.state.value != "STOPPED" for orchestrator in self.orchestrators.values())
        self.update_forex_trading(forex_trading)
        self.shutdown()
        self.initialize_broker()
        if self.initialization_error is not None:
            error = self.initialization_error
            self.config = previous_config
            save_trading_config(self.config, self.settings.config_path)
            self.shutdown()
            self.initialize_broker()
            if was_running and self.orchestrators:
                self.start_all()
            raise BrokerConnectionError(f"Could not apply Forex mode: {error}")
        if was_running and self.orchestrators:
            self.start_all()
        return self.config

    def close_all_manually(self, reason: str) -> bool:
        return all(orchestrator.close_all_manually(reason) for orchestrator in self.orchestrators.values())

    def close_basket_manually(self, basket_external_id: str, reason: str) -> bool:
        return any(orchestrator.close_basket_manually(basket_external_id, reason) for orchestrator in self.orchestrators.values())
