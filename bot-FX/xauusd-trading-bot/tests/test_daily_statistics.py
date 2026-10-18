from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.broker.mt5_client import AccountSnapshot, BrokerDeal
from app.models.bot_state import BotStateRecord, DailyStatistic, DataResetMarker
from app.models.trade import Trade
from app.services.trading_orchestrator import TradingOrchestrator
from app.utils.enums import BotState, TradeState
from tests.conftest import FakeMarket


class DailyStatsMarket(FakeMarket):
    def __init__(self, spec, account: AccountSnapshot, deals: list[BrokerDeal]) -> None:
        super().__init__(spec)
        self._account = account
        self._deals = deals
        self.deal_windows: list[tuple[datetime, datetime, str, int]] = []

    def account(self) -> AccountSnapshot:
        return self._account

    def deals(self, start: datetime, end: datetime, symbol: str, magic: int) -> list[BrokerDeal]:
        self.deal_windows.append((start, end, symbol, magic))
        return [deal for deal in self._deals if deal.symbol == symbol and start <= deal.time <= end]


def test_daily_status_uses_intraday_reset_marker(config, spec, database):
    reset_at = datetime(2026, 7, 20, 11, 0, tzinfo=UTC)
    now = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    deals = [
        BrokerDeal(1, 100, "XAUUSD", "BUY", 0.1, 2000.0, -10.0, 0.0, 0.0, "OUT", datetime(2026, 7, 20, 10, 0, tzinfo=UTC)),
        BrokerDeal(2, 200, "XAUUSD", "BUY", 0.1, 2001.0, 5.0, 0.0, 0.0, "OUT", datetime(2026, 7, 20, 11, 30, tzinfo=UTC)),
        BrokerDeal(3, 201, "XAUUSD", "BUY", 0.1, 2002.0, -2.0, 0.0, 0.0, "OUT", datetime(2026, 7, 20, 11, 45, tzinfo=UTC)),
    ]
    market = DailyStatsMarket(spec, AccountSnapshot(9993.0, 9993.0, 0.0, 9993.0, 0.0, "USD"), deals)
    orchestrator = TradingOrchestrator(database, market, config, "XAUUSD", spec, False, Path("."), ("XAUUSD",))

    with database.transaction() as session:
        session.add(DataResetMarker(reset_at=reset_at, starting_equity=9990.0, reason="test reset"))
        session.add(
            DailyStatistic(
                trading_date=now.date(),
                starting_equity=10000.0,
                realized_pnl=-10.0,
                maximum_drawdown=50.0,
                trade_count=10,
                winning_trades=3,
                losing_trades=7,
            )
        )

    allowed, record, _ = orchestrator._daily_status(now)

    assert allowed
    assert market.deal_windows[0][0] == reset_at
    assert record.starting_equity == pytest.approx(9990.0)
    assert record.realized_pnl == pytest.approx(3.0)
    assert record.maximum_drawdown == pytest.approx(0.0)
    assert record.trade_count == 2
    assert record.winning_trades == 1
    assert record.losing_trades == 1
    assert record.consecutive_losses == 1


def test_daily_status_realized_uses_closed_deals_not_balance_delta(config, spec, database):
    now = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    deals = [
        BrokerDeal(1, 100, "XAUUSD", "BUY", 0.1, 2000.0, 8.0, 0.0, 0.0, "OUT", datetime(2026, 7, 20, 11, 30, tzinfo=UTC)),
        BrokerDeal(2, 101, "XAUUSD", "BUY", 0.1, 2001.0, -3.0, 0.0, 0.0, "OUT", datetime(2026, 7, 20, 11, 45, tzinfo=UTC)),
    ]
    market = DailyStatsMarket(spec, AccountSnapshot(9980.0, 9980.0, 0.0, 9980.0, 0.0, "USD"), deals)
    orchestrator = TradingOrchestrator(database, market, config, "XAUUSD", spec, False, Path("."), ("XAUUSD",))
    with database.transaction() as session:
        session.add(DailyStatistic(trading_date=now.date(), starting_equity=10000.0))

    _, record, _ = orchestrator._daily_status(now)

    account_delta = market.account().balance - record.starting_equity
    assert account_delta == pytest.approx(-20.0)
    assert record.realized_pnl == pytest.approx(5.0)


def test_daily_status_locks_legacy_null_reset_marker_baseline(config, spec, database):
    reset_at = datetime(2026, 7, 20, 11, 0, tzinfo=UTC)
    now = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    market = DailyStatsMarket(spec, AccountSnapshot(9980.0, 9980.0, 0.0, 9980.0, 0.0, "USD"), [])
    orchestrator = TradingOrchestrator(database, market, config, "XAUUSD", spec, False, Path("."), ("XAUUSD",))

    with database.transaction() as session:
        marker = DataResetMarker(
            reset_at=reset_at,
            starting_equity=None,
            reason="legacy reset without baseline",
            created_at=datetime(2026, 7, 20, 11, 5, tzinfo=UTC),
        )
        session.add(marker)
        session.add(
            DailyStatistic(
                trading_date=now.date(),
                starting_equity=9990.0,
                realized_pnl=0.0,
                floating_pnl=0.0,
                maximum_drawdown=0.0,
                updated_at=datetime(2026, 7, 20, 11, 30, tzinfo=UTC),
            )
        )
        session.flush()
        marker_id = marker.id

    allowed, record, _ = orchestrator._daily_status(now)

    assert allowed
    assert record.starting_equity == pytest.approx(9990.0)
    assert record.realized_pnl == pytest.approx(-10.0)
    with database.transaction() as session:
        marker = session.get(DataResetMarker, marker_id)
        assert marker is not None
        assert marker.starting_equity == pytest.approx(9990.0)


def test_daily_status_uses_7am_vietnam_cutoff(config, spec, database):
    now = datetime(2026, 7, 20, 23, 30, tzinfo=UTC)
    deals = [
        BrokerDeal(1, 100, "XAUUSD", "BUY", 0.1, 2000.0, 4.0, 0.0, 0.0, "OUT", datetime(2026, 7, 20, 0, 30, tzinfo=UTC)),
        BrokerDeal(2, 101, "XAUUSD", "BUY", 0.1, 2001.0, -1.0, 0.0, 0.0, "OUT", datetime(2026, 7, 20, 23, 0, tzinfo=UTC)),
    ]
    market = DailyStatsMarket(spec, AccountSnapshot(10003.0, 10003.0, 0.0, 10003.0, 0.0, "USD"), deals)
    orchestrator = TradingOrchestrator(database, market, config, "XAUUSD", spec, False, Path("."), ("XAUUSD",))

    _, record, _ = orchestrator._daily_status(now)

    assert market.deal_windows[0][0] == datetime(2026, 7, 20, 0, 0, tzinfo=UTC)
    assert record.trading_date == now.astimezone(UTC).date()
    assert record.realized_pnl == pytest.approx(3.0)

def test_daily_status_includes_closed_forex_trades_outside_portfolio_scope(config, spec, database):
    now = datetime(2026, 7, 24, 16, 0, tzinfo=UTC)
    market = DailyStatsMarket(spec, AccountSnapshot(9990.0, 9994.0, 0.0, 9990.0, 0.0, "USD"), [])
    orchestrator = TradingOrchestrator(database, market, config, "BTCUSD", spec, False, Path("."), ("BTCUSD", "GOLD"))
    with database.transaction() as session:
        session.add(Trade(
            basket_id=None,
            broker_ticket=123,
            idempotency_key="EURUSD_SELL_M15_test",
            symbol="EURUSD",
            side="SELL",
            state=TradeState.CLOSED.value,
            volume=0.0,
            initial_volume=0.03,
            entry_price=1.1,
            stop_loss=1.11,
            initial_stop_loss=1.11,
            take_profit=1.08,
            realized_profit=-6.54,
            floating_profit=0.0,
            estimated_win_rate=76.0,
            signal_hash="forex",
            entry_candle_time=now,
            partial_levels_completed=[],
            break_even_applied=False,
            opened_at=now,
            closed_at=now,
            close_reason="STOP_LOSS",
        ))

    _, record, _ = orchestrator._daily_status(now)

    assert record.realized_pnl == pytest.approx(-6.54)


def test_start_restores_manual_pause_after_restart(config, spec, database):
    market = FakeMarket(spec)
    orchestrator = TradingOrchestrator(database, market, config, "XAUUSD", spec, False, Path("."), ("XAUUSD",))
    with database.transaction() as session:
        session.add(BotStateRecord(state=BotState.ENTRY_PAUSED.value, reason="MANUAL_PAUSE"))

    orchestrator.start()
    try:
        assert orchestrator.state is BotState.ENTRY_PAUSED
        assert orchestrator.state_reason == "MANUAL_PAUSE_RESTORED"
    finally:
        orchestrator.stop()
