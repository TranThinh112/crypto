from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app.backtest.engine import BacktestEngine, BacktestResult, BacktestTrade, BasketRecord
from app.backtest.report import build_report, write_report
from app.config.settings import AppSettings, ForexTradingConfig, PortfolioConfig
from app.main import create_app
from app.models.trade import Trade
from app.runtime import Runtime


def test_read_only_api_and_confirm_schema(config, database, tmp_path):
    settings = AppSettings(database_url="sqlite:///:memory:", config_path=Path("app/config/trading_config.yaml"), broker_startup_enabled=False)
    runtime = Runtime(settings, config, database, tmp_path)
    application = create_app(runtime)
    assert {"/health", "/status", "/positions", "/baskets", "/trades", "/signals/latest", "/statistics/daily", "/config", "/config/forex-trading", "/bot/start", "/bot/stop", "/bot/pause-entry", "/bot/resume-entry", "/positions/close-all", "/baskets/{basket_id}/close"} <= set(application.openapi()["paths"])
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/status").json()["mode"] == "PAPER"
        assert client.get("/config").json()["symbol"]["base_symbol"] == "XAUUSD"
        assert client.get("/positions").json() == []
        assert client.post("/positions/close-all", json={"confirm": False, "reason": "test"}).status_code == 422
        assert client.post("/bot/start").status_code == 503

def test_forex_mode_filters_currency_pairs_until_enabled(config, database, tmp_path):
    settings = AppSettings(database_url="sqlite:///:memory:", config_path=Path("app/config/trading_config.yaml"), broker_startup_enabled=False)
    portfolio = PortfolioConfig(enabled=True, symbols=("BTCUSD", "XAUUSD", "EURUSD"))
    forex_off = config.model_copy(update={"portfolio": portfolio, "forex_trading": ForexTradingConfig(enabled=False)})
    runtime = Runtime(settings, forex_off, database, tmp_path)
    assert runtime._portfolio_bases() == ("BTCUSD", "XAUUSD")

    forex_on = forex_off.model_copy(update={"forex_trading": ForexTradingConfig(enabled=True, symbols=("EURUSD",))})
    runtime = Runtime(settings, forex_on, database, tmp_path)
    assert runtime._portfolio_bases() == ("BTCUSD", "XAUUSD", "EURUSD")


def test_forex_mode_keeps_open_trades_visible_when_disabled(config, database, tmp_path):
    settings = AppSettings(database_url="sqlite:///:memory:", config_path=Path("app/config/trading_config.yaml"), broker_startup_enabled=False)
    portfolio = PortfolioConfig(enabled=True, symbols=("BTCUSD", "XAUUSD"))
    forex_off = config.model_copy(update={"portfolio": portfolio, "forex_trading": ForexTradingConfig(enabled=False)})
    with database.transaction() as session:
        session.add(Trade(
            basket_id=None,
            broker_ticket=123456,
            idempotency_key="EURUSD_BUY_M5_1",
            symbol="EURUSD",
            side="BUY",
            state="OPEN",
            volume=0.01,
            initial_volume=0.01,
            entry_price=1.1,
            stop_loss=1.095,
            initial_stop_loss=1.095,
            take_profit=1.11,
            realized_profit=0.0,
            floating_profit=-0.2,
            estimated_win_rate=76.0,
            entry_number=1,
            initial_risk_amount=5.0,
            max_adverse_profit=0.0,
            max_favorable_profit=0.0,
            max_adverse_r=0.0,
            max_favorable_r=0.0,
            signal_hash="abc123",
            entry_candle_time=datetime.now(UTC),
            partial_levels_completed=[],
            break_even_applied=False,
            opened_at=datetime.now(UTC),
            closed_at=None,
            close_reason=None,
        ))
    runtime = Runtime(settings, forex_off, database, tmp_path)
    assert runtime._portfolio_bases() == ("BTCUSD", "XAUUSD", "EURUSD")


def test_weekend_entry_is_btc_only(config, database, tmp_path):
    settings = AppSettings(database_url="sqlite:///:memory:", config_path=Path("app/config/trading_config.yaml"), broker_startup_enabled=False, enable_live_trading=True)
    portfolio = PortfolioConfig(enabled=True, symbols=("BTCUSD", "XAUUSD"))
    forex_on = ForexTradingConfig(enabled=True, symbols=("EURUSD",))
    btc_session = config.session.model_copy(update={
        "allowed_days": ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"),
        "close_before_weekend": config.session.close_before_weekend.model_copy(update={"enabled": False}),
    })
    btc_config = config.model_copy(update={"session": btc_session})
    cfg = btc_config.model_copy(update={"portfolio": portfolio, "forex_trading": forex_on})
    runtime = Runtime(settings, cfg, database, tmp_path)

    btc = runtime._config_for_symbol("BTCUSD")
    gold = runtime._config_for_symbol("XAUUSD")
    forex = runtime._config_for_symbol("EURUSD")

    assert "SATURDAY" in btc.session.allowed_days
    assert "SUNDAY" in btc.session.allowed_days
    assert "SATURDAY" not in gold.session.allowed_days
    assert "SUNDAY" not in forex.session.allowed_days
    assert gold.session.close_before_weekend.enabled
    assert forex.session.close_before_weekend.enabled


def test_backtest_report_json_and_csv(tmp_path):
    now = datetime.now(UTC)
    trades = (
        BacktestTrade(1, 1, "BUY", .1, 2000, 2010, now, now + timedelta(hours=1), 100, 50, 2, 3600, "TAKE_PROFIT", 90),
        BacktestTrade(2, 2, "SELL", .1, 2010, 2015, now, now + timedelta(hours=2), -50, 50, -1, 7200, "STOP_LOSS", 85),
    )
    baskets = (BasketRecord(1, "BUY", now, now + timedelta(hours=1), 50, 100, "TAKE_PROFIT", 110, 10),)
    result = BacktestResult(trades, baskets, ((now, 10_000), (now + timedelta(hours=1), 10_100), (now + timedelta(hours=2), 10_050)), 3, 1)
    report = write_report(result, tmp_path)
    assert report["total_trades"] == 2 and report["net_profit"] == 50 and report["maximum_drawdown"] == 50
    assert (tmp_path / "report.json").exists() and (tmp_path / "trades.csv").exists() and (tmp_path / "monthly_performance.csv").exists()


def test_backtest_completes_with_next_bar_execution(config, spec):
    small_strategy = config.strategy.model_copy(update={"ema_fast": 3, "ema_mid": 5, "ema_slow": 8, "minimum_adx": 5})
    small = config.model_copy(update={"strategy": small_strategy})
    count = 1_050
    close = 1900 + np.linspace(0, 60, count) + np.sin(np.arange(count) / 9) * 3
    candles = pd.DataFrame({
        "time": pd.date_range("2026-01-05", periods=count, freq="5min", tz="UTC"),
        "open": close - .2, "high": close + 1, "low": close - 1,
        "close": close, "volume": 1000, "spread": 20,
    })
    result = BacktestEngine(small, spec).run(candles)
    assert len(result.equity_curve) >= 1_000
