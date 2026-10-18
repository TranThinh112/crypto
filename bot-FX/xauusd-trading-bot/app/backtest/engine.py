"""Event-driven M5 backtester reusing the production rule and risk engines."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pandas as pd

from app.broker.mt5_client import BrokerPosition, SymbolSpec
from app.config.settings import TradingConfig
from app.guards.session_guard import SessionGuard
from app.market_data.indicator_service import IndicatorService
from app.positions.break_even_manager import BreakEvenManager
from app.positions.partial_close_manager import PartialCloseManager
from app.positions.trailing_stop_manager import TrailingStopManager
from app.risk.daily_risk_guard import DailyRiskGuard, DailyRiskSnapshot
from app.risk.position_sizing import PositionSizer
from app.risk.risk_manager import RiskManager
from app.strategy.signal_engine import SignalEngine
from app.strategy.trend_detector import TrendDetector
from app.utils.enums import SignalSide, TrendDirection
from app.utils.exceptions import MarketDataError, OrderValidationError


@dataclass(slots=True)
class SimPosition:
    ticket: int
    basket_id: int
    side: str
    initial_volume: float
    volume: float
    entry: float
    initial_stop: float
    stop: float
    take_profit: float
    opened_at: datetime
    signal_score: int
    completed_levels: tuple[float, ...] = ()
    break_even_applied: bool = False
    realized_profit: float = 0


@dataclass(frozen=True, slots=True)
class BacktestTrade:
    ticket: int
    basket_id: int
    side: str
    volume: float
    entry_price: float
    exit_price: float
    opened_at: datetime
    closed_at: datetime
    profit: float
    risk_amount: float
    achieved_r_multiple: float
    holding_seconds: float
    close_reason: str
    signal_score: int


@dataclass(frozen=True, slots=True)
class BasketRecord:
    basket_id: int
    direction: str
    opened_at: datetime
    closed_at: datetime
    initial_risk: float
    profit: float
    close_reason: str
    maximum_floating_profit: float
    maximum_drawdown: float


@dataclass(frozen=True, slots=True)
class PendingSignal:
    side: SignalSide
    atr: float
    swing_low: float
    swing_high: float
    score: int
    created_at: datetime


@dataclass(slots=True)
class ActiveBasket:
    basket_id: int
    direction: str
    opened_at: datetime
    initial_risk: float = 0
    realized: float = 0
    maximum_profit: float = 0
    maximum_drawdown: float = 0


@dataclass(frozen=True, slots=True)
class BacktestResult:
    trades: tuple[BacktestTrade, ...]
    baskets: tuple[BasketRecord, ...]
    equity_curve: tuple[tuple[datetime, float], ...]
    signal_count: int
    rejected_signal_count: int


class BacktestEngine:
    """Signals use a closed bar and orders fill no earlier than the next M5 open."""

    def __init__(self, config: TradingConfig, spec: SymbolSpec) -> None:
        self.config = config
        self.spec = spec
        self.indicators = IndicatorService(config.strategy)
        self.trends = TrendDetector(config.strategy)
        self.signals = SignalEngine(config.strategy, config.signal_scoring, config.take_profit)
        self.risk = RiskManager(config.stop_loss, config.take_profit)
        self.break_even = BreakEvenManager(config.break_even)
        self.trailing = TrailingStopManager(config.trailing_stop)
        self.partial = PartialCloseManager(config.partial_close)
        self.session = SessionGuard(config.session)
        self.daily_guard = DailyRiskGuard(config.daily_risk)

    @staticmethod
    def _validate(candles: pd.DataFrame) -> pd.DataFrame:
        required = {"time", "open", "high", "low", "close", "volume"}
        missing = required.difference(candles.columns)
        if missing:
            raise MarketDataError(f"Backtest data missing columns: {sorted(missing)}")
        frame = candles.copy()
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        if frame["time"].duplicated().any():
            raise MarketDataError("Backtest timestamps must be unique")
        frame = frame.sort_values("time").reset_index(drop=True)
        if "spread" not in frame:
            frame["spread"] = 0.0
        return frame

    @staticmethod
    def _resample(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
        indexed = frame.set_index("time")
        output = indexed.resample(rule, label="right", closed="right").agg({
            "open": "first", "high": "max", "low": "min", "close": "last",
            "volume": "sum", "spread": "mean",
        }).dropna(subset=["open", "high", "low", "close"])
        return output.reset_index()

    def _prepare(self, candles: pd.DataFrame) -> dict[str, pd.DataFrame]:
        m5 = self._validate(candles)
        raw = {"M5": m5, "M15": self._resample(m5, "15min"), "H1": self._resample(m5, "1h"), "H4": self._resample(m5, "4h")}
        return {name: self.indicators.calculate(value) for name, value in raw.items()}

    def _profit(self, side: str, entry: float, exit_price: float, volume: float) -> float:
        movement = exit_price - entry if side == "BUY" else entry - exit_price
        return movement / self.spec.trade_tick_size * self.spec.trade_tick_value * volume

    def run(self, candles: pd.DataFrame) -> BacktestResult:
        frames = self._prepare(candles)
        m5 = frames["M5"]
        starting_equity = self.config.backtest.initial_equity
        realized_balance = 0.0
        positions: list[SimPosition] = []
        trades: list[BacktestTrade] = []
        baskets: list[BasketRecord] = []
        equity_curve: list[tuple[datetime, float]] = []
        active_basket: ActiveBasket | None = None
        pending: PendingSignal | None = None
        cooldown_until: datetime | None = None
        last_entry_at: datetime | None = None
        next_ticket = 1
        next_basket_id = 1
        signal_count = rejected_count = 0
        day_start_equity = starting_equity
        current_day = None
        consecutive_losses = 0

        def price_with_cost(mid: float, side: str, spread_points: float, is_entry: bool) -> float:
            half_spread = spread_points * self.spec.point / 2
            slip = self.config.backtest.slippage_points * self.spec.point
            if (side == "BUY") == is_entry:
                return mid + half_spread + slip
            return mid - half_spread - slip

        def close_position(position: SimPosition, price: float, now: datetime, reason: str, volume: float | None = None) -> float:
            nonlocal realized_balance, consecutive_losses
            close_volume = position.volume if volume is None else volume
            gross = self._profit(position.side, position.entry, price, close_volume)
            commission = self.config.backtest.commission_per_lot * close_volume
            net = gross - commission
            position.realized_profit += net
            position.volume -= close_volume
            realized_balance += net
            if active_basket:
                active_basket.realized += net
            if position.volume <= 1e-12:
                risk_amount = abs(position.entry - position.initial_stop) / self.spec.trade_tick_size * self.spec.trade_tick_value * position.initial_volume
                achieved_r = position.realized_profit / risk_amount if risk_amount else 0
                trades.append(BacktestTrade(
                    position.ticket, position.basket_id, position.side, position.initial_volume, position.entry, price,
                    position.opened_at, now, position.realized_profit, risk_amount, achieved_r,
                    (now - position.opened_at).total_seconds(), reason, position.signal_score,
                ))
                consecutive_losses = consecutive_losses + 1 if position.realized_profit < 0 else 0
            return net

        def close_basket(now: datetime, mid_price: float, spread_points: float, reason: str) -> None:
            nonlocal active_basket, cooldown_until
            if active_basket is None:
                return
            for position in list(positions):
                exit_price = price_with_cost(mid_price, position.side, spread_points, False)
                close_position(position, exit_price, now, reason)
                positions.remove(position)
            basket_profit = active_basket.realized
            baskets.append(BasketRecord(
                active_basket.basket_id, active_basket.direction, active_basket.opened_at, now,
                active_basket.initial_risk, basket_profit, reason,
                active_basket.maximum_profit, active_basket.maximum_drawdown,
            ))
            minutes = self.config.cooldown.after_take_profit_minutes if reason == "TAKE_PROFIT" else self.config.cooldown.after_stop_loss_minutes if reason == "STOP_LOSS" else self.config.cooldown.after_manual_close_minutes
            cooldown_until = now + timedelta(minutes=minutes)
            active_basket = None

        for index, row in m5.iterrows():
            now = row.time.to_pydatetime() if hasattr(row.time, "to_pydatetime") else row.time
            spread_points = float(row.spread) if float(row.spread) > 0 else self.config.backtest.simulated_spread_points
            if current_day != now.date():
                current_day = now.date()
                day_start_equity = starting_equity + realized_balance

            # A signal created at the previous close can only fill at this bar's open.
            if pending is not None:
                open_floating = sum(self._profit(item.side, item.entry, float(row.open), item.volume) for item in positions)
                realized_today = starting_equity + realized_balance - day_start_equity
                daily_locked = not self.daily_guard.evaluate(DailyRiskSnapshot(day_start_equity, realized_today, open_floating, consecutive_losses))[0]
                basket_losing = (
                    self.config.position_control.prohibit_adding_to_losing_basket
                    and active_basket is not None
                    and active_basket.realized + open_floating < 0
                )
                entry_price = price_with_cost(float(row.open), pending.side.value, spread_points, True)
                distance_ok = not positions or min(abs(entry_price - item.entry) for item in positions) >= pending.atr * self.config.position_control.minimum_entry_distance_atr
                entry_time_ok = last_entry_at is None or now - last_entry_at >= timedelta(minutes=self.config.position_control.entry_cooldown_minutes)
                open_count_ok = self.config.position_control.max_open_positions is None or len(positions) < self.config.position_control.max_open_positions
                entry_allowed = not daily_locked and not basket_losing and distance_ok and entry_time_ok and (cooldown_until is None or now >= cooldown_until) and open_count_ok
                if entry_allowed:
                    try:
                        plan = self.risk.plan(pending.side, entry_price, pending.atr, pending.swing_low, pending.swing_high, self.spec)
                        equity_before = starting_equity + realized_balance + sum(self._profit(item.side, item.entry, float(row.open), item.volume) for item in positions)
                        sizing = PositionSizer.calculate(equity_before, self.config.risk.risk_per_entry_percent, plan.entry, plan.stop_loss, self.spec, self.config.risk.max_lot_per_entry)
                        open_risk = sum(abs(item.entry - item.initial_stop) / self.spec.trade_tick_size * self.spec.trade_tick_value * item.volume for item in positions)
                        new_risk = sizing.loss_per_lot * sizing.volume
                        lot_ok = self.config.risk.max_total_lot is None or sum(item.volume for item in positions) + sizing.volume <= self.config.risk.max_total_lot + 1e-12
                        risk_ok = self.config.risk.max_basket_risk_percent is None or (open_risk + new_risk) / equity_before * 100 <= self.config.risk.max_basket_risk_percent + 1e-12
                        if lot_ok and risk_ok:
                            if active_basket is None:
                                active_basket = ActiveBasket(next_basket_id, pending.side.value, now)
                                next_basket_id += 1
                            elif active_basket.direction != pending.side.value and self.config.position_control.allow_opposite_positions:
                                active_basket.direction = "MIXED"
                            active_basket.initial_risk += new_risk
                            positions.append(SimPosition(next_ticket, active_basket.basket_id, pending.side.value, sizing.volume, sizing.volume, plan.entry, plan.stop_loss, plan.stop_loss, plan.take_profit, now, pending.score))
                            next_ticket += 1
                            last_entry_at = now
                        else:
                            rejected_count += 1
                    except OrderValidationError:
                        rejected_count += 1
                else:
                    rejected_count += 1
                pending = None

            # Conservative intrabar ordering: when both SL and TP are touched, SL wins.
            for position in list(positions):
                stop_hit = float(row.low) <= position.stop if position.side == "BUY" else float(row.high) >= position.stop
                target_hit = float(row.high) >= position.take_profit if position.side == "BUY" else float(row.low) <= position.take_profit
                if stop_hit or target_hit:
                    level = position.stop if stop_hit else position.take_profit
                    close_position(position, level, now, "STOP_LOSS" if stop_hit else "TAKE_PROFIT")
                    positions.remove(position)

            close_mid = float(row.close)
            floating = sum(self._profit(item.side, item.entry, close_mid, item.volume) for item in positions)
            if active_basket:
                basket_total = active_basket.realized + floating
                active_basket.maximum_profit = max(active_basket.maximum_profit, basket_total)
                active_basket.maximum_drawdown = max(active_basket.maximum_drawdown, active_basket.maximum_profit - basket_total)
                if positions and self.session.should_close_for_weekend(now):
                    close_basket(now, close_mid, spread_points, "WEEKEND")
                elif positions:
                    take = self.config.basket_take_profit
                    target = active_basket.initial_risk * take.target_r_multiple if take.mode.value == "R_MULTIPLE" else take.target_fixed_usd if take.mode.value == "FIXED_USD" else (starting_equity + realized_balance) * take.target_equity_percent / 100
                    loss_percent = (starting_equity + realized_balance) * self.config.basket_stop_loss.maximum_loss_percent / 100
                    if take.enabled and basket_total >= target:
                        close_basket(now, close_mid, spread_points, "TAKE_PROFIT")
                    elif self.config.basket_stop_loss.enabled and (basket_total <= -self.config.basket_stop_loss.maximum_loss_usd or basket_total <= -loss_percent):
                        close_basket(now, close_mid, spread_points, "STOP_LOSS")
                else:
                    reason = "TAKE_PROFIT" if active_basket.realized >= 0 else "STOP_LOSS"
                    close_basket(now, close_mid, spread_points, reason)

            # Stops and partial exits are based on the just-closed bar and affect only later bars.
            for position in list(positions):
                view = BrokerPosition(position.ticket, self.spec.name, position.side, position.volume, position.entry, close_mid, position.stop, position.take_profit, self._profit(position.side, position.entry, close_mid, position.volume), 0, "backtest", position.opened_at)
                be = self.break_even.evaluate(view, position.initial_stop, self.spec, position.break_even_applied)
                trail = self.trailing.evaluate(view, position.initial_stop, float(row.atr), self.spec)
                candidates = [item.new_stop for item in (be, trail) if item.should_update and item.new_stop is not None]
                if candidates:
                    position.stop = max(candidates) if position.side == "BUY" else min(candidates)
                    position.break_even_applied = position.break_even_applied or be.should_update
                partial = self.partial.evaluate(view, position.initial_volume, position.initial_stop, position.completed_levels, self.spec)
                if partial.should_close and partial.trigger_r is not None:
                    exit_price = price_with_cost(close_mid, position.side, spread_points, False)
                    close_position(position, exit_price, now, f"PARTIAL_R_{partial.trigger_r:g}", partial.volume)
                    position.completed_levels = tuple((*position.completed_levels, partial.trigger_r))

            floating = sum(self._profit(item.side, item.entry, close_mid, item.volume) for item in positions)
            equity_curve.append((now, starting_equity + realized_balance + floating))

            # Create a signal using only timeframe rows whose close timestamp is <= now.
            slices = {name: frame.iloc[: frame["time"].searchsorted(row.time, side="right")] for name, frame in frames.items()}
            if all(len(slices[name]) >= 2 for name in ("M5", "M15")) and len(slices["H1"]) >= 1 and len(slices["H4"]) >= 1:
                trend = self.trends.detect(slices["H4"], slices["H1"])
                if trend.direction in (TrendDirection.BULLISH, TrendDirection.BEARISH):
                    side = SignalSide.BUY if trend.direction is TrendDirection.BULLISH else SignalSide.SELL
                    latest15 = slices["M15"].iloc[-1]
                    evaluation = self.signals.evaluate(trend, slices["M15"], slices["M5"], self.config.take_profit.default_risk_reward)
                    signal_count += 1
                    no_opposite = self.config.position_control.allow_opposite_positions or not positions or all(item.side == side.value for item in positions)
                    session_allowed, _ = self.session.evaluate(now)
                    spread_ok = spread_points <= self.config.spread_guard.maximum_spread_points and spread_points * self.spec.point / float(latest15.atr) <= self.config.spread_guard.maximum_spread_atr_ratio
                    if evaluation.decision == "TRADE" and no_opposite and session_allowed and spread_ok:
                        pending = PendingSignal(side, float(latest15.atr), float(latest15.last_swing_low), float(latest15.last_swing_high), evaluation.score, now)
                    elif evaluation.decision != "TRADE":
                        rejected_count += 1

        if active_basket and len(m5):
            last = m5.iloc[-1]
            final_spread = float(last.spread)
            if not pd.notna(final_spread) or final_spread <= 0:
                final_spread = self.config.backtest.simulated_spread_points
            close_basket(last.time.to_pydatetime(), float(last.close), final_spread, "END_OF_TEST")
            equity_curve.append((last.time.to_pydatetime(), starting_equity + realized_balance))
        return BacktestResult(tuple(trades), tuple(baskets), tuple(equity_curve), signal_count, rejected_count)
