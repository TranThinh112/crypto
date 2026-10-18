"""Validated, immutable application and trading configuration."""

from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.utils.enums import BasketProfitMode, BasketStopLossMode, StopLossMethod, TakeProfitMethod, TradingMode


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BotConfig(StrictModel):
    name: str = "XAUUSD_RULE_BASED_BOT"
    mode: TradingMode = TradingMode.PAPER
    scan_interval_seconds: float = Field(default=5, gt=0)
    position_monitor_interval_seconds: float = Field(default=2, ge=1)


SupportedSymbol = Literal["XAUUSD", "BTCUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"]

FOREX_SYMBOLS: tuple[str, ...] = ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD")

class SymbolConfig(StrictModel):
    base_symbol: SupportedSymbol = "XAUUSD"
    auto_detect_alias: bool = True
    allowed_aliases: tuple[str, ...]


class TimeframeConfig(StrictModel):
    trend: tuple[Literal["H4", "H1"], ...] = ("H4", "H1")
    setup: Literal["M15"] = "M15"
    entry: Literal["M5"] = "M5"
    candle_history: int = Field(default=500, ge=250)


class StrategyConfig(StrictModel):
    type: Literal["TREND_PULLBACK"] = "TREND_PULLBACK"
    require_h4_h1_alignment: bool = True
    minimum_signal_score: int = Field(default=78, ge=0, le=100)
    ema_fast: int = Field(default=20, gt=1)
    ema_mid: int = Field(default=50, gt=1)
    ema_slow: int = Field(default=200, gt=1)
    rsi_period: int = Field(default=14, gt=1)
    rsi_buy_min: float = 45
    rsi_buy_max: float = 68
    rsi_sell_min: float = 32
    rsi_sell_max: float = 55
    atr_period: int = Field(default=14, gt=1)
    adx_period: int = Field(default=14, gt=1)
    minimum_adx: float = Field(default=20, ge=0)
    macd_fast: int = Field(default=12, gt=1)
    macd_slow: int = Field(default=26, gt=1)
    macd_signal: int = Field(default=9, gt=1)
    swing_window: int = Field(default=5, ge=2)
    pullback_tolerance_atr: float = Field(default=0.35, gt=0)

    @model_validator(mode="after")
    def validate_periods(self) -> "StrategyConfig":
        if not self.ema_fast < self.ema_mid < self.ema_slow:
            raise ValueError("EMA periods must be ordered fast < mid < slow")
        if self.macd_fast >= self.macd_slow:
            raise ValueError("MACD fast period must be below slow period")
        return self


class FastScalpConfig(StrictModel):
    enabled: bool = False
    timeframe: Literal["M1"] = "M1"
    max_lot_per_entry: float | None = Field(default=None, gt=0)
    minimum_signal_score: int = Field(default=70, ge=0, le=100)
    countertrend_minimum_signal_score: int = Field(default=80, ge=0, le=100)
    countertrend_reversal_enabled: bool = True
    reversal_minimum_signal_score: int = Field(default=65, ge=0, le=100)
    overbought_rsi: float = Field(default=68, ge=50, le=100)
    oversold_rsi: float = Field(default=32, ge=0, le=50)
    avoid_same_trend_chase: bool = True
    same_trend_buy_max_rsi: float = Field(default=70, ge=50, le=100)
    same_trend_sell_min_rsi: float = Field(default=30, ge=0, le=50)
    same_trend_max_ema20_distance_atr: float = Field(default=2.5, gt=0)
    stop_atr_multiplier: float = Field(default=1.2, gt=0)
    risk_reward: float = Field(default=1.8, gt=0)
    require_candle_confirmation: bool = True
    minimum_historical_win_rate: float | None = Field(default=None, ge=0, le=100)
    historical_win_rate_min_trades: int = Field(default=10, ge=1)
    historical_win_rate_lookback: int = Field(default=100, ge=1)


class HardTradeConfig(StrictModel):
    enabled: bool = False
    minimum_setup_win_rate: float = Field(default=70.0, ge=0, le=100)
    m5_minimum_setup_win_rate: float = Field(default=80.0, ge=0, le=100)
    max_lot_per_entry: float = Field(default=0.03, gt=0)
    max_open_positions: int = Field(default=7, ge=1)
    max_add_entry_distance_atr: float = Field(default=1.0, gt=0)
    max_losing_basket_add_usd: float = Field(default=2.0, ge=0)
    allow_fast_scalp: bool = False
    scan_interval_seconds: float = Field(default=1.0, gt=0)
    position_monitor_interval_seconds: float = Field(default=1.0, ge=1)
    preferred_setup_timeframe: Literal["M15", "M30"] = "M30"
    preferred_entry_timeframe: Literal["M5", "M15"] = "M15"
    emergency_exit_on_restart: bool = True
    emergency_exit_max_loss_usd: float = Field(default=8.0, gt=0)
    emergency_exit_max_adverse_r: float = Field(default=0.8, gt=0)
    btc_weekend_relaxation_enabled: bool = False
    btc_weekend_signal_score_discount: int = Field(default=5, ge=0, le=30)
    btc_weekend_setup_win_rate_discount: float = Field(default=5.0, ge=0, le=30)
    btc_weekend_max_atr_multiplier_discount: float = Field(default=1.0, ge=0)

class M15QuickTradeConfig(StrictModel):
    enabled: bool = False
    minimum_signal_score: int = Field(default=80, ge=0, le=100)
    minimum_setup_win_rate: float = Field(default=76.0, ge=0, le=100)
    minimum_adx: float = Field(default=18.0, ge=0)
    max_body_atr: float = Field(default=1.8, gt=0)
    min_body_atr: float = Field(default=0.35, gt=0)
    max_lot_per_entry: float = Field(default=0.01, gt=0)
    risk_per_entry_percent: float = Field(default=0.03, gt=0, le=2)
    minimum_lot_max_risk_percent: float = Field(default=0.12, gt=0, le=2)
    require_profit_factor_gate: bool = True

class RecoveryModeConfig(StrictModel):
    enabled: bool = True
    trigger_basket_position_count: int = Field(default=7, ge=1)
    soft_minimum_setup_win_rate: float = Field(default=72.0, ge=0, le=100)
    hard_minimum_setup_win_rate: float = Field(default=75.0, ge=0, le=100)
    soft_minimum_loss_usd: float = Field(default=4.0, ge=0)
    soft_maximum_loss_usd: float = Field(default=6.0, ge=0)
    hard_minimum_loss_usd: float = Field(default=8.0, ge=0)
    soft_recovered_ratio: float = Field(default=0.5, ge=0, le=1)
    normal_recovered_ratio: float = Field(default=1.0, ge=0, le=5)

class SignalScoringConfig(StrictModel):
    h4_trend_alignment: int = 20
    h1_trend_alignment: int = 15
    ema_alignment: int = 10
    market_structure: int = 10
    pullback_quality: int = 15
    candle_confirmation: int = 10
    macd_confirmation: int = 5
    rsi_confirmation: int = 5
    adx_strength: int = 5
    risk_reward_quality: int = 5

    @model_validator(mode="after")
    def total_is_one_hundred(self) -> "SignalScoringConfig":
        if sum(self.model_dump().values()) != 100:
            raise ValueError("signal_scoring weights must total 100")
        return self


class PositionControlConfig(StrictModel):
    max_open_positions: int | None = Field(default=7, ge=1)
    max_buy_positions: int | None = Field(default=7, ge=1)
    max_sell_positions: int | None = Field(default=7, ge=1)
    allow_opposite_positions: bool = False
    auto_refill_empty_slots: bool = True
    entry_cooldown_minutes: int = Field(default=15, ge=0)
    minimum_entry_distance_atr: float = Field(default=0.4, ge=0)
    prohibit_adding_to_losing_basket: bool = True


class RiskConfig(StrictModel):
    risk_per_entry_percent: float = Field(default=0.25, gt=0, le=2)
    max_basket_risk_percent: float | None = Field(default=1.25, gt=0, le=100)
    max_lot_per_entry: float | None = Field(default=None, gt=0)
    max_total_lot: float | None = Field(default=0.10, gt=0)
    minimum_free_margin_percent: float = Field(default=40, ge=0, le=100)


class StopLossConfig(StrictModel):
    method: StopLossMethod = StopLossMethod.SWING_ATR
    atr_buffer_multiplier: float = Field(default=0.3, ge=0)
    minimum_atr_multiplier: float = Field(default=1.0, gt=0)
    maximum_atr_multiplier: float = Field(default=2.5, gt=0)
    relaxed_forex_maximum_atr_multiplier: float = Field(default=10.0, gt=0)
    relaxed_forex_minimum_signal_score: int = Field(default=85, ge=0, le=100)

    @model_validator(mode="after")
    def validate_range(self) -> "StopLossConfig":
        if self.minimum_atr_multiplier > self.maximum_atr_multiplier:
            raise ValueError("minimum ATR multiplier cannot exceed maximum")
        if self.relaxed_forex_maximum_atr_multiplier < self.maximum_atr_multiplier:
            raise ValueError("relaxed forex ATR multiplier cannot be below maximum")
        return self


class TakeProfitConfig(StrictModel):
    method: TakeProfitMethod = TakeProfitMethod.RISK_REWARD
    minimum_risk_reward: float = Field(default=1.8, gt=0)
    default_risk_reward: float = Field(default=2.0, gt=0)


class BasketTakeProfitConfig(StrictModel):
    enabled: bool = True
    mode: BasketProfitMode = BasketProfitMode.R_MULTIPLE
    target_r_multiple: float = Field(default=1.5, gt=0)
    target_fixed_usd: float = Field(default=15, gt=0)
    fast_target_fixed_usd: float = Field(default=2, gt=0)
    target_equity_percent: float = Field(default=1.0, gt=0)


class BasketStopLossConfig(StrictModel):
    enabled: bool = True
    mode: BasketStopLossMode = BasketStopLossMode.FIXED_USD
    maximum_loss_percent: float = Field(default=1.25, gt=0)
    maximum_loss_usd: float = Field(default=20, gt=0)
    hard_max_loss_usd: float | None = Field(default=8.0, gt=0)
    balanced_daily_loss_ratio: float = Field(default=0.2, gt=0, le=1)
    balanced_minimum_loss_usd: float = Field(default=3, gt=0)


class PositionRevalidationConfig(StrictModel):
    enabled: bool = True
    close_opposite_positions: bool = True
    require_rotation_trade_signal: bool = True
    minimum_rotation_score: int = Field(default=60, ge=0, le=100)
    minimum_keep_score: int = Field(default=5, ge=0, le=11)
    early_loss_protection_enabled: bool = False
    early_loss_min_age_minutes: int = Field(default=5, ge=0)
    early_loss_adverse_r: float = Field(default=0.6, gt=0)
    early_loss_minimum_keep_score: int = Field(default=5, ge=0, le=11)
    early_loss_close_on_unclear_trend: bool = False
    early_loss_after_runup_r: float = Field(default=0.25, ge=0)
    early_loss_after_runup_adverse_r: float = Field(default=0.25, gt=0)
    keep_event_retention_minutes: int = Field(default=180, ge=1)
    keep_event_cleanup_interval_seconds: int = Field(default=300, ge=30)


class BreakEvenConfig(StrictModel):
    enabled: bool = True
    trigger_r_multiple: float = Field(default=0.8, gt=0)
    lock_profit_points: int = Field(default=20, ge=0)
    apply_once: bool = True


class TrailingStopConfig(StrictModel):
    enabled: bool = True
    activation_r_multiple: float = Field(default=1.0, gt=0)
    method: Literal["ATR"] = "ATR"
    atr_multiplier: float = Field(default=1.5, gt=0)
    update_step_points: int = Field(default=20, gt=0)


class PartialCloseLevel(StrictModel):
    trigger_r: float = Field(gt=0)
    close_percent: float = Field(gt=0, lt=100)


class PartialCloseConfig(StrictModel):
    enabled: bool = True
    levels: tuple[PartialCloseLevel, ...]

    @model_validator(mode="after")
    def validate_levels(self) -> "PartialCloseConfig":
        triggers = [level.trigger_r for level in self.levels]
        if triggers != sorted(set(triggers)):
            raise ValueError("partial-close triggers must be unique and ascending")
        if sum(level.close_percent for level in self.levels) >= 100:
            raise ValueError("partial-close percentages must total below 100")
        return self


class ProfitProtectionConfig(StrictModel):
    enabled: bool = True
    minimum_peak_profit_usd: float = Field(default=5.0, gt=0)
    giveback_percent: float = Field(default=45.0, gt=0, lt=100)
    hard_peak_profit_usd: float = Field(default=6.0, gt=0)
    hard_floor_profit_usd: float = Field(default=3.0, ge=0)
    require_break_even_applied: bool = True


class SpreadGuardConfig(StrictModel):
    enabled: bool = True
    maximum_spread_points: int = Field(default=80, gt=0)
    maximum_spread_atr_ratio: float = Field(default=0.08, gt=0)


class DailyRiskConfig(StrictModel):
    max_daily_loss_percent: float = Field(default=2, gt=0)
    daily_profit_target_percent: float = Field(default=1.5, gt=0)
    max_daily_loss_usd: float | None = Field(default=None, gt=0)
    daily_profit_target_usd: float | None = Field(default=None, gt=0)
    max_consecutive_losses: int = Field(default=3, ge=1)
    pause_until_next_day: bool = True


class CooldownConfig(StrictModel):
    enabled: bool = True
    after_take_profit_minutes: int = Field(default=30, ge=0)
    after_stop_loss_minutes: int = Field(default=120, ge=0)
    after_manual_close_minutes: int = Field(default=30, ge=0)
    after_trend_reversal_minutes: int = Field(default=60, ge=0)


class SessionWindow(StrictModel):
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class EntrySessionProfileConfig(StrictModel):
    enabled: bool = False
    active_sessions: tuple[SessionWindow, ...] = ()
    quiet_minimum_signal_score: int = Field(default=80, ge=0, le=100)


class AvoidRolloverConfig(SessionWindow):
    enabled: bool = True


class WeekendCloseConfig(StrictModel):
    enabled: bool = True
    friday_close_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class SessionConfig(StrictModel):
    timezone: str = "UTC"
    allowed_days: tuple[str, ...]
    allowed_sessions: tuple[SessionWindow, ...]
    entry_profile: EntrySessionProfileConfig = EntrySessionProfileConfig()
    avoid_rollover: AvoidRolloverConfig
    close_before_weekend: WeekendCloseConfig


class ExecutionConfig(StrictModel):
    deviation_points: int = Field(default=30, ge=0)
    maximum_retries: int = Field(default=2, ge=0, le=5)
    retry_delay_seconds: float = Field(default=1, ge=0)
    reject_if_price_changed_points: int = Field(default=50, ge=0)


class BrokerConfig(StrictModel):
    magic_number: int = Field(default=26071701, gt=0)
    order_comment_prefix: str = Field(default="XAU_RULE_BOT", max_length=20)
    server_time_offset_hours: int = Field(default=0, ge=-14, le=14)


class PortfolioConfig(StrictModel):
    enabled: bool = False
    symbols: tuple[SupportedSymbol, ...] = ()

class ForexTradingConfig(StrictModel):
    enabled: bool = False
    symbols: tuple[SupportedSymbol, ...] = ("EURUSD", "GBPUSD", "USDJPY")
    max_open_positions: int = Field(default=7, ge=1)


class AdaptiveLearningConfig(StrictModel):
    enabled: bool = True
    lookback_days: int = Field(default=90, ge=1)
    wr_bucket_size: float = Field(default=5.0, gt=0, le=25)
    session_bucket_hours: int = Field(default=4, ge=1, le=24)
    raise_threshold_min_samples: int = Field(default=5, ge=1)
    raise_threshold_win_rate_below: float = Field(default=50.0, ge=0, le=100)
    threshold_penalty: float = Field(default=5.0, ge=0, le=30)
    block_min_samples: int = Field(default=10, ge=1)
    block_win_rate_below: float = Field(default=40.0, ge=0, le=100)
    block_if_net_pnl_negative: bool = True
    profit_factor_min_samples: int = Field(default=8, ge=1)
    block_profit_factor_below: float = Field(default=0.90, ge=0)
    raise_threshold_profit_factor_below: float = Field(default=1.15, ge=0)
    min_average_win_loss_ratio: float = Field(default=0.90, ge=0)
    drawdown_raise_min_samples: int = Field(default=4, ge=1)
    drawdown_pain_r: float = Field(default=0.8, ge=0)
    drawdown_penalty: float = Field(default=5.0, ge=0, le=30)
    addon_raise_min_samples: int = Field(default=3, ge=1)
    addon_loss_rate_below: float = Field(default=45.0, ge=0, le=100)
    addon_penalty: float = Field(default=7.5, ge=0, le=30)
    symbol_lock_min_samples: int = Field(default=6, ge=1)
    symbol_lock_loss_rate_below: float = Field(default=35.0, ge=0, le=100)
    maximum_adaptive_threshold: float = Field(default=85.0, ge=0, le=100)

class DataRetentionConfig(StrictModel):
    closed_trade_retention_days: int = Field(default=90, ge=1)
    rejected_signal_retention_days: int = Field(default=3, ge=1)
    indicator_snapshot_retention_days: int = Field(default=3, ge=1)
    auxiliary_file_retention_days: int = Field(default=2, ge=1)
    auxiliary_file_max_mb: int = Field(default=2, ge=1)
    backup_retention_days: int = Field(default=7, ge=1)
    log_file_max_mb: int = Field(default=20, ge=1)
    max_project_storage_mb: int = Field(default=3072, ge=256)
    cleanup_interval_seconds: int = Field(default=3600, ge=60)

class BacktestConfig(StrictModel):
    initial_equity: float = Field(default=10_000, gt=0)
    simulated_spread_points: float = Field(default=30, ge=0)
    slippage_points: float = Field(default=5, ge=0)
    commission_per_lot: float = Field(default=7, ge=0)


class TradingConfig(StrictModel):
    bot: BotConfig
    symbol: SymbolConfig
    timeframes: TimeframeConfig
    strategy: StrategyConfig
    fast_scalp: FastScalpConfig = FastScalpConfig()
    hard_trade: HardTradeConfig = HardTradeConfig()
    m15_quick_trade: M15QuickTradeConfig = M15QuickTradeConfig()
    recovery_mode: RecoveryModeConfig = RecoveryModeConfig()
    signal_scoring: SignalScoringConfig
    position_control: PositionControlConfig
    risk: RiskConfig
    stop_loss: StopLossConfig
    take_profit: TakeProfitConfig
    basket_take_profit: BasketTakeProfitConfig
    basket_stop_loss: BasketStopLossConfig
    position_revalidation: PositionRevalidationConfig = PositionRevalidationConfig()
    break_even: BreakEvenConfig
    trailing_stop: TrailingStopConfig
    partial_close: PartialCloseConfig
    profit_protection: ProfitProtectionConfig = ProfitProtectionConfig()
    spread_guard: SpreadGuardConfig
    daily_risk: DailyRiskConfig
    cooldown: CooldownConfig
    session: SessionConfig
    execution: ExecutionConfig
    broker: BrokerConfig
    portfolio: PortfolioConfig = PortfolioConfig()
    forex_trading: ForexTradingConfig = ForexTradingConfig()
    adaptive_learning: AdaptiveLearningConfig = AdaptiveLearningConfig()
    data_retention: DataRetentionConfig = DataRetentionConfig()
    backtest: BacktestConfig = BacktestConfig()


class AppSettings(StrictModel):
    database_url: str
    mt5_login: int | None = None
    mt5_password: str | None = None
    mt5_server: str | None = None
    mt5_terminal_path: str | None = None
    enable_live_trading: bool = False
    require_demo_account: bool = True
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = "INFO"
    broker_startup_enabled: bool = True
    auto_start_bot: bool = False
    config_path: Path


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_app_settings() -> AppSettings:
    root = Path(__file__).resolve().parents[2]
    config_path = Path(os.getenv("TRADING_CONFIG_PATH", root / "app/config/trading_config.yaml"))
    return AppSettings(
        database_url=os.getenv("DATABASE_URL", f"sqlite:///{root / 'data' / 'trading_bot.db'}"),
        mt5_login=int(os.environ["MT5_LOGIN"]) if os.getenv("MT5_LOGIN") else None,
        mt5_password=os.getenv("MT5_PASSWORD"),
        mt5_server=os.getenv("MT5_SERVER"),
        mt5_terminal_path=os.getenv("MT5_TERMINAL_PATH"),
        enable_live_trading=_env_bool("ENABLE_LIVE_TRADING"),
        require_demo_account=_env_bool("REQUIRE_DEMO_ACCOUNT", True),
        api_host=os.getenv("API_HOST", "127.0.0.1"),
        api_port=int(os.getenv("API_PORT", "8000")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        broker_startup_enabled=_env_bool("BROKER_STARTUP_ENABLED", True),
        auto_start_bot=_env_bool("AUTO_START_BOT", False),
        config_path=config_path,
    )


def load_trading_config(path: Path | None = None) -> TradingConfig:
    config_path = path or get_app_settings().config_path
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    mode_override = os.getenv("TRADING_MODE")
    if mode_override:
        raw.setdefault("bot", {})["mode"] = mode_override
    config = TradingConfig.model_validate(raw)
    if config.bot.mode is TradingMode.LIVE and not get_app_settings().enable_live_trading:
        raise ValueError("LIVE mode requires ENABLE_LIVE_TRADING=true")
    return config


def save_trading_config(config: TradingConfig, path: Path | None = None) -> None:
    config_path = path or get_app_settings().config_path
    payload = yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False, allow_unicode=True)
    config_path.write_text(payload, encoding="utf-8")


def config_fingerprint(config: TradingConfig) -> str:
    payload = json.dumps(config.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
