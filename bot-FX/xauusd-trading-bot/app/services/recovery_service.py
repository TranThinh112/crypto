"""Restart recovery and database/broker reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from app.broker.mt5_client import BrokerClient, BrokerDeal, BrokerPosition, SymbolSpec
from app.config.settings import TradingConfig
from app.database import Database
from app.models.basket import Basket, BasketEvent
from app.models.bot_state import BotStateRecord
from app.models.trade import Trade, TradeEvent
from app.utils.enums import BasketState, BotState, TradeState


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    consistent: bool
    broker_positions: int
    database_open_trades: int
    restored_paper_positions: int
    missing_in_database: tuple[int, ...]
    missing_at_broker: tuple[int, ...]
    message: str


class RecoveryService:
    def __init__(self, database: Database, broker: BrokerClient, config: TradingConfig, symbol: str, spec: SymbolSpec) -> None:
        self.database = database
        self.broker = broker
        self.config = config
        self.symbol = symbol
        self.spec = spec

    def reconcile(self) -> ReconciliationResult:
        with self.database.transaction() as session:
            db_trades = list(session.scalars(select(Trade).where(Trade.symbol == self.symbol, Trade.state.in_((TradeState.OPEN.value, TradeState.PARTIALLY_CLOSED.value, TradeState.SUBMITTED.value)))))
            active_basket = session.scalar(select(Basket).where(Basket.symbol == self.symbol, Basket.status.in_((BasketState.ACTIVE.value, BasketState.CLOSING.value, BasketState.CLOSE_FAILED.value))))
            deal_events = list(session.scalars(select(TradeEvent).where(TradeEvent.event_type == "BROKER_DEAL_RECONCILED")))

        restore_deal = getattr(self.broker, "restore_deal", None)
        if callable(restore_deal):
            for event in deal_events:
                details = event.details
                restore_deal(BrokerDeal(
                    ticket=int(details["deal_ticket"]), position_id=int(details["position_id"]),
                    symbol=str(details["symbol"]), side=str(details["side"]), volume=float(details["volume"]),
                    price=float(details["price"]), profit=float(details["profit"]),
                    commission=float(details["commission"]), swap=float(details["swap"]), entry=str(details["entry"]),
                    time=datetime.fromisoformat(str(details["time"])).astimezone(UTC),
                ))
            restore_balance = getattr(self.broker, "restore_balance", None)
            if callable(restore_balance):
                total_realized = sum(float(event.details["profit"]) + float(event.details["commission"]) + float(event.details["swap"]) for event in deal_events)
                restore_balance(self.config.backtest.initial_equity + total_realized)

        restored = 0
        restore = getattr(self.broker, "restore_position", None)
        if callable(restore):
            current_tickets = {item.ticket for item in self.broker.positions(self.symbol, self.config.broker.magic_number)}
            tick = self.broker.tick(self.symbol)
            for trade in db_trades:
                if trade.broker_ticket and trade.broker_ticket not in current_tickets:
                    current = tick.bid if trade.side == "BUY" else tick.ask
                    restore(BrokerPosition(
                        ticket=trade.broker_ticket, symbol=trade.symbol, side=trade.side, volume=trade.volume,
                        entry_price=trade.entry_price, current_price=current, stop_loss=trade.stop_loss,
                        take_profit=trade.take_profit, profit=trade.floating_profit,
                        magic=self.config.broker.magic_number, comment=f"{self.config.broker.order_comment_prefix}|restored",
                        opened_at=trade.opened_at or datetime.now(UTC),
                    ))
                    restored += 1

        positions = self.broker.positions(self.symbol, self.config.broker.magic_number)
        broker_tickets = {item.ticket for item in positions}
        db_by_ticket = {item.broker_ticket: item for item in db_trades if item.broker_ticket is not None}
        missing_db = tuple(sorted(broker_tickets.difference(db_by_ticket)))
        missing_broker = tuple(sorted(set(db_by_ticket).difference(broker_tickets)))

        # A confirmed broker-side exit is reflected in the DB; unknown broker positions are never adopted.
        if missing_broker:
            with self.database.transaction() as session:
                now = datetime.now(UTC)
                for ticket in missing_broker:
                    trade = session.scalar(select(Trade).where(Trade.broker_ticket == ticket))
                    if trade:
                        try:
                            deals = self.broker.deals(trade.opened_at or now, now, trade.symbol, self.config.broker.magic_number)
                        except Exception:
                            deals = []
                        exit_deals = [
                            deal for deal in deals
                            if deal.position_id == ticket and str(deal.entry).upper() in ("OUT", "INOUT", "OUT_BY")
                        ]
                        monetary = sum(deal.profit + deal.commission + deal.swap for deal in exit_deals)
                        trade.state = TradeState.CLOSED.value
                        trade.closed_at = max((deal.time for deal in exit_deals), default=now)
                        trade.close_reason = "BROKER_SIDE_EXIT"
                        if exit_deals:
                            trade.realized_profit = monetary
                            for deal in exit_deals:
                                session.add(TradeEvent(trade_id=trade.id, event_type="BROKER_DEAL_RECONCILED", details={
                                    "deal_ticket": deal.ticket, "position_id": deal.position_id, "symbol": deal.symbol,
                                    "side": deal.side, "volume": deal.volume, "price": deal.price, "profit": deal.profit,
                                    "commission": deal.commission, "swap": deal.swap, "entry": deal.entry,
                                    "time": deal.time.isoformat(),
                                }))
                        elif abs(float(trade.realized_profit or 0.0)) < 1e-9 and abs(float(trade.floating_profit or 0.0)) > 1e-9:
                            trade.realized_profit = trade.floating_profit
                            session.add(TradeEvent(trade_id=trade.id, event_type="BROKER_EXIT_ESTIMATED", details={
                                "ticket": ticket,
                                "monetary": trade.floating_profit,
                                "source": "last_floating_profit",
                                "closed_at": trade.closed_at.isoformat(),
                            }))
                        session.add(TradeEvent(trade_id=trade.id, event_type="RECONCILED_BROKER_EXIT", details={"ticket": ticket}))

        inconsistent = bool(missing_db or (positions and active_basket is None))
        message = "RECONCILIATION_OK" if not inconsistent else "UNTRACKED_BROKER_POSITION_OR_MISSING_BASKET"
        with self.database.transaction() as session:
            if active_basket:
                basket = session.get(Basket, active_basket.id)
                if basket:
                    basket.position_count = len(positions)
                    basket.total_volume = sum(item.volume for item in positions)
                    session.add(BasketEvent(basket_id=basket.id, event_type="RECONCILIATION", details={"consistent": not inconsistent, "broker_tickets": sorted(broker_tickets), "missing_db": missing_db, "missing_broker": missing_broker}))
            session.add(BotStateRecord(state=BotState.ENTRY_PAUSED.value if inconsistent else BotState.RUNNING.value, reason=message, details={"missing_db": missing_db, "missing_broker": missing_broker, "restored_paper": restored}))
        return ReconciliationResult(not inconsistent, len(positions), len(db_trades), restored, missing_db, missing_broker, message)
