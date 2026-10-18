from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Crypto Spot AI Bot"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    port: int = 8000

    mongodb_uri: str = ""
    mongodb_database: str = "crypto_spot_bot"

    openai_api_key: str = ""
    openai_model: str = "gpt-5.4-mini"
    ai_temperature: float = 0.2
    gpt_5_4_manager_api_key: str = ""
    gpt_5_4_manager_model: str = "gpt-5.4-mini"
    gpt_5_4_manager_enabled: bool = True
    gpt_crypto_api_key: str = ""
    gpt_crypto_model: str = "gpt-5.4-mini"
    gpt_crypto_enabled: bool = True
    gpt_fork_api_key: str = ""
    gpt_fork_model: str = "gpt-5.4-mini"
    gpt_fork_enabled: bool = True

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_notify_scans: bool = True
    telegram_message_thread_id: str = ""
    telegram_approval_required: bool = True
    telegram_top_scan_report_enabled: bool = True

    user_total_budget_usd: float = 100.0
    live_trading_enabled: bool = False
    paper_trading_enabled: bool = True
    live_trading_confirm: str = ""
    max_live_trade_usd: float = 25.0
    min_new_trade_capital_usdt: float = 1.0
    spot_only_trading: bool = True
    quote_currency: str = "USDT"
    market_symbols: str = "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT"
    market_scan_expand_universe_enabled: bool = True
    market_scan_universe_max_symbols: int = 200
    market_scan_shortlist_ttl_hours: int = 12
    shortlist_min_observations_for_trade: int = 2
    shortlist_min_age_minutes_for_trade: int = 30
    watchlist_care_enabled: bool = True
    watchlist_care_interval_seconds: int = 900
    auto_scan_enabled: bool = True
    scan_interval_seconds: int = 300
    signal_trend_threshold: float = 0.65
    signal_liquidity_threshold: float = 0.70
    signal_max_volatility: float = 0.80
    market_regime_enabled: bool = True
    market_regime_symbols: str = "BTCUSDT,ETHUSDT"
    market_regime_min_trend: float = 0.45
    market_regime_min_liquidity: float = 0.65
    anti_pump_max_24h_change_pct: float = 6.0
    anti_pump_near_resistance_pct: float = -1.5
    buy_zone_support_buffer_pct: float = 3.0
    buy_zone_breakout_buffer_pct: float = 2.0
    risk_per_trade_pct_of_budget: float = 1.0
    min_proposal_amount_usd: float = 5.0
    store_all_scans: bool = False
    scan_heartbeat_store_interval: int = 12
    market_scan_ttl_days: int = 30
    held_asset_summary_enabled: bool = True
    held_asset_summary_interval_seconds: int = 3600
    held_asset_strong_move_pct: float = 5.0
    held_asset_take_profit_partial_pct: float = 8.0
    held_asset_take_profit_full_pct: float = 25.0
    held_asset_high_risk_loss_pct: float = -20.0
    held_asset_exit_loss_pct: float = -35.0
    position_ai_min_confidence: float = 0.65
    position_max_asset_weight_pct: float = 60.0
    position_add_cooldown_hours: int = 24
    position_partial_take_profit_pct: float = 35.0
    position_full_take_profit_pct: float = 100.0
    position_execution_requires_approval: bool = True

    exchange_name: str = "okx"
    okx_api_key: str = ""
    okx_secret: str = ""
    okx_passphrase: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
