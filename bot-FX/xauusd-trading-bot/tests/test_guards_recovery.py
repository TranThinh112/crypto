from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.api.routes_status import _stale_care_symbols
from app.broker.execution_service import ExecutionService, OrderIntent
from app.broker.mt5_client import BrokerPosition, TickSnapshot
from app.broker.paper_client import PaperBrokerClient
from app.config.settings import EntrySessionProfileConfig, ForexTradingConfig, SessionWindow
from app.guards.cooldown_guard import CooldownGuard
from app.guards.session_guard import SessionGuard
from app.guards.spread_guard import SpreadGuard
from app.models.basket import Basket
from app.models.event_log import IndicatorSnapshot, SignalDecision
from app.models.trade import ExecutionRequest, Trade, TradeEvent
from app.risk.daily_risk_guard import DailyRiskGuard, DailyRiskSnapshot
from app.risk.position_sizing import PositionSizer
from app.risk.risk_manager import RiskManager
from app.services.recovery_service import RecoveryService
from app.services.trading_orchestrator import TradingOrchestrator
from app.strategy.signal_engine import SignalEvaluation
from app.strategy.trend_detector import RuleResult
from app.utils.enums import BasketState, CloseReason, SignalSide, TradeState
from tests.conftest import FakeMarket

class ForexPositionMarket(FakeMarket):
    def __init__(self, spec, positions_by_symbol):
        super().__init__(spec)
        self.positions_by_symbol = positions_by_symbol

    def positions(self, symbol: str, magic: int) -> list[BrokerPosition]:
        return self.positions_by_symbol.get(symbol, [])


def test_spread_session_daily_and_cooldown_guards(config, spec, database):
    monday = datetime(2026, 7, 13, 8, tzinfo=UTC)
    assert SessionGuard(config.session).evaluate(monday)[0]
    assert not SessionGuard(config.session).evaluate(datetime(2026, 7, 12, 8, tzinfo=UTC))[0]
    tick = TickSnapshot("XAUUSD", 2000, 2000.2, 2000.1, monday)
    assert SpreadGuard(config.spread_guard).evaluate(tick, spec.point, 3).passed
    assert not DailyRiskGuard(config.daily_risk).evaluate(DailyRiskSnapshot(10_000, -201, 0, 0))[0]
    first = CooldownGuard(database, config.cooldown, "XAUUSD")
    first.activate(CloseReason.STOP_LOSS, "basket", monday)
    assert CooldownGuard(database, config.cooldown, "XAUUSD").active(monday + timedelta(minutes=1)) is not None
    assert CooldownGuard(database, config.cooldown, "XAUUSD").active(monday + timedelta(minutes=121)) is None


def test_daily_risk_supports_fixed_usd_limits(config):
    daily = config.daily_risk.model_copy(update={"max_daily_loss_usd": 8, "daily_profit_target_usd": 15})
    guard = DailyRiskGuard(daily)
    assert not guard.evaluate(DailyRiskSnapshot(10_000, -8, 0, 0))[0]
    assert not guard.evaluate(DailyRiskSnapshot(10_000, 10, 5, 0))[0]
    assert guard.evaluate(DailyRiskSnapshot(10_000, 7, 7.99, 0))[0]


def test_daily_threshold_rules_map_to_basket_close_reasons():
    loss = (RuleResult(False, "DAILY_LOSS_LIMIT", {"limit": -8}),)
    profit = (RuleResult(False, "DAILY_PROFIT_TARGET", {"target": 15}),)
    assert TradingOrchestrator._daily_close_trigger(loss) == (CloseReason.STOP_LOSS, -8)
    assert TradingOrchestrator._daily_close_trigger(profit) == (CloseReason.TAKE_PROFIT, 15)


def test_entry_session_profile_reduces_entries_outside_active_windows(config):
    profile = EntrySessionProfileConfig(
        enabled=True,
        active_sessions=(SessionWindow(start="07:00", end="21:00"),),
        quiet_minimum_signal_score=80,
    )
    session_config = config.session.model_copy(update={
        "allowed_days": ("MONDAY",),
        "allowed_sessions": (SessionWindow(start="00:00", end="23:59"),),
        "entry_profile": profile,
    })
    guard = SessionGuard(session_config)
    assert guard.evaluate(datetime(2026, 7, 13, 23, tzinfo=UTC))[0]
    assert guard.entry_profile_rule(datetime(2026, 7, 13, 12, tzinfo=UTC), 60).passed
    assert not guard.entry_profile_rule(datetime(2026, 7, 13, 23, tzinfo=UTC), 70).passed
    assert guard.entry_profile_rule(datetime(2026, 7, 13, 23, tzinfo=UTC), 85).passed


def test_restart_reconciliation_restores_paper_state(config, spec, database):
    market = FakeMarket(spec)
    paper_before = PaperBrokerClient(market)
    with database.transaction() as session:
        basket = Basket(external_id="restart-basket", symbol="XAUUSD", direction="BUY", status=BasketState.ACTIVE.value, opened_at=datetime.now(UTC), initial_risk_amount=20)
        session.add(basket); session.flush(); basket_id = basket.id
    plan = RiskManager(config.stop_loss, config.take_profit).plan(SignalSide.BUY, 2000.2, 3, 1998, 2004, spec)
    size = PositionSizer.calculate(10_000, .25, plan.entry, plan.stop_loss, spec, .1)
    outcome = ExecutionService(paper_before, database, config).submit(OrderIntent("XAUUSD", "restart-key", "hash", datetime.now(UTC), basket_id, "restart-basket", 1, plan, size, 3))
    assert outcome.success
    paper_after = PaperBrokerClient(FakeMarket(spec))
    result = RecoveryService(database, paper_after, config, "XAUUSD", spec).reconcile()
    assert result.consistent and result.restored_paper_positions == 1
    assert len(paper_after.positions("XAUUSD", config.broker.magic_number)) == 1


def test_reconciliation_pauses_for_untracked_position(config, spec, database):
    paper = PaperBrokerClient(FakeMarket(spec))
    paper.restore_position(BrokerPosition(42, "XAUUSD", "BUY", .01, 2000, 2000, 1990, 2020, 0, config.broker.magic_number, "unknown", datetime.now(UTC)))
    result = RecoveryService(database, paper, config, "XAUUSD", spec).reconcile()
    assert not result.consistent and result.missing_in_database == (42,)

def test_calculated_setup_win_rate_gate_passes_current_setup_above_50(config, spec, database):
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), config, "XAUUSD", spec, False, Path("."), ("XAUUSD",))
    evaluation = SignalEvaluation(SignalSide.BUY, 72, "TRADE", None, (), "signal-hash", {})
    rule = orchestrator._calculated_setup_win_rate_rule(evaluation)
    assert rule.passed
    assert rule.reason_code == "CALCULATED_SETUP_WIN_RATE_GATE"
    assert rule.details["win_rate"] == pytest.approx(57.4)
    assert rule.details["threshold"] == 50.0
    assert rule.details["source"] == "CURRENT_SETUP_RULE_SCORE"

def test_calculated_setup_win_rate_gate_rejects_current_setup_at_or_below_50(config, spec, database):
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), config, "XAUUSD", spec, False, Path("."), ("XAUUSD",))
    evaluation = SignalEvaluation(SignalSide.SELL, 40, "TRADE", None, (), "signal-hash", {})
    rule = orchestrator._calculated_setup_win_rate_rule(evaluation)
    assert not rule.passed
    assert rule.reason_code == "CALCULATED_SETUP_WIN_RATE_GATE"
    assert rule.details["win_rate"] == pytest.approx(43.0)

def test_calculated_setup_win_rate_can_clear_recovery_hard_for_high_quality_setup(config, spec, database):
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), config, "XAUUSD", spec, False, Path("."), ("XAUUSD",))
    rules = (
        RuleResult(True, "H4_TREND_ALIGNMENT", {}),
        RuleResult(True, "H1_TREND_ALIGNMENT", {}),
        RuleResult(True, "M15_EMA_ALIGNMENT", {}),
        RuleResult(True, "MARKET_STRUCTURE", {}),
        RuleResult(True, "M15_PULLBACK_QUALITY", {}),
        RuleResult(True, "M5_CANDLE_CONFIRMATION", {}),
        RuleResult(True, "M5_MACD_CONFIRMATION", {}),
        RuleResult(True, "M15_RSI_CONFIRMATION", {}),
        RuleResult(True, "M15_ADX_STRENGTH", {}),
        RuleResult(True, "RISK_REWARD_QUALITY", {}),
    )
    evaluation = SignalEvaluation(SignalSide.BUY, 95, "TRADE", None, rules, "signal-hash", {"rsi": 55})

    rule = orchestrator._calculated_setup_win_rate_rule(evaluation, threshold=75)

    assert rule.passed
    assert 75 <= rule.details["win_rate"] <= 85

def test_btc_weekend_relaxation_only_applies_on_weekends(config, spec, database):
    hard_trade = config.hard_trade.model_copy(update={
        "enabled": True,
        "minimum_setup_win_rate": 70.0,
        "m5_minimum_setup_win_rate": 80.0,
        "btc_weekend_relaxation_enabled": True,
        "btc_weekend_signal_score_discount": 5,
        "btc_weekend_setup_win_rate_discount": 5.0,
        "btc_weekend_max_atr_multiplier_discount": 1.0,
    })
    stop_loss = config.stop_loss.model_copy(update={"maximum_atr_multiplier": 7.5})
    btc_config = config.model_copy(update={
        "symbol": config.symbol.model_copy(update={"base_symbol": "BTCUSD"}),
        "hard_trade": hard_trade,
        "stop_loss": stop_loss,
    })
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), btc_config, "BTCUSD", spec, False, Path("."), ("BTCUSD",))

    saturday = datetime(2026, 7, 25, 8, tzinfo=UTC)
    monday = datetime(2026, 7, 27, 8, tzinfo=UTC)

    assert orchestrator._effective_setup_win_rate_threshold(saturday, "M15") == 65.0
    assert orchestrator._effective_setup_win_rate_threshold(saturday, "M5") == 75.0
    assert orchestrator._weekend_btc_signal_engine(saturday).strategy.minimum_signal_score == config.strategy.minimum_signal_score - 5
    assert orchestrator._weekend_btc_max_atr_multiplier(saturday) == 6.5

    assert orchestrator._effective_setup_win_rate_threshold(monday, "M15") == 70.0
    assert orchestrator._weekend_btc_signal_engine(monday) is orchestrator.signal_engine
    assert orchestrator._weekend_btc_max_atr_multiplier(monday) is None

def _add_closed_learning_trade(database, *, symbol="XAUUSD", side="BUY", timeframe="M15", wr=60.0, pnl=-1.0, days_ago=1, entry_number=1, max_adverse_r=0.0):
    now = datetime.now(UTC)
    with database.transaction() as session:
        trade = Trade(
            basket_id=None,
            broker_ticket=None,
            idempotency_key=f"{symbol}_{side}_{timeframe}_{int(now.timestamp())}_{session.query(Trade).count()}",
            symbol=symbol,
            side=side,
            state=TradeState.CLOSED.value,
            volume=0,
            initial_volume=0.01,
            entry_price=2000,
            stop_loss=1990,
            initial_stop_loss=1990,
            take_profit=2020,
            realized_profit=pnl,
            floating_profit=0,
            estimated_win_rate=wr,
            entry_number=entry_number,
            initial_risk_amount=2.0,
            max_adverse_profit=-2.0 * max_adverse_r,
            max_favorable_profit=max(0.0, pnl),
            max_adverse_r=max_adverse_r,
            max_favorable_r=max(0.0, pnl) / 2.0,
            signal_hash="learning",
            entry_candle_time=now - timedelta(days=days_ago),
            opened_at=now - timedelta(days=days_ago),
            closed_at=now - timedelta(days=days_ago),
            close_reason="TAKE_PROFIT" if pnl > 0 else "STOP_LOSS",
        )
        session.add(trade)

def test_adaptive_learning_disabled_keeps_base_threshold(config, spec, database):
    cfg = config.model_copy(update={"adaptive_learning": config.adaptive_learning.model_copy(update={"enabled": False})})
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), cfg, "XAUUSD", spec, False, Path("."), ("XAUUSD",))
    evaluation = SignalEvaluation(SignalSide.BUY, 72, "TRADE", None, (), "signal-hash", {})

    rule, threshold = orchestrator._adaptive_learning_rule(evaluation, "M15", 57.4, 50.0)

    assert rule.passed
    assert rule.reason_code == "ADAPTIVE_LEARNING_DISABLED"
    assert threshold == 50.0

def test_adaptive_learning_passes_when_samples_are_insufficient(config, spec, database):
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), config, "XAUUSD", spec, False, Path("."), ("XAUUSD",))
    evaluation = SignalEvaluation(SignalSide.BUY, 72, "TRADE", None, (), "signal-hash", {})
    _add_closed_learning_trade(database, wr=57.0, pnl=-1.0)

    rule, threshold = orchestrator._adaptive_learning_rule(evaluation, "M15", 57.4, 50.0)

    assert rule.passed
    assert rule.reason_code == "ADAPTIVE_LEARNING_PASS"
    assert rule.details["sample_size"] == 1
    assert threshold == 50.0

def test_adaptive_learning_raises_threshold_for_losing_setup_cluster(config, spec, database):
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), config, "XAUUSD", spec, False, Path("."), ("XAUUSD",))
    evaluation = SignalEvaluation(SignalSide.BUY, 72, "TRADE", None, (), "signal-hash", {})
    for _ in range(4):
        _add_closed_learning_trade(database, wr=58.0, pnl=-1.0)
    _add_closed_learning_trade(database, wr=58.0, pnl=1.0)

    rule, threshold = orchestrator._adaptive_learning_rule(evaluation, "M15", 57.4, 50.0)

    assert rule.passed
    assert rule.reason_code == "ADAPTIVE_LEARNING_RAISED_WR_THRESHOLD"
    assert rule.details["sample_size"] == 5
    assert threshold == 55.0

def test_adaptive_learning_blocks_bad_setup_cluster(config, spec, database):
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), config, "XAUUSD", spec, False, Path("."), ("XAUUSD",))
    evaluation = SignalEvaluation(SignalSide.BUY, 72, "TRADE", None, (), "signal-hash", {})
    for _ in range(7):
        _add_closed_learning_trade(database, wr=58.0, pnl=-1.0)
    for _ in range(3):
        _add_closed_learning_trade(database, wr=58.0, pnl=1.0)

    rule, threshold = orchestrator._adaptive_learning_rule(evaluation, "M15", 57.4, 50.0)

    assert not rule.passed
    assert rule.reason_code == "ADAPTIVE_LEARNING_BLOCK_BAD_SETUP_CLUSTER"
    assert rule.details["historical_win_rate"] == 30.0
    assert threshold == 50.0

def test_adaptive_learning_raises_threshold_for_painful_drawdown(config, spec, database):
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), config, "XAUUSD", spec, False, Path("."), ("XAUUSD",))
    evaluation = SignalEvaluation(SignalSide.BUY, 72, "TRADE", None, (), "signal-hash", {})
    for _ in range(4):
        _add_closed_learning_trade(database, wr=58.0, pnl=0.5, max_adverse_r=1.0)

    rule, threshold = orchestrator._adaptive_learning_rule(evaluation, "M15", 57.4, 50.0)

    assert rule.passed
    assert rule.reason_code == "ADAPTIVE_RISK_RAISED_WR_THRESHOLD"
    assert rule.details["average_max_adverse_r"] == pytest.approx(1.0)
    assert threshold == 55.0

def test_adaptive_learning_raises_threshold_for_weak_addons(config, spec, database):
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), config, "XAUUSD", spec, False, Path("."), ("XAUUSD",))
    evaluation = SignalEvaluation(SignalSide.BUY, 72, "TRADE", None, (), "signal-hash", {})
    for _ in range(3):
        _add_closed_learning_trade(database, wr=58.0, pnl=-1.0, entry_number=2)

    rule, threshold = orchestrator._adaptive_learning_rule(evaluation, "M15", 57.4, 50.0, proposed_entry_number=2)

    assert rule.passed
    assert rule.reason_code == "ADAPTIVE_RISK_RAISED_WR_THRESHOLD"
    assert rule.details["addon_sample_size"] == 3
    assert threshold == 57.5

def test_hard_trade_add_rules_block_deep_losing_basket(config, spec, database):
    hard_config = config.model_copy(update={"hard_trade": config.hard_trade.model_copy(update={"enabled": True})})
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), hard_config, "XAUUSD", spec, False, Path("."), ("XAUUSD",))
    rules = orchestrator._hard_trade_rules([], 0.01, same_side_count=1, basket_floating_profit=-2.01, entry_distance_atr=0.5)
    by_code = {rule.reason_code: rule for rule in rules}
    assert not by_code["HARD_TRADE_NO_DEEP_LOSING_ADD"].passed
    assert by_code["HARD_TRADE_NO_FAR_CHASE_ADD"].passed

def test_hard_trade_add_rules_block_far_chase(config, spec, database):
    hard_config = config.model_copy(update={"hard_trade": config.hard_trade.model_copy(update={"enabled": True})})
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), hard_config, "XAUUSD", spec, False, Path("."), ("XAUUSD",))
    rules = orchestrator._hard_trade_rules([], 0.01, same_side_count=1, basket_floating_profit=0.0, entry_distance_atr=1.01)
    by_code = {rule.reason_code: rule for rule in rules}
    assert by_code["HARD_TRADE_NO_DEEP_LOSING_ADD"].passed
    assert not by_code["HARD_TRADE_NO_FAR_CHASE_ADD"].passed

def test_hard_trade_add_rules_allow_first_entry(config, spec, database):
    hard_config = config.model_copy(update={"hard_trade": config.hard_trade.model_copy(update={"enabled": True})})
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), hard_config, "XAUUSD", spec, False, Path("."), ("XAUUSD",))
    rules = orchestrator._hard_trade_rules([], 0.01, same_side_count=0, basket_floating_profit=-99.0, entry_distance_atr=None)
    by_code = {rule.reason_code: rule for rule in rules}
    assert by_code["HARD_TRADE_NO_DEEP_LOSING_ADD"].passed
    assert by_code["HARD_TRADE_NO_FAR_CHASE_ADD"].passed

def _add_closed_recovery_basket(database, *, loss=-14.0, closed_at=None, positions=7):
    closed_at = closed_at or datetime.now(UTC)
    with database.transaction() as session:
        basket = Basket(
            external_id=f"recovery-{int(closed_at.timestamp())}",
            symbol="GBPUSD",
            direction="SELL",
            status=BasketState.CLOSED.value,
            opened_at=closed_at - timedelta(hours=1),
            closed_at=closed_at,
            position_count=positions,
            total_realized_profit=loss,
            close_reason=CloseReason.STOP_LOSS.value,
        )
        session.add(basket)
        session.flush()
        for index in range(positions):
            session.add(Trade(
                basket_id=basket.id,
                broker_ticket=None,
                idempotency_key=f"recovery-basket-trade-{basket.id}-{index}",
                symbol="GBPUSD",
                side="SELL",
                state=TradeState.CLOSED.value,
                volume=0,
                initial_volume=0.01,
                entry_price=1.3,
                stop_loss=1.31,
                initial_stop_loss=1.31,
                take_profit=1.28,
                realized_profit=loss / positions,
                floating_profit=0,
                estimated_win_rate=75,
                signal_hash="recovery-basket",
                entry_candle_time=closed_at - timedelta(hours=1),
                opened_at=closed_at - timedelta(hours=1),
                closed_at=closed_at,
                close_reason=CloseReason.STOP_LOSS.value,
            ))
        return basket.id

def _add_closed_recovery_trade(database, *, pnl, closed_at, symbol="GBPUSD"):
    with database.transaction() as session:
        session.add(Trade(
            basket_id=None,
            broker_ticket=None,
            idempotency_key=f"recovery-trade-{symbol}-{pnl}-{int(closed_at.timestamp())}",
            symbol=symbol,
            side="SELL",
            state=TradeState.CLOSED.value,
            volume=0,
            initial_volume=0.01,
            entry_price=1.3,
            stop_loss=1.31,
            initial_stop_loss=1.31,
            take_profit=1.28,
            realized_profit=pnl,
            floating_profit=0,
            estimated_win_rate=76,
            signal_hash="recovery",
            entry_candle_time=closed_at - timedelta(minutes=15),
            opened_at=closed_at - timedelta(minutes=15),
            closed_at=closed_at,
            close_reason=CloseReason.TAKE_PROFIT.value if pnl > 0 else CloseReason.STOP_LOSS.value,
        ))

def test_recovery_mode_tracks_hard_soft_and_normal(config, spec, database):
    cfg = config.model_copy(update={"recovery_mode": config.recovery_mode.model_copy(update={"enabled": True})})
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), cfg, "GBPUSD", spec, False, Path("."), ("BTCUSD", "GOLD", "GBPUSD"))
    closed_at = datetime.now(UTC) - timedelta(hours=3)
    _add_closed_recovery_basket(database, loss=-20.0, closed_at=closed_at)

    hard = orchestrator.recovery_mode_status()
    assert hard["mode"] == "hard"
    assert hard["required_win_rate"] == pytest.approx(75.0)

    _add_closed_recovery_trade(database, pnl=10.0, closed_at=closed_at + timedelta(hours=1))
    soft = orchestrator.recovery_mode_status()
    assert soft["mode"] == "soft"
    assert soft["required_win_rate"] == pytest.approx(72.0)
    assert soft["recovered_ratio"] == pytest.approx(0.5)

    _add_closed_recovery_trade(database, pnl=10.0, closed_at=closed_at + timedelta(hours=2))
    normal = orchestrator.recovery_mode_status()
    assert normal["mode"] == "normal"
    assert not normal["active"]

def test_recovery_mode_under_five_losses_starts_soft(config, spec, database):
    cfg = config.model_copy(update={"recovery_mode": config.recovery_mode.model_copy(update={"enabled": True})})
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), cfg, "GBPUSD", spec, False, Path("."), ("BTCUSD", "GOLD", "GBPUSD"))
    _add_closed_recovery_basket(database, loss=-8.0, closed_at=datetime.now(UTC) - timedelta(hours=1), positions=4)
    status = orchestrator.recovery_mode_status()
    assert status["mode"] == "soft"
    assert status["required_win_rate"] == pytest.approx(72.0)

def test_recovery_mode_five_or_six_losses_starts_hard(config, spec, database):
    cfg = config.model_copy(update={"recovery_mode": config.recovery_mode.model_copy(update={"enabled": True})})
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), cfg, "GBPUSD", spec, False, Path("."), ("BTCUSD", "GOLD", "GBPUSD"))
    _add_closed_recovery_basket(database, loss=-8.0, closed_at=datetime.now(UTC) - timedelta(hours=1), positions=5)
    status = orchestrator.recovery_mode_status()
    assert status["mode"] == "hard"
    assert status["required_win_rate"] == pytest.approx(75.0)

def test_recovery_mode_uses_latest_closed_basket_only(config, spec, database):
    cfg = config.model_copy(update={"recovery_mode": config.recovery_mode.model_copy(update={"enabled": True})})
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), cfg, "GBPUSD", spec, False, Path("."), ("BTCUSD", "GOLD", "GBPUSD"))
    old_closed = datetime.now(UTC) - timedelta(hours=4)
    recent_closed = datetime.now(UTC) - timedelta(hours=1)
    _add_closed_recovery_basket(database, loss=-20.0, closed_at=old_closed)
    with database.transaction() as session:
        basket = Basket(
            external_id="recent-win",
            symbol="GBPUSD",
            direction="SELL",
            status=BasketState.CLOSED.value,
            opened_at=recent_closed - timedelta(hours=1),
            closed_at=recent_closed,
            position_count=2,
            total_realized_profit=7.0,
            close_reason=CloseReason.TAKE_PROFIT.value,
        )
        session.add(basket)
        session.flush()
    status = orchestrator.recovery_mode_status()
    assert status["mode"] == "normal"
    assert status["trigger_basket_external_id"] == "recent-win"
    assert status["trigger_position_count"] == 0

def test_recovery_mode_raises_wr_threshold_to_75(config, spec, database):
    cfg = config.model_copy(update={"recovery_mode": config.recovery_mode.model_copy(update={"enabled": True})})
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), cfg, "GBPUSD", spec, False, Path("."), ("BTCUSD", "GOLD", "GBPUSD"))
    _add_closed_recovery_basket(database, loss=-20.0, closed_at=datetime.now(UTC) - timedelta(hours=1))

    rule, threshold = orchestrator._recovery_mode_rule(70.0)

    assert rule.passed
    assert rule.reason_code == "RECOVERY_MODE_HARD_WR_GATE"
    assert threshold == pytest.approx(75.0)

def test_recovery_mode_soft_raises_wr_threshold_to_72(config, spec, database):
    cfg = config.model_copy(update={"recovery_mode": config.recovery_mode.model_copy(update={"enabled": True})})
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), cfg, "GBPUSD", spec, False, Path("."), ("BTCUSD", "GOLD", "GBPUSD"))
    closed_at = datetime.now(UTC) - timedelta(hours=2)
    _add_closed_recovery_basket(database, loss=-20.0, closed_at=closed_at)
    _add_closed_recovery_trade(database, pnl=10.0, closed_at=closed_at + timedelta(hours=1))

    rule, threshold = orchestrator._recovery_mode_rule(70.0)

    assert rule.passed
    assert rule.reason_code == "RECOVERY_MODE_SOFT_WR_GATE"
    assert threshold == pytest.approx(72.0)

def test_restart_emergency_exit_closes_losing_hard_trade_basket(config, spec, database):
    cfg = config.model_copy(update={
        "hard_trade": config.hard_trade.model_copy(update={
            "enabled": True,
            "emergency_exit_on_restart": True,
            "emergency_exit_max_loss_usd": 8,
            "emergency_exit_max_adverse_r": 0.8,
        }),
        "basket_stop_loss": config.basket_stop_loss.model_copy(update={"hard_max_loss_usd": 8}),
    })
    paper = PaperBrokerClient(FakeMarket(spec, bid=1990.0, ask=1990.2))
    orchestrator = TradingOrchestrator(database, paper, cfg, "XAUUSD", spec, True, Path("."), ("XAUUSD",))
    now = datetime.now(UTC)
    with database.transaction() as session:
        basket = Basket(external_id="hard-restart-basket", symbol="XAUUSD", direction="BUY", status=BasketState.ACTIVE.value, opened_at=now, initial_risk_amount=10)
        session.add(basket)
        session.flush()
        basket_id = basket.id
        session.add(Trade(
            basket_id=basket_id,
            broker_ticket=901,
            idempotency_key="hard-restart-trade",
            symbol="XAUUSD",
            side="BUY",
            state=TradeState.OPEN.value,
            volume=0.01,
            initial_volume=0.01,
            entry_price=2000.0,
            stop_loss=1980.0,
            initial_stop_loss=1980.0,
            take_profit=2020.0,
            realized_profit=0.0,
            floating_profit=-10.0,
            initial_risk_amount=10.0,
            max_adverse_r=0.9,
            signal_hash="hard-restart",
            entry_candle_time=now,
            opened_at=now,
        ))
    paper.restore_position(BrokerPosition(901, "XAUUSD", "BUY", 0.01, 2000.0, 1990.0, 1980.0, 2020.0, -10.0, cfg.broker.magic_number, "test", now))

    orchestrator._hard_restart_emergency_exit()

    assert paper.positions("XAUUSD", cfg.broker.magic_number) == []
    with database.transaction() as session:
        stored_basket = session.get(Basket, basket_id)
        stored_trade = session.scalar(select(Trade).where(Trade.idempotency_key == "hard-restart-trade"))
        request = session.scalar(select(ExecutionRequest).where(ExecutionRequest.trade_id == stored_trade.id, ExecutionRequest.action == "CLOSE"))
        assert stored_basket.status == BasketState.CLOSED.value
        assert stored_basket.close_reason == CloseReason.STOP_LOSS.value
        assert stored_trade.state == TradeState.CLOSED.value
        assert request.status == "SUCCESS"

def test_status_care_warning_flags_stale_or_unhealthy_heartbeats():
    stale = _stale_care_symbols({
        "XAUUSD": {"healthy": True, "loop_heartbeat_age_seconds": {"position_manager": 31, "signal_loop": 1}},
        "BTCUSD": {"healthy": False, "loop_heartbeat_age_seconds": {"position_manager": 1, "signal_loop": 1}},
        "EURUSD": {"healthy": True, "loop_heartbeat_age_seconds": {"position_manager": 2, "signal_loop": 3}},
    })
    assert set(stale) == {"XAUUSD", "BTCUSD"}
    assert stale["XAUUSD"]["position_manager_age_seconds"] == 31

def test_forex_position_scope_is_separate_from_btc_gold(config, spec, database):
    forex = ForexTradingConfig(enabled=True, symbols=("EURUSD",), max_open_positions=7)
    cfg = config.model_copy(update={"forex_trading": forex})
    non_forex = TradingOrchestrator(database, FakeMarket(spec), cfg, "BTCUSD", spec, False, Path("."), ("BTCUSD", "GOLD", "EURUSD"))
    forex_orch = TradingOrchestrator(database, FakeMarket(spec), cfg, "EURUSD", spec, False, Path("."), ("BTCUSD", "GOLD", "EURUSD"))
    assert non_forex._position_scope_symbols() == ("BTCUSD", "GOLD")
    assert forex_orch._position_scope_symbols() == ("EURUSD",)

def test_forex_mode_only_blocks_when_disabled(config, spec, database):
    positions = [
        BrokerPosition(100 + idx, "EURUSD", "BUY", 0.01, 1.1, 1.1, 1.09, 1.12, 0, config.broker.magic_number, "fx", datetime.now(UTC))
        for idx in range(5)
    ]
    forex = ForexTradingConfig(enabled=False, symbols=("EURUSD",), max_open_positions=7)
    cfg = config.model_copy(update={"forex_trading": forex})
    broker = ForexPositionMarket(spec, {"EURUSD": positions})
    orchestrator = TradingOrchestrator(database, broker, cfg, "EURUSD", spec, False, Path("."), ("BTCUSD", "GOLD", "EURUSD"))
    rule = orchestrator._forex_trading_rules()[0]
    assert not rule.passed
    assert rule.reason_code == "FOREX_MODE_DISABLED"
    assert rule.details["enabled"] is False

def test_open_trade_stores_setup_win_rate(config, spec, database):
    with database.transaction() as session:
        trade = Trade(
            basket_id=None,
            broker_ticket=None,
            idempotency_key="XAUUSD_BUY_M5_test",
            symbol="XAUUSD",
            side="BUY",
            state=TradeState.OPEN.value,
            volume=0.01,
            initial_volume=0.01,
            entry_price=2000.0,
            stop_loss=1999.0,
            initial_stop_loss=1999.0,
            take_profit=2002.0,
            realized_profit=0.0,
            floating_profit=0.0,
            estimated_win_rate=67.5,
            signal_hash="signal-hash",
            entry_candle_time=datetime.now(UTC),
            opened_at=datetime.now(UTC),
        )
        session.add(trade)
        session.flush()
        trade_id = trade.id

    with database.transaction() as session:
        stored = session.get(Trade, trade_id)
        assert stored is not None
        assert stored.estimated_win_rate == pytest.approx(67.5)

def test_closed_trade_history_cleanup_keeps_recent_and_open_trades(config, spec, database):
    orchestrator = TradingOrchestrator(database, FakeMarket(spec), config, "XAUUSD", spec, False, Path("."), ("XAUUSD",))
    now = datetime.now(UTC)
    with database.transaction() as session:
        old = Trade(
            basket_id=None, broker_ticket=1, idempotency_key="old", symbol="XAUUSD", side="BUY",
            state=TradeState.CLOSED.value, volume=0, initial_volume=0.01, entry_price=2000,
            stop_loss=1990, initial_stop_loss=1990, take_profit=2020, realized_profit=1,
            floating_profit=0, estimated_win_rate=70, signal_hash="old", entry_candle_time=now,
            opened_at=now - timedelta(days=100), closed_at=now - timedelta(days=91), close_reason="TAKE_PROFIT",
        )
        recent = Trade(
            basket_id=None, broker_ticket=2, idempotency_key="recent", symbol="XAUUSD", side="BUY",
            state=TradeState.CLOSED.value, volume=0, initial_volume=0.01, entry_price=2000,
            stop_loss=1990, initial_stop_loss=1990, take_profit=2020, realized_profit=1,
            floating_profit=0, estimated_win_rate=70, signal_hash="recent", entry_candle_time=now,
            opened_at=now - timedelta(days=1), closed_at=now - timedelta(days=1), close_reason="TAKE_PROFIT",
        )
        open_trade = Trade(
            basket_id=None, broker_ticket=3, idempotency_key="open", symbol="XAUUSD", side="BUY",
            state=TradeState.OPEN.value, volume=0.01, initial_volume=0.01, entry_price=2000,
            stop_loss=1990, initial_stop_loss=1990, take_profit=2020, realized_profit=0,
            floating_profit=0, estimated_win_rate=70, signal_hash="open", entry_candle_time=now,
            opened_at=now - timedelta(days=5), closed_at=None, close_reason=None,
        )
        session.add_all((old, recent, open_trade))
        session.flush()
        old_id, recent_id, open_id = old.id, recent.id, open_trade.id
        session.add(TradeEvent(trade_id=old_id, event_type="POSITION_REVALIDATION_KEPT", details={}))
        session.add(ExecutionRequest(idempotency_key="old-request", trade_id=old_id, action="OPEN", status="SUCCESS"))
        old_rejected = SignalDecision(
            timestamp=now - timedelta(days=4), symbol="XAUUSD", trend="BULLISH", side="BUY",
            score=70, rule_results=[], spread=1, atr=1, rsi=50, adx=20, entry_price=2000,
            stop_loss=None, take_profit=None, risk_reward=None, decision="NO_TRADE",
            rejection_reason="TEST_REJECT", signal_hash="old-reject",
        )
        old_opened = SignalDecision(
            timestamp=now - timedelta(days=4), symbol="XAUUSD", trend="BULLISH", side="BUY",
            score=90, rule_results=[], spread=1, atr=1, rsi=50, adx=20, entry_price=2000,
            stop_loss=1990, take_profit=2020, risk_reward=2, decision="OPENED",
            rejection_reason=None, signal_hash="old-opened",
        )
        old_indicator = IndicatorSnapshot(
            timestamp=now - timedelta(days=4), symbol="XAUUSD", timeframe="M15",
            candle_time=now - timedelta(days=4), values={"close": 2000},
        )
        session.add_all((old_rejected, old_opened, old_indicator))
        session.flush()
        old_rejected_id, old_opened_id, old_indicator_id = old_rejected.id, old_opened.id, old_indicator.id

    orchestrator._cleanup_old_closed_trades()

    with database.transaction() as session:
        assert session.get(Trade, old_id) is None
        assert session.get(Trade, recent_id) is not None
        assert session.get(Trade, open_id) is not None
        assert not list(session.scalars(select(TradeEvent).where(TradeEvent.trade_id == old_id)))
        assert not list(session.scalars(select(ExecutionRequest).where(ExecutionRequest.trade_id == old_id)))
        assert session.get(SignalDecision, old_rejected_id) is None
        assert session.get(SignalDecision, old_opened_id) is not None
        assert session.get(IndicatorSnapshot, old_indicator_id) is None
