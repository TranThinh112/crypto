from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest
from sqlalchemy import select

from app.broker.mt5_client import BrokerPosition, BrokerResult
from app.broker.execution_service import ExecutionService
from app.broker.paper_client import PaperBrokerClient
from app.models.basket import Basket
from app.models.trade import ExecutionRequest, Trade, TradeEvent
from app.positions.basket_manager import BasketManager, BasketMetrics
from app.positions.break_even_manager import BreakEvenManager
from app.positions.partial_close_manager import PartialCloseManager
from app.positions.position_revalidator import PositionRevalidator
from app.positions.trailing_stop_manager import TrailingStopManager
from app.strategy.signal_engine import SignalEvaluation
from app.strategy.trend_detector import TimeframeTrend, TrendAssessment
from app.utils.calculations import weighted_average_price
from app.utils.enums import BasketState, BasketStopLossMode, CloseReason, SignalSide, TradeState, TrendDirection
from tests.conftest import FakeMarket


def position(price: float = 2003.5, volume: float = 0.08) -> BrokerPosition:
    return BrokerPosition(1, "XAUUSD", "BUY", volume, 2000.2, price, 1997.1, 2006.4, 20, 26071701, "test", datetime.now(UTC))


def test_weighted_average_and_basket_pnl():
    values = [position(volume=0.08), BrokerPosition(2, "XAUUSD", "BUY", 0.02, 2010, 2011, 2005, 2020, 5, 26071701, "test", datetime.now(UTC))]
    metrics = BasketManager.metrics(values, 3)
    assert metrics.weighted_average_entry == pytest.approx(weighted_average_price([(2000.2, 0.08), (2010, 0.02)]))
    assert metrics.combined_profit == 28


def test_basket_take_profit_and_any_stop_threshold(config):
    manager = object.__new__(BasketManager)
    manager.config = config
    take = manager.exit_decision(BasketMetrics(1, .1, 2000, 16, 0, 16), 10, 10_000)
    stop = manager.exit_decision(BasketMetrics(1, .1, 2000, -21, 0, -21), 10, 10_000)
    assert take.reason is CloseReason.TAKE_PROFIT
    assert stop.reason is CloseReason.STOP_LOSS


def test_balanced_basket_stop_loss_uses_daily_loss_floor(config):
    manager = object.__new__(BasketManager)
    manager.config = config.model_copy(update={
        "basket_stop_loss": config.basket_stop_loss.model_copy(update={
            "mode": BasketStopLossMode.BALANCED_DAILY,
            "balanced_daily_loss_ratio": 0.2,
            "balanced_minimum_loss_usd": 3,
        }),
        "daily_risk": config.daily_risk.model_copy(update={"max_daily_loss_usd": 10}),
    })
    hit = manager.exit_decision(BasketMetrics(1, .1, 2000, -3.1, 0, -3.1), 10, 10_000)
    safe = manager.exit_decision(BasketMetrics(1, .1, 2000, -2.9, 0, -2.9), 10, 10_000)
    assert hit.reason is CloseReason.STOP_LOSS
    assert safe.reason is None


def test_basket_stop_loss_uses_stricter_hard_cap(config):
    manager = object.__new__(BasketManager)
    manager.config = config.model_copy(update={
        "basket_stop_loss": config.basket_stop_loss.model_copy(update={
            "mode": BasketStopLossMode.BALANCED_DAILY,
            "balanced_daily_loss_ratio": 0.5,
            "balanced_minimum_loss_usd": 20,
            "hard_max_loss_usd": 8,
        }),
        "daily_risk": config.daily_risk.model_copy(update={"max_daily_loss_usd": 100}),
    })
    assert manager.basket_stop_loss_threshold(10_000) == pytest.approx(8)
    hit = manager.exit_decision(BasketMetrics(1, .1, 2000, -8.01, 0, -8.01), 10, 10_000)
    safe = manager.exit_decision(BasketMetrics(1, .1, 2000, -7.99, 0, -7.99), 10, 10_000)
    assert hit.reason is CloseReason.STOP_LOSS
    assert safe.reason is None

def test_fast_only_basket_uses_fast_take_profit(config, spec, database):
    paper = PaperBrokerClient(FakeMarket(spec))
    manager = BasketManager(database, paper, ExecutionService(paper, database, config), config, "XAUUSD", spec)
    basket = manager.ensure_active("BUY", 10)
    with database.transaction() as session:
        session.add(Trade(
            basket_id=basket.id,
            broker_ticket=123,
            idempotency_key="XAUUSD_BUY_M1_123_fast",
            symbol="XAUUSD",
            side="BUY",
            state=TradeState.OPEN.value,
            volume=0.01,
            initial_volume=0.01,
            entry_price=2000,
            stop_loss=1998,
            initial_stop_loss=1998,
            take_profit=2004,
            realized_profit=0,
            floating_profit=0,
            signal_hash="fast",
            entry_candle_time=datetime.now(UTC),
            opened_at=datetime.now(UTC),
        ))
    fast_hit = manager.exit_decision(BasketMetrics(1, .1, 2000, 2.1, 0, 2.1), 10, 10_000, basket.external_id)
    assert fast_hit.reason is CloseReason.TAKE_PROFIT
    assert fast_hit.threshold == pytest.approx(config.basket_take_profit.fast_target_fixed_usd)


def test_failed_basket_close_does_not_commit_final_close_reason(config, spec, database, monkeypatch):
    paper = PaperBrokerClient(FakeMarket(spec))
    manager = BasketManager(database, paper, ExecutionService(paper, database, config), config, "XAUUSD", spec)
    basket = manager.ensure_active("BUY", 10)
    now = datetime.now(UTC)
    paper.restore_position(BrokerPosition(123, "XAUUSD", "BUY", 0.01, 2000, 2001, 1998, 2004, 1, config.broker.magic_number, "test", now))
    with database.transaction() as session:
        session.add(Trade(
            basket_id=basket.id,
            broker_ticket=123,
            idempotency_key="close-fail",
            symbol="XAUUSD",
            side="BUY",
            state=TradeState.OPEN.value,
            volume=0.01,
            initial_volume=0.01,
            entry_price=2000,
            stop_loss=1998,
            initial_stop_loss=1998,
            take_profit=2004,
            realized_profit=0,
            floating_profit=1,
            signal_hash="close-fail",
            entry_candle_time=now,
            opened_at=now,
        ))
    monkeypatch.setattr(
        paper,
        "close_position",
        lambda position, volume, deviation_points, comment: BrokerResult(False, 10036, None, None, None, None, "forced failure", {}),
    )

    assert manager.close_basket(basket.external_id, CloseReason.STOP_LOSS) is False
    with database.transaction() as session:
        stored = session.get(Basket, basket.id)
        assert stored.status == BasketState.CLOSE_FAILED.value
        assert stored.close_reason is None

def test_empty_unconfirmed_basket_is_discarded_without_exit_result(config, spec, database):
    paper = PaperBrokerClient(FakeMarket(spec))
    manager = BasketManager(database, paper, ExecutionService(paper, database, config), config, "XAUUSD", spec)
    basket = manager.ensure_active("BUY", 20)
    assert manager.finalize_empty(basket.external_id, CloseReason.TAKE_PROFIT) is False
    with database.transaction() as session:
        stored = session.get(Basket, basket.id)
        assert stored.status == BasketState.CLOSED.value
        assert stored.close_reason == "NO_CONFIRMED_BROKER_POSITION"


def test_missing_broker_position_estimates_closed_pnl_from_last_floating(config, spec, database):
    paper = PaperBrokerClient(FakeMarket(spec))
    manager = BasketManager(database, paper, ExecutionService(paper, database, config), config, "XAUUSD", spec)
    basket = manager.ensure_active("SELL", 10)
    with database.transaction() as session:
        session.add(Trade(
            basket_id=basket.id,
            broker_ticket=12345,
            idempotency_key="estimated-exit",
            symbol="XAUUSD",
            side="SELL",
            state=TradeState.OPEN.value,
            volume=0.01,
            initial_volume=0.01,
            entry_price=2000,
            stop_loss=2001,
            initial_stop_loss=2001,
            take_profit=1998,
            realized_profit=0,
            floating_profit=-3.4,
            signal_hash="estimate",
            entry_candle_time=datetime.now(UTC),
            opened_at=datetime.now(UTC),
        ))
    metrics = manager.synchronize(basket.external_id)
    assert metrics.realized_profit == pytest.approx(-3.4)
    with database.transaction() as session:
        trade = session.scalar(select(Trade).where(Trade.idempotency_key == "estimated-exit"))
        event = session.scalar(select(TradeEvent).where(TradeEvent.trade_id == trade.id, TradeEvent.event_type == "BROKER_EXIT_ESTIMATED"))
        assert trade.state == TradeState.CLOSED.value
        assert trade.realized_profit == pytest.approx(-3.4)
        assert event.details["monetary"] == pytest.approx(-3.4)


def test_opposite_side_baskets_are_separate(config, spec, database):
    config = config.model_copy(update={"position_control": config.position_control.model_copy(update={"allow_opposite_positions": True})})
    paper = PaperBrokerClient(FakeMarket(spec))
    manager = BasketManager(database, paper, ExecutionService(paper, database, config), config, "XAUUSD", spec)
    buy = manager.ensure_active("BUY", 10)
    sell = manager.ensure_active("SELL", 10)
    assert buy.external_id != sell.external_id
    assert buy.direction == "BUY"
    assert sell.direction == "SELL"


def test_close_basket_only_closes_tracked_side_when_hedged(config, spec, database):
    config = config.model_copy(update={"position_control": config.position_control.model_copy(update={"allow_opposite_positions": True})})
    paper = PaperBrokerClient(FakeMarket(spec))
    manager = BasketManager(database, paper, ExecutionService(paper, database, config), config, "XAUUSD", spec)
    buy = manager.ensure_active("BUY", 10)
    sell = manager.ensure_active("SELL", 10)
    now = datetime.now(UTC)
    buy_position = BrokerPosition(101, "XAUUSD", "BUY", 0.01, 2000.2, 2000.0, 1999.0, 2002.0, 0, config.broker.magic_number, "buy", now)
    sell_position = BrokerPosition(202, "XAUUSD", "SELL", 0.01, 2000.0, 2000.2, 2001.0, 1998.0, 0, config.broker.magic_number, "sell", now)
    paper.restore_position(buy_position)
    paper.restore_position(sell_position)
    with database.transaction() as session:
        session.add(Trade(
            basket_id=buy.id,
            broker_ticket=buy_position.ticket,
            idempotency_key="buy-hedge",
            symbol="XAUUSD",
            side="BUY",
            state=TradeState.OPEN.value,
            volume=0.01,
            initial_volume=0.01,
            entry_price=buy_position.entry_price,
            stop_loss=buy_position.stop_loss,
            initial_stop_loss=buy_position.stop_loss,
            take_profit=buy_position.take_profit,
            realized_profit=0,
            floating_profit=0,
            signal_hash="buy",
            entry_candle_time=now,
            opened_at=now,
        ))
        session.add(Trade(
            basket_id=sell.id,
            broker_ticket=sell_position.ticket,
            idempotency_key="sell-hedge",
            symbol="XAUUSD",
            side="SELL",
            state=TradeState.OPEN.value,
            volume=0.01,
            initial_volume=0.01,
            entry_price=sell_position.entry_price,
            stop_loss=sell_position.stop_loss,
            initial_stop_loss=sell_position.stop_loss,
            take_profit=sell_position.take_profit,
            realized_profit=0,
            floating_profit=0,
            signal_hash="sell",
            entry_candle_time=now,
            opened_at=now,
        ))

    assert manager.close_basket(buy.external_id, CloseReason.MANUAL)
    remaining = paper.positions("XAUUSD", config.broker.magic_number)
    assert [item.ticket for item in remaining] == [sell_position.ticket]


def test_close_basket_estimates_realized_pnl_when_history_lags(config, spec, database):
    class LaggingHistoryBroker(FakeMarket):
        def __init__(self):
            super().__init__(spec, bid=2002.0, ask=2002.2)
            self.open_positions: dict[int, BrokerPosition] = {}

        def positions(self, symbol: str, magic: int) -> list[BrokerPosition]:
            return [item for item in self.open_positions.values() if item.symbol == symbol and item.magic == magic]

        def close_position(self, position: BrokerPosition, volume: float, deviation_points: int, comment: str) -> BrokerResult:
            self.open_positions.pop(position.ticket, None)
            return BrokerResult(True, 10009, position.ticket, 999, self.bid, volume, "closed", {})

    broker = LaggingHistoryBroker()
    manager = BasketManager(database, broker, ExecutionService(broker, database, config), config, "XAUUSD", spec)
    basket = manager.ensure_active("BUY", 10)
    now = datetime.now(UTC)
    open_position = BrokerPosition(303, "XAUUSD", "BUY", 0.01, 2000.0, 2002.0, 1999.0, 2004.0, 2.0, config.broker.magic_number, "buy", now)
    broker.open_positions[open_position.ticket] = open_position
    with database.transaction() as session:
        session.add(Trade(
            basket_id=basket.id,
            broker_ticket=open_position.ticket,
            idempotency_key="history-lags-close",
            symbol="XAUUSD",
            side="BUY",
            state=TradeState.OPEN.value,
            volume=open_position.volume,
            initial_volume=open_position.volume,
            entry_price=open_position.entry_price,
            stop_loss=open_position.stop_loss,
            initial_stop_loss=open_position.stop_loss,
            take_profit=open_position.take_profit,
            realized_profit=0,
            floating_profit=open_position.profit,
            signal_hash="lag",
            entry_candle_time=now,
            opened_at=now,
        ))

    assert manager.close_basket(basket.external_id, CloseReason.TAKE_PROFIT)
    with database.transaction() as session:
        stored_trade = session.scalar(select(Trade).where(Trade.idempotency_key == "history-lags-close"))
        stored_basket = session.get(Basket, basket.id)
        event = session.scalar(select(TradeEvent).where(TradeEvent.trade_id == stored_trade.id, TradeEvent.event_type == "BROKER_EXIT_ESTIMATED"))
        assert stored_trade.realized_profit == pytest.approx(2.0)
        assert stored_trade.floating_profit == pytest.approx(0.0)
        assert stored_basket.total_realized_profit == pytest.approx(2.0)
        assert event.details["source"] == "management_close_result"


def test_close_basket_retries_with_new_audit_after_previous_failure(config, spec, database):
    class FlakyCloseBroker(FakeMarket):
        def __init__(self):
            super().__init__(spec, bid=2002.0, ask=2002.2)
            self.open_positions: dict[int, BrokerPosition] = {}
            self.close_calls = 0

        def positions(self, symbol: str, magic: int) -> list[BrokerPosition]:
            return [item for item in self.open_positions.values() if item.symbol == symbol and item.magic == magic]

        def close_position(self, position: BrokerPosition, volume: float, deviation_points: int, comment: str) -> BrokerResult:
            self.close_calls += 1
            if self.close_calls == 1:
                return BrokerResult(False, 10031, None, None, 0.0, 0.0, "Request rejected due to absence of network connection", {"retcode": 10031})
            self.open_positions.pop(position.ticket, None)
            return BrokerResult(True, 10009, position.ticket, 999, self.bid, volume, "closed", {})

    config = config.model_copy(update={"execution": config.execution.model_copy(update={"maximum_retries": 0})})
    broker = FlakyCloseBroker()
    manager = BasketManager(database, broker, ExecutionService(broker, database, config), config, "XAUUSD", spec)
    basket = manager.ensure_active("BUY", 10)
    now = datetime.now(UTC)
    open_position = BrokerPosition(404, "XAUUSD", "BUY", 0.01, 2000.0, 2002.0, 1999.0, 2004.0, 2.0, config.broker.magic_number, "buy", now)
    broker.open_positions[open_position.ticket] = open_position
    with database.transaction() as session:
        session.add(Trade(
            basket_id=basket.id,
            broker_ticket=open_position.ticket,
            idempotency_key="flaky-close",
            symbol="XAUUSD",
            side="BUY",
            state=TradeState.OPEN.value,
            volume=open_position.volume,
            initial_volume=open_position.volume,
            entry_price=open_position.entry_price,
            stop_loss=open_position.stop_loss,
            initial_stop_loss=open_position.stop_loss,
            take_profit=open_position.take_profit,
            realized_profit=0,
            floating_profit=open_position.profit,
            signal_hash="flaky",
            entry_candle_time=now,
            opened_at=now,
        ))

    assert not manager.close_basket(basket.external_id, CloseReason.TAKE_PROFIT)
    assert manager.close_basket(basket.external_id, CloseReason.TAKE_PROFIT)
    assert broker.close_calls == 2
    with database.transaction() as session:
        requests = list(session.scalars(select(ExecutionRequest).where(ExecutionRequest.action == "CLOSE").order_by(ExecutionRequest.id)))
        stored_basket = session.get(Basket, basket.id)
        assert [item.status for item in requests] == ["FAILED", "SUCCESS"]
        assert [item.idempotency_key.rsplit(":", 1)[-1] for item in requests] == ["1", "2"]
        assert stored_basket.status == BasketState.CLOSED.value


def test_break_even_never_increases_risk(config, spec):
    manager = BreakEvenManager(config.break_even)
    assert manager.evaluate(position(), 1997.1, spec, False).new_stop == 2000.4
    already_safer = BrokerPosition(**{field: getattr(position(), field) for field in position().__dataclass_fields__} | {"stop_loss": 2001})
    assert not manager.evaluate(already_safer, 1997.1, spec, False).should_update


def test_trailing_requires_activation_and_update_step(config, spec):
    manager = TrailingStopManager(config.trailing_stop)
    assert manager.evaluate(position(), 1997.1, 1.0, spec).new_stop == 2002.0
    assert not manager.evaluate(position(2001), 1997.1, 1.0, spec).should_update


def test_partial_close_is_once_and_volume_safe(config, spec):
    manager = PartialCloseManager(config.partial_close)
    first = manager.evaluate(position(), 0.08, 1997.1, (), spec)
    assert first.should_close and first.volume == pytest.approx(0.03) and first.trigger_r == 1
    second = manager.evaluate(position(2005.0), 0.08, 1997.1, (1.0,), spec)
    assert second.should_close and second.trigger_r == 1.5


def test_revalidation_closes_invalidated_long_on_strong_sell_rotation(config):
    bearish = TimeframeTrend("H4", TrendDirection.BEARISH, 0, 6, ())
    trend = TrendAssessment(TrendDirection.BEARISH, bearish, TimeframeTrend("H1", TrendDirection.BEARISH, 0, 6, ()))
    m15 = pd.DataFrame([{
        "close": 90.0, "ema20": 94.0, "ema50": 100.0, "rsi": 35.0,
        "last_swing_low": 85.0, "last_swing_high": 110.0,
    }])
    m5 = pd.DataFrame([{"macd_hist": 2.0}, {"macd_hist": 1.0}])
    rotation = SignalEvaluation(SignalSide.SELL, 65, "TRADE", None, (), "sell", {})
    decision = PositionRevalidator(config.position_revalidation, config.strategy).evaluate(position(), trend, m15, m5, rotation)
    assert decision.should_close
    assert decision.keep_score < config.position_revalidation.minimum_keep_score


def test_revalidation_keeps_long_with_recovery_evidence(config):
    bearish = TimeframeTrend("H4", TrendDirection.BEARISH, 0, 6, ())
    trend = TrendAssessment(TrendDirection.BEARISH, bearish, TimeframeTrend("H1", TrendDirection.BEARISH, 0, 6, ()))
    m15 = pd.DataFrame([{
        "close": 105.0, "ema20": 103.0, "ema50": 100.0, "rsi": 55.0,
        "last_swing_low": 95.0, "last_swing_high": 110.0,
    }])
    m5 = pd.DataFrame([{"macd_hist": 1.0}, {"macd_hist": 2.0}])
    rotation = SignalEvaluation(SignalSide.SELL, 65, "TRADE", None, (), "sell", {})
    decision = PositionRevalidator(config.position_revalidation, config.strategy).evaluate(position(), trend, m15, m5, rotation)
    assert not decision.should_close
    assert decision.keep_score >= config.position_revalidation.minimum_keep_score
