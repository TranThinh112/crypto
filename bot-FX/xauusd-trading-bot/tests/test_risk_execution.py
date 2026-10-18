from __future__ import annotations

from datetime import UTC, datetime, timedelta
import re
from types import SimpleNamespace

import pytest

from app.broker.execution_service import ExecutionService, OrderIntent
from app.broker.mt5_client import MT5Client
from app.broker.paper_client import PaperBrokerClient
from app.risk.margin_guard import MarginGuard
from app.risk.position_sizing import PositionSizer
from app.risk.risk_manager import RiskManager
from app.utils.calculations import normalize_price, normalize_volume
from app.utils.enums import SignalSide
from app.utils.exceptions import BrokerConnectionError, OrderValidationError
from tests.conftest import FakeMarket


def plan_and_size(config, spec):
    plan = RiskManager(config.stop_loss, config.take_profit).plan(SignalSide.BUY, 2000.2, 3.0, 1998.0, 2004.0, spec)
    size = PositionSizer.calculate(10_000, config.risk.risk_per_entry_percent, plan.entry, plan.stop_loss, spec, config.risk.max_total_lot)
    return plan, size


def test_price_volume_normalization():
    assert normalize_price(1.23456, 3) == 1.235
    assert normalize_volume(0.089, 0.01, 1, 0.01) == 0.08
    assert normalize_volume(0.005, 0.01, 1, 0.01) == 0


def test_sl_tp_and_position_sizing(config, spec):
    plan, size = plan_and_size(config, spec)
    assert plan.stop_loss == 1997.1 and plan.take_profit == 2006.4
    assert plan.risk_reward == pytest.approx(2)
    assert size.volume == pytest.approx(0.08)
    invalid_spec = type(spec)(**{field: getattr(spec, field) for field in spec.__dataclass_fields__} | {"trade_tick_value": 0})
    with pytest.raises(OrderValidationError):
        PositionSizer.calculate(10_000, 0.25, 2000, 1999, invalid_spec, 1)


def test_margin_guard_rejects_insufficient(config, spec):
    market = FakeMarket(spec)
    market.margin = 9_000
    result = MarginGuard(market, config.risk).validate("BUY", "XAUUSD", 0.1, 2000, market.account())
    assert not result.passed


def test_execution_is_idempotent_and_has_server_stops(config, spec, database):
    market = FakeMarket(spec)
    paper = PaperBrokerClient(market)
    plan, size = plan_and_size(config, spec)
    service = ExecutionService(paper, database, config)
    intent = OrderIntent("XAUUSD", "unique-order-key", "signal", datetime.now(UTC), None, "basket", 1, plan, size, 3.0)
    first, second = service.submit(intent), service.submit(intent)
    assert first.success and second.duplicate
    positions = paper.positions("XAUUSD", config.broker.magic_number)
    assert len(positions) == 1 and positions[0].stop_loss > 0 and positions[0].take_profit > 0


def test_execution_allows_unbounded_total_lot_config(config, spec, database):
    free_config = config.model_copy(update={"risk": config.risk.model_copy(update={"max_total_lot": None})})
    market = FakeMarket(spec)
    paper = PaperBrokerClient(market)
    plan, size = plan_and_size(free_config, spec)
    service = ExecutionService(paper, database, free_config)
    result = service.submit(OrderIntent("XAUUSD", "unbounded-total-lot", "signal", datetime.now(UTC), None, "basket", 1, plan, size, 3.0))
    assert result.success


def test_broker_comment_uses_only_mt5_safe_characters(config, spec, database):
    service = ExecutionService(PaperBrokerClient(FakeMarket(spec)), database, config)
    comment = service._comment("54dfb3f3-1234", 1, "ab-cd|ef")
    assert len(comment) <= 31
    assert re.fullmatch(r"[A-Za-z0-9_]+", comment)


def test_live_mode_has_second_environment_gate(config, spec, database):
    live_config = config.model_copy(update={"bot": config.bot.model_copy(update={"mode": "LIVE"})})
    plan, size = plan_and_size(config, spec)
    result = ExecutionService(PaperBrokerClient(FakeMarket(spec)), database, live_config, live_enabled=False).submit(OrderIntent("XAUUSD", "live-gate", "signal", datetime.now(UTC), None, "basket", 1, plan, size, 3))
    assert not result.success and result.reason == "LIVE_TRADING_ENV_NOT_ENABLED"


def test_mt5_connection_error_is_wrapped():
    class Module:
        @staticmethod
        def initialize(**kwargs): return False
        @staticmethod
        def last_error(): return (1, "terminal unavailable")
    with pytest.raises(BrokerConnectionError):
        MT5Client(module=Module()).connect()


def test_mt5_server_time_offset_normalizes_tick_to_utc():
    expected = datetime(2026, 7, 17, 8, 45, tzinfo=UTC)
    server_wall_clock = expected + timedelta(hours=3)

    class Module:
        @staticmethod
        def symbol_info_tick(symbol):
            return SimpleNamespace(
                bid=3993.0,
                ask=3993.5,
                last=3993.2,
                time=int(server_wall_clock.timestamp()),
                time_msc=int(server_wall_clock.timestamp() * 1000),
            )

    tick = MT5Client(module=Module(), server_time_offset_hours=3).tick("GOLD")
    assert tick.time == expected
