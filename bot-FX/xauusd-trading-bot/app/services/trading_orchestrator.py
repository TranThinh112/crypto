"""Two-loop trading runtime with deterministic entry and independent position management."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import delete, func, select

from app.broker.execution_service import ExecutionService, OrderIntent
from app.broker.mt5_client import BrokerClient, SymbolSpec
from app.config.settings import FOREX_SYMBOLS, BasketStopLossConfig, BasketTakeProfitConfig, DailyRiskConfig, HardTradeConfig, PositionControlConfig, TradingConfig, config_fingerprint
from app.database import Database
from app.guards.cooldown_guard import CooldownGuard
from app.guards.duplicate_order_guard import DuplicateOrderGuard
from app.guards.session_guard import SessionGuard
from app.guards.spread_guard import SpreadGuard
from app.market_data.candle_provider import CandleProvider
from app.market_data.indicator_service import IndicatorService
from app.models.basket import Basket
from app.models.bot_state import BotStateRecord, ConfigurationVersion, DailyStatistic, DataResetMarker
from app.models.event_log import IndicatorSnapshot, SignalDecision
from app.models.trade import ExecutionRequest, Trade, TradeEvent
from app.positions.basket_manager import BasketExitDecision, BasketManager, BasketMetrics
from app.positions.position_manager import PositionManager
from app.risk.daily_risk_guard import DailyRiskGuard, DailyRiskSnapshot
from app.risk.position_sizing import PositionSizer, SizingResult
from app.risk.risk_manager import PricePlan, RiskManager
from app.strategy.candlestick_patterns import detect_candlestick_patterns
from app.services.health_service import HealthService
from app.services.recovery_service import RecoveryService
from app.strategy.entry_validator import EntryContext, EntryValidator
from app.strategy.exit_signal_engine import ExitSignalEngine
from app.strategy.signal_engine import SignalEngine, SignalEvaluation
from app.strategy.trend_detector import RuleResult, TrendAssessment, TrendDetector
from app.utils.enums import BasketState, BotState, CloseReason, SignalSide, TradeState, TrendDirection
from app.utils.exceptions import OrderValidationError, TradingBotError
from app.utils.calculations import normalize_price
from app.utils.time_utils import ensure_utc


class TradingOrchestrator:
    """Runs signal and position management in separate threads and failure domains."""

    TRADING_DAY_START_HOUR = 7
    LOCAL_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")

    def __init__(
        self,
        database: Database,
        broker: BrokerClient,
        config: TradingConfig,
        symbol: str,
        spec: SymbolSpec,
        live_enabled: bool,
        project_path: Path,
        portfolio_symbols: tuple[str, ...] | None = None,
    ) -> None:
        self.database = database
        self.broker = broker
        self.config = config
        self.symbol = symbol
        self.portfolio_symbols = portfolio_symbols or (symbol,)
        self.spec = spec
        self.execution = ExecutionService(broker, database, config, live_enabled)
        self.candles = CandleProvider(broker)
        self.indicators = IndicatorService(config.strategy)
        self.trend_detector = TrendDetector(config.strategy)
        self.signal_engine = SignalEngine(config.strategy, config.signal_scoring, config.take_profit)
        self.risk_manager = RiskManager(config.stop_loss, config.take_profit)
        self.entry_validator = EntryValidator(config.position_control, config.risk)
        self.exit_signal_engine = ExitSignalEngine()
        self.daily_guard = DailyRiskGuard(config.daily_risk)
        self.session_guard = SessionGuard(config.session)
        self.spread_guard = SpreadGuard(config.spread_guard)
        self.cooldown_guard = CooldownGuard(database, config.cooldown, symbol)
        self.duplicate_guard = DuplicateOrderGuard(database)
        self.basket_manager = BasketManager(database, broker, self.execution, config, symbol, spec)
        self.position_manager = PositionManager(database, self.execution, config, spec)
        self.recovery = RecoveryService(database, broker, config, symbol, spec)
        self.health = HealthService(database, broker, symbol, project_path)
        self.project_path = project_path
        self._state = BotState.STOPPED
        self._state_reason: str | None = None
        self._manual_pause = False
        self._stop_event = threading.Event()
        self._signal_lock = threading.Lock()
        self._recovery_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._threads: list[threading.Thread] = []
        self._last_signal_candle: datetime | None = None
        self._last_scalp_candle: datetime | None = None
        self._last_management_candle: datetime | None = None
        self._last_history_cleanup_at: datetime | None = None
        self._latest_management_atr: float | None = None
        self._pending_trend_reversal = False
        self.log = logging.getLogger("trading")

    def _learning_export_paths(self) -> tuple[Path, Path]:
        data_dir = self.project_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "learning_export.jsonl", data_dir / "learning_export_state.json"

    def _learning_export_state(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _timeframe_from_key(key: str) -> str | None:
        for timeframe in ("M1", "M5", "M15", "M30"):
            if f"_{timeframe}_" in key:
                return timeframe
        return None

    def _learning_session_bucket(self, value: datetime | None = None) -> int | None:
        if value is None:
            value = datetime.now(UTC)
        value = ensure_utc(value).astimezone(self.LOCAL_TIMEZONE)
        hours = max(1, int(self.config.adaptive_learning.session_bucket_hours))
        return value.hour // hours * hours

    def _learning_record_for_trade(self, trade: Trade) -> dict[str, Any]:
        pnl = float(self._closed_trade_profit(trade))
        return {
            "version": 1,
            "exported_at": datetime.now(UTC).isoformat(),
            "trade_id": trade.id,
            "broker_ticket": trade.broker_ticket,
            "basket_id": trade.basket_id,
            "symbol": trade.symbol,
            "side": trade.side,
            "timeframe": self._timeframe_from_key(trade.idempotency_key),
            "setup_fingerprint": trade.signal_hash,
            "idempotency_key": trade.idempotency_key,
            "estimated_win_rate": trade.estimated_win_rate,
            "entry_candle_time": ensure_utc(trade.entry_candle_time).isoformat() if trade.entry_candle_time else None,
            "opened_at": ensure_utc(trade.opened_at).isoformat() if trade.opened_at else None,
            "closed_at": ensure_utc(trade.closed_at).isoformat() if trade.closed_at else None,
            "entry_price": trade.entry_price,
            "initial_stop_loss": trade.initial_stop_loss,
            "take_profit": trade.take_profit,
            "initial_volume": trade.initial_volume,
            "entry_number": trade.entry_number,
            "initial_risk_amount": trade.initial_risk_amount,
            "max_adverse_profit": trade.max_adverse_profit,
            "max_favorable_profit": trade.max_favorable_profit,
            "max_adverse_r": trade.max_adverse_r,
            "max_favorable_r": trade.max_favorable_r,
            "realized_profit": pnl,
            "floating_profit": trade.floating_profit,
            "outcome": "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "FLAT",
            "close_reason": trade.close_reason,
            "break_even_applied": trade.break_even_applied,
        }

    def _export_learning_records(self) -> None:
        export_path, state_path = self._learning_export_paths()
        state = self._learning_export_state(state_path)
        key = self.symbol
        last_id = int(state.get("last_exported_trade_id_by_symbol", {}).get(key, 0))
        with self.database.transaction() as session:
            trades = list(session.scalars(
                select(Trade)
                .where(
                    Trade.symbol == self.symbol,
                    Trade.state == TradeState.CLOSED.value,
                    Trade.closed_at.is_not(None),
                    Trade.id > last_id,
                )
                .order_by(Trade.id.asc())
            ))
        if not trades:
            return
        exported = 0
        with export_path.open("a", encoding="utf-8") as handle:
            for trade in trades:
                handle.write(json.dumps(self._learning_record_for_trade(trade), ensure_ascii=False, sort_keys=True) + "\n")
                last_id = max(last_id, int(trade.id))
                exported += 1
        by_symbol = dict(state.get("last_exported_trade_id_by_symbol", {}))
        by_symbol[key] = last_id
        state = {
            **state,
            "last_exported_trade_id_by_symbol": by_symbol,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        self.log.info(
            "Exported learning records",
            extra={"event_type": "LEARNING_EXPORT", "symbol": self.symbol, "context": {"exported": exported, "path": str(export_path)}},
        )

    def _project_storage_bytes(self) -> int:
        total = 0
        for path in self.project_path.rglob("*"):
            if path.is_file():
                try:
                    total += path.stat().st_size
                except OSError:
                    continue
        return total

    def _cleanup_project_storage_cap(self) -> None:
        limit = self.config.data_retention.max_project_storage_mb * 1024 * 1024
        total = self._project_storage_bytes()
        if total <= limit:
            return
        target = int(limit * 0.9)
        candidates: list[Path] = []
        for folder, patterns in (
            (self.project_path / "data" / "backups", ("*.db", "*.sqlite", "*.sqlite3")),
            (self.project_path / "data", ("*.log", "*.json")),
            (self.project_path / "logs", ("*.log",)),
        ):
            for pattern in patterns:
                candidates.extend(path for path in folder.glob(pattern) if path.is_file())
        learning_export_path, learning_state_path = self._learning_export_paths()
        protected = {
            (self.project_path / "data" / "trading_bot.db").resolve(),
            learning_export_path.resolve(),
            learning_state_path.resolve(),
        }
        removed = 0
        for path in sorted(candidates, key=lambda item: item.stat().st_mtime):
            try:
                resolved = path.resolve()
                if resolved in protected:
                    continue
                size = path.stat().st_size
                path.unlink()
                total -= size
                removed += 1
            except OSError:
                continue
            if total <= target:
                break
        if removed:
            self.log.warning(
                "Project storage cap cleanup removed auxiliary files",
                extra={"event_type": "STORAGE_CAP_CLEANUP", "symbol": self.symbol, "context": {"removed_files": removed, "remaining_bytes": total}},
            )

    def _truncate_log_file(self, path: Path, max_bytes: int) -> bool:
        try:
            if not path.is_file() or path.stat().st_size <= max_bytes:
                return False
            keep_bytes = max(1024, max_bytes // 2)
            with path.open("rb") as handle:
                handle.seek(max(0, path.stat().st_size - keep_bytes))
                data = handle.read()
            path.write_bytes(data)
            return True
        except OSError:
            return False

    def _cleanup_auxiliary_data_files(self) -> None:
        retention = self.config.data_retention
        now = datetime.now(UTC)
        auxiliary_cutoff = now - timedelta(days=retention.auxiliary_file_retention_days)
        backup_cutoff = now - timedelta(days=retention.backup_retention_days)
        protected = {
            (self.project_path / "data" / "trading_bot.db").resolve(),
            self._learning_export_paths()[0].resolve(),
            self._learning_export_paths()[1].resolve(),
        }
        patterns = (
            (self.project_path / "data", ("hard_trade_monitor*.log", "hard_trade_monitor*.json", "dashboard_*.html", "dashboard_*.js"), auxiliary_cutoff),
            (self.project_path / "data" / "backups", ("*.db", "*.sqlite", "*.sqlite3"), backup_cutoff),
        )
        max_auxiliary_bytes = retention.auxiliary_file_max_mb * 1024 * 1024
        removed = 0
        for folder, globs, cutoff in patterns:
            for glob in globs:
                for path in folder.glob(glob):
                    try:
                        if not path.is_file() or path.resolve() in protected:
                            continue
                        stat = path.stat()
                        is_old = datetime.fromtimestamp(stat.st_mtime, UTC) < cutoff
                        is_oversized_auxiliary = folder.name == "data" and stat.st_size > max_auxiliary_bytes
                        if is_old or is_oversized_auxiliary:
                            path.unlink()
                            removed += 1
                    except OSError:
                        continue
        truncated = 0
        max_log_bytes = retention.log_file_max_mb * 1024 * 1024
        for path in (self.project_path / "logs").glob("*.log"):
            if self._truncate_log_file(path, max_log_bytes):
                truncated += 1
        if removed or truncated:
            self.log.info(
                "Cleaned auxiliary data files",
                extra={"event_type": "DATA_RETENTION_CLEANUP", "symbol": self.symbol, "context": {"removed_files": removed, "truncated_logs": truncated}},
            )

    def _vacuum_sqlite_database(self) -> None:
        if self.database.engine.dialect.name != "sqlite":
            return
        database_path = self.database.engine.url.database
        if not database_path or database_path == ":memory:":
            return
        path = Path(database_path)
        if not path.exists():
            return
        try:
            with sqlite3.connect(path) as connection:
                connection.execute("VACUUM")
        except sqlite3.Error as exc:
            self.log.warning("SQLite vacuum failed", extra={"event_type": "SQLITE_VACUUM_FAILED", "symbol": self.symbol, "context": {"error": str(exc)}})

    def _cleanup_old_closed_trades(self) -> None:
        retention = self.config.data_retention.closed_trade_retention_days
        interval = self.config.data_retention.cleanup_interval_seconds
        now = datetime.now(UTC)
        if self._last_history_cleanup_at is not None and now - self._last_history_cleanup_at < timedelta(seconds=interval):
            return
        self._last_history_cleanup_at = now
        cutoff = now - timedelta(days=retention)
        signal_cutoff = now - timedelta(days=self.config.data_retention.rejected_signal_retention_days)
        indicator_cutoff = now - timedelta(days=self.config.data_retention.indicator_snapshot_retention_days)
        self._export_learning_records()
        old_trade_ids = select(Trade.id).where(
            Trade.state == TradeState.CLOSED.value,
            Trade.closed_at.is_not(None),
            Trade.closed_at < cutoff,
        )
        with self.database.transaction() as session:
            session.execute(delete(TradeEvent).where(TradeEvent.trade_id.in_(old_trade_ids)))
            session.execute(delete(ExecutionRequest).where(ExecutionRequest.trade_id.in_(old_trade_ids)))
            session.execute(delete(Trade).where(Trade.id.in_(old_trade_ids)))
            session.execute(delete(SignalDecision).where(
                SignalDecision.decision == "NO_TRADE",
                SignalDecision.timestamp < signal_cutoff,
            ))
            session.execute(delete(IndicatorSnapshot).where(IndicatorSnapshot.timestamp < indicator_cutoff))
        self._cleanup_auxiliary_data_files()
        self._vacuum_sqlite_database()
        self._cleanup_project_storage_cap()

    @staticmethod
    def _is_forex_base(symbol: str) -> bool:
        return symbol in FOREX_SYMBOLS

    @staticmethod
    def _matches_base_symbol(symbol: str, base: str) -> bool:
        return symbol.upper().startswith(base)

    def _is_forex_runtime_symbol(self, symbol: str | None = None) -> bool:
        value = (symbol or self.symbol).upper()
        return any(self._matches_base_symbol(value, base) for base in self.config.forex_trading.symbols)

    def _forex_runtime_symbols(self) -> tuple[str, ...]:
        return tuple(
            symbol for symbol in self.portfolio_symbols
            if self._is_forex_runtime_symbol(symbol)
        )

    def _trading_day_start(self, now: datetime) -> datetime:
        local_now = ensure_utc(now).astimezone(self.LOCAL_TIMEZONE)
        local_start = local_now.replace(
            hour=self.TRADING_DAY_START_HOUR,
            minute=0,
            second=0,
            microsecond=0,
        )
        if local_now < local_start:
            local_start -= timedelta(days=1)
        return local_start.astimezone(UTC)

    def _trading_day_date(self, now: datetime) -> datetime.date:
        return self._trading_day_start(now).astimezone(self.LOCAL_TIMEZONE).date()

    def update_daily_risk(self, daily_risk: DailyRiskConfig) -> None:
        """Apply changed daily target/loss limits without recreating the broker runtime."""
        self.config = self.config.model_copy(update={"daily_risk": daily_risk})
        self.daily_guard = DailyRiskGuard(daily_risk)
        self.basket_manager.config = self.config

    def update_basket_take_profit(self, basket_take_profit: BasketTakeProfitConfig) -> None:
        self.config = self.config.model_copy(update={"basket_take_profit": basket_take_profit})
        self.basket_manager.config = self.config

    def update_basket_stop_loss(self, basket_stop_loss: BasketStopLossConfig) -> None:
        self.config = self.config.model_copy(update={"basket_stop_loss": basket_stop_loss})
        self.basket_manager.config = self.config

    def update_hard_trade(self, hard_trade: HardTradeConfig) -> None:
        self.config = self.config.model_copy(update={"hard_trade": hard_trade})
        self.execution.config = self.config
        self.entry_validator = EntryValidator(self.config.position_control, self.config.risk)
        self.basket_manager.config = self.config
        self.position_manager.config = self.config

    def update_position_control(self, position_control: PositionControlConfig) -> None:
        self.config = self.config.model_copy(update={"position_control": position_control})
        self.entry_validator = EntryValidator(position_control, self.config.risk)
        self.execution.config = self.config
        self.basket_manager.config = self.config
        self.position_manager.config = self.config

    @property
    def state(self) -> BotState:
        with self._state_lock:
            return self._state

    @property
    def state_reason(self) -> str | None:
        with self._state_lock:
            return self._state_reason

    def _set_state(self, state: BotState, reason: str, details: dict[str, Any] | None = None) -> None:
        with self._state_lock:
            if self._state is state and self._state_reason == reason:
                return
            self._state, self._state_reason = state, reason
        with self.database.transaction() as session:
            session.add(BotStateRecord(state=state.value, reason=reason, details=details or {}))
        self.log.info("Bot state changed", extra={"event_type": "BOT_STATE", "symbol": self.symbol, "bot_state": state.value, "context": {"reason": reason, **(details or {})}})

    def _store_configuration(self) -> None:
        fingerprint = config_fingerprint(self.config)
        with self.database.transaction() as session:
            existing = session.scalar(select(ConfigurationVersion).where(ConfigurationVersion.fingerprint == fingerprint))
            if existing is None:
                session.add(ConfigurationVersion(fingerprint=fingerprint, content=self.config.model_dump(mode="json"), note="startup"))

    def _manual_pause_was_requested(self) -> bool:
        with self.database.transaction() as session:
            record = session.scalar(select(BotStateRecord).order_by(BotStateRecord.timestamp.desc(), BotStateRecord.id.desc()).limit(1))
        return record is not None and record.state == BotState.ENTRY_PAUSED.value and record.reason in ("MANUAL_PAUSE", "MANUAL_PAUSE_RESTORED")

    def start(self) -> None:
        with self._state_lock:
            if self._state not in (BotState.STOPPED, BotState.ERROR):
                return
        restore_manual_pause = self._manual_pause_was_requested()
        self._set_state(BotState.STARTING, "START_REQUESTED")
        self._manual_pause = restore_manual_pause
        self._stop_event.clear()
        try:
            if not self.broker.is_connected():
                self.broker.connect()
            self._store_configuration()
            result = self.recovery.reconcile()
            self.health.set_broker_synchronized(result.consistent)
            if result.consistent:
                self._hard_restart_emergency_exit()
            if result.consistent and restore_manual_pause:
                self._set_state(BotState.ENTRY_PAUSED, "MANUAL_PAUSE_RESTORED")
            else:
                self._set_state(BotState.RUNNING if result.consistent else BotState.ENTRY_PAUSED, result.message)
            self._threads = [
                threading.Thread(target=self._signal_loop, name="xau-signal-loop", daemon=True),
                threading.Thread(target=self._position_loop, name="xau-position-loop", daemon=True),
            ]
            for thread in self._threads:
                thread.start()
        except Exception as exc:
            self.health.record("startup", "ERROR", "Bot startup failed", {"error": str(exc)})
            self._set_state(BotState.ERROR, "STARTUP_FAILED", {"error": str(exc)})
            raise

    def stop(self) -> None:
        self._manual_pause = True
        if self.state is not BotState.STOPPED:
            self._set_state(BotState.ENTRY_PAUSED, "STOPPING")
        self._stop_event.set()
        for thread in self._threads:
            thread.join(timeout=10)
        self._threads.clear()
        try:
            self.broker.disconnect()
        finally:
            self._set_state(BotState.STOPPED, "STOP_REQUESTED")

    def pause_entry(self, reason: str = "MANUAL_PAUSE") -> None:
        self._manual_pause = True
        self._set_state(BotState.ENTRY_PAUSED, reason)

    def resume_entry(self) -> bool:
        if not self.health.snapshot()["broker_synchronized"]:
            return False
        self._manual_pause = False
        self._set_state(BotState.RUNNING, "MANUAL_RESUME")
        return True

    def close_basket_manually(self, basket_external_id: str, reason: str) -> bool:
        """Closes only the tracked bot basket; manual/user positions remain untouched."""
        self._set_state(BotState.CLOSING_BASKET, reason)
        closed = self.basket_manager.close_basket(basket_external_id, CloseReason.MANUAL)
        if closed:
            self.cooldown_guard.activate(CloseReason.MANUAL, basket_external_id)
            self._set_state(BotState.COOLDOWN, f"MANUAL_CLOSE:{reason}")
        else:
            self._set_state(BotState.ENTRY_PAUSED, "MANUAL_BASKET_CLOSE_FAILED")
        return closed

    def close_all_manually(self, reason: str) -> bool:
        baskets = self._active_baskets()
        return all(self.close_basket_manually(basket.external_id, reason) for basket in baskets)

    def _hard_restart_emergency_exit(self) -> None:
        hard = self.config.hard_trade
        if not hard.enabled or not hard.emergency_exit_on_restart:
            return
        try:
            account = self.broker.account()
            for basket in self._active_baskets():
                positions = self.basket_manager.basket_positions(basket.external_id)
                if not positions:
                    continue
                metrics = self.basket_manager.synchronize(basket.external_id)
                with self.database.transaction() as session:
                    trades = list(session.scalars(select(Trade).where(
                        Trade.basket_id == basket.id,
                        Trade.state.in_((TradeState.OPEN.value, TradeState.PARTIALLY_CLOSED.value)),
                    )))
                    max_adverse_r = max((float(trade.max_adverse_r or 0.0) for trade in trades), default=0.0)
                loss_threshold = min(
                    hard.emergency_exit_max_loss_usd,
                    self.basket_manager.basket_stop_loss_threshold(account.equity) or hard.emergency_exit_max_loss_usd,
                )
                should_close = metrics.combined_profit <= -loss_threshold or max_adverse_r >= hard.emergency_exit_max_adverse_r
                if not should_close:
                    self.health.record("restart_care", "OK", "Restart emergency check passed", {
                        "basket": basket.external_id,
                        "profit": metrics.combined_profit,
                        "loss_threshold": loss_threshold,
                        "max_adverse_r": max_adverse_r,
                    })
                    continue
                self._set_state(BotState.CLOSING_BASKET, "HARD_RESTART_EMERGENCY_EXIT", {
                    "basket": basket.external_id,
                    "profit": metrics.combined_profit,
                    "loss_threshold": loss_threshold,
                    "max_adverse_r": max_adverse_r,
                })
                closed = self.basket_manager.close_basket(basket.external_id, CloseReason.STOP_LOSS)
                self.health.record("restart_care", "WARNING" if closed else "ERROR", "Hard restart emergency exit", {
                    "basket": basket.external_id,
                    "closed": closed,
                    "profit": metrics.combined_profit,
                    "loss_threshold": loss_threshold,
                    "max_adverse_r": max_adverse_r,
                })
        except Exception as exc:
            self.log.exception("Restart emergency exit failed", extra={"event_type": "HARD_RESTART_EMERGENCY_EXIT_ERROR", "symbol": self.symbol, "context": {"error": str(exc)}})
            self.health.record("restart_care", "ERROR", "Restart emergency exit failed", {"error": str(exc)})

    def _signal_loop(self) -> None:
        while not self._stop_event.is_set():
            self.health.heartbeat("signal_loop")
            try:
                self.signal_cycle()
            except Exception as exc:
                self.log.exception("Signal loop error", extra={"event_type": "SIGNAL_LOOP_ERROR", "symbol": self.symbol, "bot_state": self.state.value, "context": {"error": str(exc)}})
                self.health.record("signal_loop", "ERROR", "Unhandled signal-loop exception", {"error": str(exc)})
                if self.state not in (BotState.STOPPED, BotState.CLOSING_BASKET):
                    self._set_state(BotState.ENTRY_PAUSED, "SIGNAL_LOOP_ERROR", {"error": str(exc)})
            self._stop_event.wait(self._scan_interval_seconds())

    def _position_loop(self) -> None:
        while not self._stop_event.is_set():
            self.health.heartbeat("position_manager")
            try:
                self.position_cycle()
            except Exception as exc:
                self.log.exception("Position loop error", extra={"event_type": "POSITION_LOOP_ERROR", "symbol": self.symbol, "bot_state": self.state.value, "context": {"error": str(exc)}})
                self.health.record("position_manager", "ERROR", "Unhandled position-loop exception", {"error": str(exc)})
                self.health.set_broker_synchronized(False)
                if self.state is not BotState.STOPPED:
                    self._set_state(BotState.ENTRY_PAUSED, "POSITION_LOOP_ERROR", {"error": str(exc)})
            self._stop_event.wait(self._position_monitor_interval_seconds())

    def _scan_interval_seconds(self) -> float:
        return self.config.hard_trade.scan_interval_seconds if self.config.hard_trade.enabled else self.config.bot.scan_interval_seconds

    def _position_monitor_interval_seconds(self) -> float:
        return self.config.hard_trade.position_monitor_interval_seconds if self.config.hard_trade.enabled else self.config.bot.position_monitor_interval_seconds

    def _ensure_connection(self) -> bool:
        if self.broker.is_connected():
            return True
        self.health.set_broker_synchronized(False)
        with self._recovery_lock:
            try:
                self.broker.connect()
                result = self.recovery.reconcile()
                self.health.set_broker_synchronized(result.consistent)
                if result.consistent and not self._manual_pause:
                    self._set_state(BotState.RUNNING, "RECONNECTED_AND_RECONCILED")
                return result.consistent
            except Exception as exc:
                self.health.record("mt5", "ERROR", "Reconnect failed", {"error": str(exc)})
                return False

    def _daily_accounting_window(self, now: datetime) -> tuple[datetime, int | None, float | None]:
        day_start = self._trading_day_start(now)
        with self.database.transaction() as session:
            marker = session.scalar(
                select(DataResetMarker)
                .where(DataResetMarker.reset_at >= day_start, DataResetMarker.reset_at <= now)
                .order_by(DataResetMarker.reset_at.desc(), DataResetMarker.id.desc())
                .limit(1)
            )
        if marker is None:
            return day_start, None, None
        return max(day_start, ensure_utc(marker.reset_at)), marker.id, marker.starting_equity

    def _daily_status(self, now: datetime) -> tuple[bool, DailyStatistic, tuple[RuleResult, ...]]:
        account = self.broker.account()
        day_start = self._trading_day_start(now)
        trading_date = self._trading_day_date(now)
        start, reset_marker_id, reset_starting_equity = self._daily_accounting_window(now)
        has_intraday_reset = start > day_start
        deals = [
            deal
            for symbol in self.portfolio_symbols
            for deal in self.broker.deals(start, now, symbol, self.config.broker.magic_number)
        ]
        exit_ids = {item.position_id for item in deals if item.entry in ("OUT", "INOUT", "OUT_BY")}
        all_monetary: dict[int, float] = {}
        last_exit: dict[int, datetime] = {}
        for deal in deals:
            all_monetary[deal.position_id] = all_monetary.get(deal.position_id, 0) + deal.profit + deal.commission + deal.swap
            if deal.position_id in exit_ids:
                last_exit[deal.position_id] = max(last_exit.get(deal.position_id, deal.time), deal.time)
        grouped = {position_id: all_monetary[position_id] for position_id in exit_ids}
        ordered = [grouped[key] for key in sorted(grouped, key=lambda value: last_exit[value])]
        consecutive = 0
        for result in reversed(ordered):
            if result < 0:
                consecutive += 1
            else:
                break
        positions = [
            position
            for symbol in self.portfolio_symbols
            for position in self.broker.positions(symbol, self.config.broker.magic_number)
        ]
        floating = account.equity - account.balance
        with self.database.transaction() as session:
            record = session.scalar(select(DailyStatistic).where(DailyStatistic.trading_date == trading_date))
            # Use the account balance as the authoritative realized PnL source.
            # This keeps today's PnL aligned with the 7:00 AM trading-day cutoff:
            # realized = closed PnL since the cutoff, floating = open PnL now.
            derived_start = max(0.01, account.balance - sum(grouped.values()))
            reset_marker = session.get(DataResetMarker, reset_marker_id) if reset_marker_id is not None else None
            if reset_marker is not None and reset_marker.starting_equity is None:
                existing_baseline = None
                if record is not None and record.updated_at is not None and reset_marker.created_at is not None:
                    if ensure_utc(record.updated_at) >= ensure_utc(reset_marker.created_at):
                        existing_baseline = record.starting_equity
                reset_marker.starting_equity = max(0.01, existing_baseline if existing_baseline is not None else derived_start)
                reset_starting_equity = reset_marker.starting_equity
            baseline = max(0.01, reset_starting_equity if reset_starting_equity is not None else derived_start)
            if record is None:
                record = DailyStatistic(trading_date=trading_date, starting_equity=baseline)
                session.add(record)
                session.flush()
            elif has_intraday_reset and not math.isclose(record.starting_equity, baseline, rel_tol=0.0, abs_tol=0.000001):
                record.starting_equity = baseline
                record.maximum_drawdown = max(0.0, record.starting_equity - account.equity)
            estimated_events = list(session.scalars(
                select(TradeEvent)
                .join(Trade, TradeEvent.trade_id == Trade.id)
                .where(
                    TradeEvent.event_type == "BROKER_EXIT_ESTIMATED",
                    Trade.closed_at >= start,
                    Trade.symbol.in_(self.portfolio_symbols),
                )
            ))
            actual_trade_ids = set(session.scalars(
                select(TradeEvent.trade_id)
                .join(Trade, TradeEvent.trade_id == Trade.id)
                .where(
                    TradeEvent.event_type == "BROKER_DEAL_RECONCILED",
                    TradeEvent.details["entry"].as_string().in_(("OUT", "INOUT", "OUT_BY")),
                    Trade.closed_at >= start,
                    Trade.symbol.in_(self.portfolio_symbols),
                )
            ))
            estimated_correction = sum(
                float(event.details.get("monetary", 0.0))
                for event in estimated_events
                if event.trade_id not in actual_trade_ids
            )
            broker_realized = sum(grouped.values()) + estimated_correction
            closed_trade_values = [
                float(value or 0.0)
                for value in session.scalars(
                    select(Trade.realized_profit).where(
                        Trade.state == TradeState.CLOSED.value,
                        Trade.closed_at.is_not(None),
                        Trade.closed_at >= start,
                    )
                )
            ]
            closed_trade_realized = sum(closed_trade_values)
            if not closed_trade_values:
                closed_trade_realized = float(session.scalar(
                    select(func.coalesce(func.sum(Trade.realized_profit), 0.0)).where(
                        Trade.state == TradeState.CLOSED.value,
                        Trade.closed_at.is_not(None),
                        Trade.closed_at >= start,
                    )
                ) or 0.0)
            realized = closed_trade_realized if not math.isclose(closed_trade_realized, 0.0, rel_tol=0.0, abs_tol=1e-12) else broker_realized if grouped or estimated_correction else account.balance - baseline
            record.realized_pnl = realized
            record.floating_pnl = floating
            record.maximum_drawdown = max(record.maximum_drawdown, max(0.0, record.starting_equity - account.equity))
            estimated_results = [float(event.details.get("monetary", 0.0)) for event in estimated_events if event.trade_id not in actual_trade_ids]
            daily_results = closed_trade_values or (ordered + estimated_results)
            estimated_consecutive = 0
            for result in reversed(daily_results):
                if result < 0:
                    estimated_consecutive += 1
                else:
                    break
            record.trade_count = len(daily_results)
            record.winning_trades = sum(value > 0 for value in daily_results)
            record.losing_trades = sum(value < 0 for value in daily_results)
            record.consecutive_losses = max(consecutive, estimated_consecutive)
            snapshot = DailyRiskSnapshot(record.starting_equity, realized, floating, record.consecutive_losses)
            allowed, rules = self.daily_guard.evaluate(snapshot)
            record.entry_locked = not allowed
            record.lock_reason = next((rule.reason_code for rule in rules if not rule.passed), None)
            return allowed, record, rules

    @staticmethod
    def _json_number(value: Any) -> float | None:
        try:
            result = float(value)
            return result if math.isfinite(result) else None
        except (TypeError, ValueError):
            return None

    def _store_indicators(self, frames: dict[str, pd.DataFrame]) -> None:
        keys = ("ema20", "ema50", "ema200", "rsi", "atr", "adx", "macd", "macd_signal", "macd_hist", "last_swing_high", "last_swing_low", "average_candle_range", "volume")
        with self.database.transaction() as session:
            for timeframe, frame in frames.items():
                row = frame.iloc[-1]
                values = {key: self._json_number(row.get(key)) for key in keys}
                session.add(IndicatorSnapshot(symbol=self.symbol, timeframe=timeframe, candle_time=row.time.to_pydatetime() if hasattr(row.time, "to_pydatetime") else row.time, values=values))

    def _persist_decision(
        self,
        trend: TrendDirection,
        evaluation: SignalEvaluation | None,
        rules: tuple[RuleResult, ...],
        decision: str,
        rejection: str | None,
        tick: Any | None = None,
        row: Any | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        risk_reward: float | None = None,
    ) -> None:
        spread = (tick.ask - tick.bid) / self.spec.point if tick is not None else None
        side = evaluation.side.value if evaluation else SignalSide.NO_TRADE.value
        signal_hash = evaluation.signal_hash if evaluation else hashlib.sha256(f"{datetime.now(UTC).isoformat()}:{rejection}".encode()).hexdigest()[:24]
        with self.database.transaction() as session:
            session.add(SignalDecision(
                symbol=self.symbol, trend=trend.value, side=side, score=evaluation.score if evaluation else 0,
                rule_results=[rule.as_dict() for rule in rules], spread=spread,
                atr=self._json_number(row.atr) if row is not None else None,
                rsi=self._json_number(row.rsi) if row is not None else None,
                adx=self._json_number(row.adx) if row is not None else None,
                entry_price=(tick.ask if evaluation and evaluation.side is SignalSide.BUY else tick.bid) if tick is not None and evaluation else None,
                stop_loss=stop_loss, take_profit=take_profit, risk_reward=risk_reward,
                decision=decision, rejection_reason=rejection, signal_hash=signal_hash,
            ))

    def _active_baskets(self) -> list[Basket]:
        return self.basket_manager.active_baskets()

    def _active_basket(self, side: str | None = None) -> Basket | None:
        with self.database.transaction() as session:
            query = select(Basket).where(
                Basket.symbol == self.symbol,
                Basket.status.in_((BasketState.ACTIVE.value, BasketState.CLOSING.value, BasketState.CLOSE_FAILED.value)),
            )
            if side is not None:
                query = query.where(Basket.direction.in_((side, "MIXED")))
            return session.scalar(query)

    @staticmethod
    def _daily_close_trigger(rules: tuple[RuleResult, ...]) -> tuple[CloseReason | None, float | None]:
        for rule in rules:
            if rule.passed:
                continue
            if rule.reason_code == "DAILY_PROFIT_TARGET":
                return CloseReason.TAKE_PROFIT, rule.details.get("target")
            if rule.reason_code == "DAILY_LOSS_LIMIT":
                return CloseReason.STOP_LOSS, rule.details.get("limit")
        return None, None

    def _fast_scalp_evaluation(self, m1: pd.DataFrame, trend: TrendAssessment) -> SignalEvaluation:
        latest, previous = m1.iloc[-1], m1.iloc[-2]

        def score_for(side: SignalSide) -> tuple[int, tuple[RuleResult, ...], dict[str, Any]]:
            is_buy = side is SignalSide.BUY
            patterns = detect_candlestick_patterns(m1, side)
            candle_ok = patterns.confirmed or not self.config.fast_scalp.require_candle_confirmation
            ema20_ok = bool(latest.close > latest.ema20) if is_buy else bool(latest.close < latest.ema20)
            ema50_ok = bool(latest.close > latest.ema50) if is_buy else bool(latest.close < latest.ema50)
            macd_ok = bool(latest.macd_hist > previous.macd_hist) if is_buy else bool(latest.macd_hist < previous.macd_hist)
            rsi_ok = bool(latest.rsi >= 50) if is_buy else bool(latest.rsi <= 50)
            body = abs(float(latest.close - latest.open))
            impulse_ok = body >= max(float(latest.average_body), 1e-12)
            countertrend_reversal = self.config.fast_scalp.countertrend_reversal_enabled and (
                (
                    side is SignalSide.SELL
                    and trend.direction is TrendDirection.BULLISH
                    and float(latest.rsi) >= self.config.fast_scalp.overbought_rsi
                    and candle_ok
                    and macd_ok
                )
                or (
                    side is SignalSide.BUY
                    and trend.direction is TrendDirection.BEARISH
                    and float(latest.rsi) <= self.config.fast_scalp.oversold_rsi
                    and candle_ok
                    and macd_ok
                )
            )
            rules = (
                RuleResult(candle_ok, "M1_SCALP_CANDLE_CONFIRMATION", {
                    "supportive": list(patterns.supportive),
                    "opposing": list(patterns.opposing),
                    "neutral": list(patterns.neutral),
                }, 30),
                RuleResult(macd_ok, "M1_SCALP_MACD_MOMENTUM", {"current": float(latest.macd_hist), "previous": float(previous.macd_hist)}, 25),
                RuleResult(ema20_ok, "M1_SCALP_EMA20_SIDE", {"close": float(latest.close), "ema20": float(latest.ema20)}, 15),
                RuleResult(ema50_ok, "M1_SCALP_EMA50_SIDE", {"close": float(latest.close), "ema50": float(latest.ema50)}, 10),
                RuleResult(rsi_ok, "M1_SCALP_RSI_SIDE", {"rsi": float(latest.rsi)}, 10),
                RuleResult(impulse_ok, "M1_SCALP_IMPULSE_BODY", {"body": body, "average_body": float(latest.average_body)}, 10),
                RuleResult(countertrend_reversal, "M1_SCALP_COUNTERTREND_REVERSAL", {
                    "rsi": float(latest.rsi),
                    "overbought": self.config.fast_scalp.overbought_rsi,
                    "oversold": self.config.fast_scalp.oversold_rsi,
                    "trend": trend.direction.value,
                    "candle_confirmed": candle_ok,
                    "macd_fading": macd_ok,
                }, 25),
            )
            return sum(rule.points for rule in rules if rule.passed), rules, {
                "supportive_patterns": list(patterns.supportive),
                "opposing_patterns": list(patterns.opposing),
                "neutral_patterns": list(patterns.neutral),
                "candle_time": str(latest.time),
                "atr": float(latest.atr),
                "rsi": float(latest.rsi),
            }

        buy_score, buy_rules, buy_details = score_for(SignalSide.BUY)
        sell_score, sell_rules, sell_details = score_for(SignalSide.SELL)
        buy_reversal = any(rule.reason_code == "M1_SCALP_COUNTERTREND_REVERSAL" and rule.passed for rule in buy_rules)
        sell_reversal = any(rule.reason_code == "M1_SCALP_COUNTERTREND_REVERSAL" and rule.passed for rule in sell_rules)
        if sell_reversal and sell_score >= self.config.fast_scalp.reversal_minimum_signal_score:
            side, score, rules, details = SignalSide.SELL, sell_score, sell_rules, sell_details
        elif buy_reversal and buy_score >= self.config.fast_scalp.reversal_minimum_signal_score:
            side, score, rules, details = SignalSide.BUY, buy_score, buy_rules, buy_details
        else:
            side, score, rules, details = (
                (SignalSide.BUY, buy_score, buy_rules, buy_details)
                if buy_score >= sell_score
                else (SignalSide.SELL, sell_score, sell_rules, sell_details)
            )
        trend_opposes = (
            (side is SignalSide.BUY and trend.direction is TrendDirection.BEARISH)
            or (side is SignalSide.SELL and trend.direction is TrendDirection.BULLISH)
        )
        reversal_mode = any(rule.reason_code == "M1_SCALP_COUNTERTREND_REVERSAL" and rule.passed for rule in rules)
        threshold = (
            self.config.fast_scalp.reversal_minimum_signal_score
            if trend_opposes and reversal_mode
            else self.config.fast_scalp.countertrend_minimum_signal_score
            if trend_opposes
            else self.config.fast_scalp.minimum_signal_score
        )
        candle_confirmed = any(rule.reason_code == "M1_SCALP_CANDLE_CONFIRMATION" and rule.passed for rule in rules)
        candle_gate_rule = RuleResult(
            candle_confirmed or not self.config.fast_scalp.require_candle_confirmation,
            "M1_SCALP_MANDATORY_CANDLE_CONFIRMATION",
            {"required": self.config.fast_scalp.require_candle_confirmation, "confirmed": candle_confirmed},
        )
        ema20_distance_atr = abs(float(latest.close - latest.ema20)) / float(latest.atr) if float(latest.atr) > 0 else float("inf")
        same_trend_chase = self.config.fast_scalp.avoid_same_trend_chase and (
            (
                side is SignalSide.BUY
                and trend.direction is TrendDirection.BULLISH
                and float(latest.rsi) >= self.config.fast_scalp.same_trend_buy_max_rsi
                and ema20_distance_atr >= self.config.fast_scalp.same_trend_max_ema20_distance_atr
            )
            or (
                side is SignalSide.SELL
                and trend.direction is TrendDirection.BEARISH
                and float(latest.rsi) <= self.config.fast_scalp.same_trend_sell_min_rsi
                and ema20_distance_atr >= self.config.fast_scalp.same_trend_max_ema20_distance_atr
            )
        )
        chase_guard_rule = RuleResult(not same_trend_chase, "M1_SCALP_NO_SAME_TREND_CHASE", {
            "enabled": self.config.fast_scalp.avoid_same_trend_chase,
            "rsi": float(latest.rsi),
            "buy_max_rsi": self.config.fast_scalp.same_trend_buy_max_rsi,
            "sell_min_rsi": self.config.fast_scalp.same_trend_sell_min_rsi,
            "ema20_distance_atr": ema20_distance_atr,
            "maximum_ema20_distance_atr": self.config.fast_scalp.same_trend_max_ema20_distance_atr,
            "trend": trend.direction.value,
        })
        threshold_rule = RuleResult(score >= threshold, "M1_SCALP_SCORE_THRESHOLD", {
            "score": score,
            "minimum": threshold,
            "trend": trend.direction.value,
            "countertrend": trend_opposes,
            "reversal_mode": reversal_mode,
        })
        accepted = score >= threshold and candle_gate_rule.passed and chase_guard_rule.passed
        all_rules = rules + (candle_gate_rule, chase_guard_rule, threshold_rule)
        payload = {"side": side.value, "score": score, "rules": [rule.as_dict() for rule in all_rules], "details": details, "mode": "FAST_SCALP"}
        signal_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()[:24]
        rejection = None
        if not accepted:
            if not candle_gate_rule.passed:
                rejection = "M1_SCALP_CANDLE_CONFIRMATION_REQUIRED"
            elif not chase_guard_rule.passed:
                rejection = "M1_SCALP_SAME_TREND_CHASE_GUARD"
            else:
                rejection = f"M1_SCALP_SCORE_BELOW_THRESHOLD:{score}<{threshold}"
        return SignalEvaluation(
            side if accepted else SignalSide.NO_TRADE,
            score,
            "TRADE" if accepted else "NO_TRADE",
            rejection,
            all_rules,
            signal_hash,
            {**details, "mode": "FAST_SCALP", "threshold": threshold, "trend": trend.direction.value},
        )

    def _fast_scalp_side_evaluation(self, m1: pd.DataFrame, trend: TrendAssessment, side: SignalSide) -> SignalEvaluation:
        latest, previous = m1.iloc[-1], m1.iloc[-2]
        is_buy = side is SignalSide.BUY
        patterns = detect_candlestick_patterns(m1, side)
        candle_ok = patterns.confirmed or not self.config.fast_scalp.require_candle_confirmation
        ema20_ok = bool(latest.close > latest.ema20) if is_buy else bool(latest.close < latest.ema20)
        ema50_ok = bool(latest.close > latest.ema50) if is_buy else bool(latest.close < latest.ema50)
        macd_ok = bool(latest.macd_hist > previous.macd_hist) if is_buy else bool(latest.macd_hist < previous.macd_hist)
        rsi_ok = bool(latest.rsi >= 50) if is_buy else bool(latest.rsi <= 50)
        atr = max(float(latest.atr), 1e-12)
        body = abs(float(latest.close - latest.open))
        average_body = max(float(latest.average_body), 1e-12)
        impulse_ok = body >= average_body
        lookback = m1.iloc[-21:-1] if len(m1) >= 21 else m1.iloc[:-1]
        recent_high = float(lookback.high.max()) if len(lookback) else float(latest.high)
        recent_low = float(lookback.low.min()) if len(lookback) else float(latest.low)
        local_range = max(recent_high - recent_low, atr)
        close_position = (float(latest.close) - recent_low) / local_range
        near_local_high = bool(float(latest.high) >= recent_high - atr * 0.35 or close_position >= 0.78)
        near_local_low = bool(float(latest.low) <= recent_low + atr * 0.35 or close_position <= 0.22)
        bullish_candle = bool(latest.close > latest.open)
        bearish_candle = bool(latest.close < latest.open)
        top_sell_setup = (
            side is SignalSide.SELL
            and near_local_high
            and candle_ok
            and bearish_candle
            and (macd_ok or float(latest.rsi) >= 50 or bool(latest.close < latest.ema20))
        )
        bottom_buy_setup = (
            side is SignalSide.BUY
            and near_local_low
            and candle_ok
            and bullish_candle
            and (macd_ok or float(latest.rsi) <= 50 or bool(latest.close > latest.ema20))
        )
        countertrend_reversal = self.config.fast_scalp.countertrend_reversal_enabled and (
            (
                side is SignalSide.SELL
                and trend.direction is TrendDirection.BULLISH
                and float(latest.rsi) >= self.config.fast_scalp.overbought_rsi
                and candle_ok
                and macd_ok
            )
            or (
                side is SignalSide.BUY
                and trend.direction is TrendDirection.BEARISH
                and float(latest.rsi) <= self.config.fast_scalp.oversold_rsi
                and candle_ok
                and macd_ok
            )
        )
        rules = (
            RuleResult(candle_ok, "M1_SCALP_CANDLE_CONFIRMATION", {
                "supportive": list(patterns.supportive),
                "opposing": list(patterns.opposing),
                "neutral": list(patterns.neutral),
            }, 30),
            RuleResult(macd_ok, "M1_SCALP_MACD_MOMENTUM", {"current": float(latest.macd_hist), "previous": float(previous.macd_hist)}, 25),
            RuleResult(ema20_ok, "M1_SCALP_EMA20_SIDE", {"close": float(latest.close), "ema20": float(latest.ema20)}, 15),
            RuleResult(ema50_ok, "M1_SCALP_EMA50_SIDE", {"close": float(latest.close), "ema50": float(latest.ema50)}, 10),
            RuleResult(rsi_ok, "M1_SCALP_RSI_SIDE", {"rsi": float(latest.rsi)}, 10),
            RuleResult(impulse_ok, "M1_SCALP_IMPULSE_BODY", {"body": body, "average_body": average_body}, 10),
            RuleResult(top_sell_setup, "M1_SCALP_SELL_AT_LOCAL_HIGH", {
                "recent_high": recent_high,
                "recent_low": recent_low,
                "close_position": close_position,
                "near_local_high": near_local_high,
                "bearish_candle": bearish_candle,
                "rsi": float(latest.rsi),
            }, 20),
            RuleResult(bottom_buy_setup, "M1_SCALP_BUY_AT_LOCAL_LOW", {
                "recent_high": recent_high,
                "recent_low": recent_low,
                "close_position": close_position,
                "near_local_low": near_local_low,
                "bullish_candle": bullish_candle,
                "rsi": float(latest.rsi),
            }, 20),
            RuleResult(countertrend_reversal, "M1_SCALP_COUNTERTREND_REVERSAL", {
                "rsi": float(latest.rsi),
                "overbought": self.config.fast_scalp.overbought_rsi,
                "oversold": self.config.fast_scalp.oversold_rsi,
                "trend": trend.direction.value,
                "candle_confirmed": candle_ok,
                "macd_fading": macd_ok,
            }, 25),
        )
        score = sum(rule.points for rule in rules if rule.passed)
        details = {
            "supportive_patterns": list(patterns.supportive),
            "opposing_patterns": list(patterns.opposing),
            "neutral_patterns": list(patterns.neutral),
            "candle_time": str(latest.time),
            "atr": atr,
            "rsi": float(latest.rsi),
            "recent_high": recent_high,
            "recent_low": recent_low,
            "close_position": close_position,
            "near_local_high": near_local_high,
            "near_local_low": near_local_low,
        }
        trend_opposes = (
            (side is SignalSide.BUY and trend.direction is TrendDirection.BEARISH)
            or (side is SignalSide.SELL and trend.direction is TrendDirection.BULLISH)
        )
        reversal_mode = any(rule.reason_code == "M1_SCALP_COUNTERTREND_REVERSAL" and rule.passed for rule in rules)
        threshold = (
            self.config.fast_scalp.reversal_minimum_signal_score
            if trend_opposes and reversal_mode
            else self.config.fast_scalp.countertrend_minimum_signal_score
            if trend_opposes
            else self.config.fast_scalp.minimum_signal_score
        )
        candle_confirmed = any(rule.reason_code == "M1_SCALP_CANDLE_CONFIRMATION" and rule.passed for rule in rules)
        candle_gate_rule = RuleResult(
            candle_confirmed or not self.config.fast_scalp.require_candle_confirmation,
            "M1_SCALP_MANDATORY_CANDLE_CONFIRMATION",
            {"required": self.config.fast_scalp.require_candle_confirmation, "confirmed": candle_confirmed},
        )
        ema20_distance_atr = abs(float(latest.close - latest.ema20)) / float(latest.atr) if float(latest.atr) > 0 else float("inf")
        same_trend_chase = self.config.fast_scalp.avoid_same_trend_chase and (
            (
                side is SignalSide.BUY
                and trend.direction is TrendDirection.BULLISH
                and float(latest.rsi) >= self.config.fast_scalp.same_trend_buy_max_rsi
                and ema20_distance_atr >= self.config.fast_scalp.same_trend_max_ema20_distance_atr
            )
            or (
                side is SignalSide.SELL
                and trend.direction is TrendDirection.BEARISH
                and float(latest.rsi) <= self.config.fast_scalp.same_trend_sell_min_rsi
                and ema20_distance_atr >= self.config.fast_scalp.same_trend_max_ema20_distance_atr
            )
        )
        local_extreme_chase = (
            (
                side is SignalSide.BUY
                and near_local_high
                and bullish_candle
                and float(latest.rsi) >= 58
                and body >= average_body * 1.25
                and not bottom_buy_setup
            )
            or (
                side is SignalSide.SELL
                and near_local_low
                and bearish_candle
                and float(latest.rsi) <= 42
                and body >= average_body * 1.25
                and not top_sell_setup
            )
        )
        chase_guard_rule = RuleResult(not same_trend_chase, "M1_SCALP_NO_SAME_TREND_CHASE", {
            "enabled": self.config.fast_scalp.avoid_same_trend_chase,
            "rsi": float(latest.rsi),
            "buy_max_rsi": self.config.fast_scalp.same_trend_buy_max_rsi,
            "sell_min_rsi": self.config.fast_scalp.same_trend_sell_min_rsi,
            "ema20_distance_atr": ema20_distance_atr,
            "maximum_ema20_distance_atr": self.config.fast_scalp.same_trend_max_ema20_distance_atr,
            "trend": trend.direction.value,
        })
        local_extreme_guard_rule = RuleResult(not local_extreme_chase, "M1_SCALP_NO_LOCAL_EXTREME_CHASE", {
            "side": side.value,
            "near_local_high": near_local_high,
            "near_local_low": near_local_low,
            "close_position": close_position,
            "body": body,
            "average_body": average_body,
            "rsi": float(latest.rsi),
            "top_sell_setup": top_sell_setup,
            "bottom_buy_setup": bottom_buy_setup,
        })
        quality_confirmation = impulse_ok or top_sell_setup or bottom_buy_setup or countertrend_reversal
        quality_rule = RuleResult(quality_confirmation, "M1_SCALP_QUALITY_CONFIRMATION", {
            "impulse": impulse_ok,
            "top_sell_setup": top_sell_setup,
            "bottom_buy_setup": bottom_buy_setup,
            "countertrend_reversal": countertrend_reversal,
            "body": body,
            "average_body": average_body,
            "close_position": close_position,
        })
        threshold_rule = RuleResult(score >= threshold, "M1_SCALP_SCORE_THRESHOLD", {
            "score": score,
            "minimum": threshold,
            "trend": trend.direction.value,
            "countertrend": trend_opposes,
            "reversal_mode": reversal_mode,
        })
        accepted = score >= threshold and candle_gate_rule.passed and chase_guard_rule.passed and local_extreme_guard_rule.passed and quality_rule.passed
        all_rules = rules + (candle_gate_rule, chase_guard_rule, local_extreme_guard_rule, quality_rule, threshold_rule)
        payload = {"side": side.value, "score": score, "rules": [rule.as_dict() for rule in all_rules], "details": details, "mode": "FAST_SCALP"}
        signal_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()[:24]
        rejection = None
        if not accepted:
            if not candle_gate_rule.passed:
                rejection = "M1_SCALP_CANDLE_CONFIRMATION_REQUIRED"
            elif not chase_guard_rule.passed:
                rejection = "M1_SCALP_SAME_TREND_CHASE_GUARD"
            elif not local_extreme_guard_rule.passed:
                rejection = "M1_SCALP_LOCAL_EXTREME_CHASE_GUARD"
            elif not quality_rule.passed:
                rejection = "M1_SCALP_QUALITY_CONFIRMATION_REQUIRED"
            else:
                rejection = f"M1_SCALP_SCORE_BELOW_THRESHOLD:{score}<{threshold}"
        return SignalEvaluation(
            side if accepted else SignalSide.NO_TRADE,
            score,
            "TRADE" if accepted else "NO_TRADE",
            rejection,
            all_rules,
            signal_hash,
            {**details, "mode": "FAST_SCALP", "threshold": threshold, "trend": trend.direction.value},
        )

    def _fast_scalp_evaluations(self, m1: pd.DataFrame, trend: TrendAssessment) -> tuple[SignalEvaluation, SignalEvaluation]:
        values = (
            self._fast_scalp_side_evaluation(m1, trend, SignalSide.BUY),
            self._fast_scalp_side_evaluation(m1, trend, SignalSide.SELL),
        )
        return tuple(sorted(values, key=lambda item: item.score, reverse=True))  # type: ignore[return-value]

    def _fast_scalp_plan(self, side: SignalSide, entry: float, atr: float, spread: float = 0.0) -> PricePlan:
        distance = max(
            atr * self.config.fast_scalp.stop_atr_multiplier,
            spread * 2.5,
            self.spec.trade_stops_level * self.spec.point * 1.2,
            self.spec.point,
        )
        risk_reward = max(self.config.fast_scalp.risk_reward, self.config.take_profit.minimum_risk_reward)
        stop_loss = entry - distance if side is SignalSide.BUY else entry + distance
        take_profit = entry + distance * risk_reward if side is SignalSide.BUY else entry - distance * risk_reward
        stop_loss = normalize_price(stop_loss, self.spec.digits)
        take_profit = normalize_price(take_profit, self.spec.digits)
        entry = normalize_price(entry, self.spec.digits)
        actual_distance = abs(entry - stop_loss)
        actual_rr = abs(take_profit - entry) / actual_distance if actual_distance > 0 else 0
        if actual_distance <= 0:
            raise OrderValidationError("Fast scalp stop distance is zero")
        return PricePlan(side, entry, stop_loss, take_profit, actual_distance, actual_distance / atr if atr > 0 else float("inf"), actual_rr)

    def _m15_quick_evaluation(self, m15: pd.DataFrame, m5: pd.DataFrame) -> SignalEvaluation:
        latest15, previous15, latest5, previous5 = m15.iloc[-1], m15.iloc[-2], m5.iloc[-1], m5.iloc[-2]
        atr = max(float(latest15.atr), 1e-12)
        body = abs(float(latest15.close - latest15.open))
        body_atr = body / atr
        bullish = bool(latest15.close > latest15.open)
        bearish = bool(latest15.close < latest15.open)
        broke_previous_high = bool(latest15.close > previous15.high)
        broke_previous_low = bool(latest15.close < previous15.low)
        side = SignalSide.BUY if bullish and broke_previous_high else SignalSide.SELL if bearish and broke_previous_low else SignalSide.NO_TRADE
        if side is SignalSide.NO_TRADE:
            rule = RuleResult(False, "M15_QUICK_NO_BREAKOUT_CANDLE", {
                "close": float(latest15.close),
                "previous_high": float(previous15.high),
                "previous_low": float(previous15.low),
                "bullish": bullish,
                "bearish": bearish,
            })
            return self._finish_quick_evaluation(side, (rule,), {"mode": "M15_QUICK", "body_atr": body_atr}, "M15_QUICK_NO_BREAKOUT_CANDLE")

        is_buy = side is SignalSide.BUY
        m15_ema_ok = bool(latest15.close > latest15.ema20 and latest15.ema20 >= latest15.ema50) if is_buy else bool(latest15.close < latest15.ema20 and latest15.ema20 <= latest15.ema50)
        m5_momentum_ok = bool(latest5.close > latest5.ema20 and latest5.macd_hist > previous5.macd_hist) if is_buy else bool(latest5.close < latest5.ema20 and latest5.macd_hist < previous5.macd_hist)
        rsi_ok = bool(45 <= float(latest15.rsi) <= 74) if is_buy else bool(26 <= float(latest15.rsi) <= 55)
        adx_ok = bool(float(latest15.adx) >= self.config.m15_quick_trade.minimum_adx)
        body_min_ok = body_atr >= self.config.m15_quick_trade.min_body_atr
        body_max_ok = body_atr <= self.config.m15_quick_trade.max_body_atr
        breakout_ok = broke_previous_high if is_buy else broke_previous_low
        rules = (
            RuleResult(breakout_ok, "M15_QUICK_BREAKOUT_CLOSE", {"body_atr": body_atr, "previous_high": float(previous15.high), "previous_low": float(previous15.low)}, 25),
            RuleResult(m15_ema_ok, "M15_QUICK_EMA_ALIGNMENT", {"close": float(latest15.close), "ema20": float(latest15.ema20), "ema50": float(latest15.ema50)}, 20),
            RuleResult(m5_momentum_ok, "M15_QUICK_M5_MOMENTUM", {"m5_close": float(latest5.close), "m5_ema20": float(latest5.ema20), "macd": float(latest5.macd_hist), "previous_macd": float(previous5.macd_hist)}, 20),
            RuleResult(rsi_ok, "M15_QUICK_RSI_FILTER", {"rsi": float(latest15.rsi), "side": side.value}, 10),
            RuleResult(adx_ok, "M15_QUICK_ADX_FILTER", {"adx": float(latest15.adx), "minimum": self.config.m15_quick_trade.minimum_adx}, 10),
            RuleResult(body_min_ok, "M15_QUICK_BODY_MIN_ATR", {"body_atr": body_atr, "minimum": self.config.m15_quick_trade.min_body_atr}, 10),
            RuleResult(body_max_ok, "M15_QUICK_BODY_NOT_EXHAUSTED", {"body_atr": body_atr, "maximum": self.config.m15_quick_trade.max_body_atr}, 5),
        )
        return self._finish_quick_evaluation(side, rules, {
            "mode": "M15_QUICK",
            "atr": atr,
            "adx": float(latest15.adx),
            "rsi": float(latest15.rsi),
            "body_atr": body_atr,
            "candle_time": str(latest15.time),
        }, None)

    def _finish_quick_evaluation(self, side: SignalSide, rules: tuple[RuleResult, ...], details: dict[str, Any], forced_reason: str | None) -> SignalEvaluation:
        score = sum(rule.points for rule in rules if rule.passed)
        mandatory = {"M15_QUICK_BREAKOUT_CLOSE", "M15_QUICK_M5_MOMENTUM", "M15_QUICK_BODY_NOT_EXHAUSTED"}
        failed = [rule.reason_code for rule in rules if rule.reason_code in mandatory and not rule.passed]
        accepted = side is not SignalSide.NO_TRADE and score >= self.config.m15_quick_trade.minimum_signal_score and not failed
        reason = forced_reason or (None if accepted else (f"M15_QUICK_MANDATORY_FAILED:{','.join(failed)}" if failed else f"M15_QUICK_SCORE_BELOW_MINIMUM:{score}"))
        payload = {"side": side.value, "score": score, "rules": [rule.as_dict() for rule in rules], "details": details}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()[:24]
        return SignalEvaluation(side if accepted else SignalSide.NO_TRADE, score, "TRADE" if accepted else "NO_TRADE", reason, rules, digest, details)

    def _m15_quick_lot_cap(self) -> float | None:
        values = [self.config.m15_quick_trade.max_lot_per_entry]
        if self.config.risk.max_lot_per_entry is not None:
            values.append(self.config.risk.max_lot_per_entry)
        if self.config.hard_trade.enabled:
            values.append(self.config.hard_trade.max_lot_per_entry)
        return min(values)

    def _m15_quick_sizing(self, equity: float, plan: PricePlan) -> SizingResult:
        try:
            return PositionSizer.calculate(
                equity,
                self.config.m15_quick_trade.risk_per_entry_percent,
                plan.entry,
                plan.stop_loss,
                self.spec,
                self._m15_quick_lot_cap(),
            )
        except OrderValidationError as exc:
            if "below broker minimum" not in str(exc):
                raise
        distance = abs(plan.entry - plan.stop_loss)
        ticks_to_stop = distance / self.spec.trade_tick_size if self.spec.trade_tick_size > 0 else 0.0
        loss_per_lot = ticks_to_stop * self.spec.trade_tick_value
        if equity <= 0 or loss_per_lot <= 0:
            raise OrderValidationError("M15 quick minimum-lot risk calculation failed")
        volume_cap = self._m15_quick_lot_cap()
        minimum_lot = self.spec.volume_min
        if volume_cap is not None and minimum_lot > volume_cap + 1e-12:
            raise OrderValidationError("M15 quick minimum lot exceeds configured lot cap")
        actual_risk = minimum_lot * loss_per_lot
        actual_risk_percent = actual_risk / equity * 100
        if actual_risk_percent > self.config.m15_quick_trade.minimum_lot_max_risk_percent + 1e-12:
            raise OrderValidationError("M15 quick minimum lot risk exceeds configured cap")
        requested_risk = equity * self.config.m15_quick_trade.risk_per_entry_percent / 100
        return SizingResult(minimum_lot, minimum_lot, requested_risk, loss_per_lot, ticks_to_stop)

    def _m15_quick_plan(self, side: SignalSide, entry: float, atr: float, spread: float = 0.0) -> PricePlan:
        distance = max(
            atr,
            spread * 2.5,
            self.spec.trade_stops_level * self.spec.point * 1.2,
            self.spec.point,
        )
        risk_reward = max(self.config.take_profit.minimum_risk_reward, self.config.take_profit.default_risk_reward)
        stop_loss = normalize_price(entry - distance if side is SignalSide.BUY else entry + distance, self.spec.digits)
        take_profit = normalize_price(entry + distance * risk_reward if side is SignalSide.BUY else entry - distance * risk_reward, self.spec.digits)
        entry = normalize_price(entry, self.spec.digits)
        actual_distance = abs(entry - stop_loss)
        actual_rr = abs(take_profit - entry) / actual_distance if actual_distance > 0 else 0
        if actual_distance <= 0:
            raise OrderValidationError("M15 quick stop distance is zero")
        return PricePlan(side, entry, stop_loss, take_profit, actual_distance, actual_distance / atr if atr > 0 else float("inf"), actual_rr)

    def _fast_scalp_lot_cap(self) -> float | None:
        hard_cap = self.config.hard_trade.max_lot_per_entry if self.config.hard_trade.enabled else None
        if self.config.fast_scalp.max_lot_per_entry is None:
            base_cap = self.config.risk.max_lot_per_entry
        elif self.config.risk.max_lot_per_entry is None:
            base_cap = self.config.fast_scalp.max_lot_per_entry
        else:
            base_cap = min(self.config.fast_scalp.max_lot_per_entry, self.config.risk.max_lot_per_entry)
        if hard_cap is None:
            return base_cap
        if base_cap is None:
            return hard_cap
        return min(base_cap, hard_cap)

    def _closed_trade_profit(self, trade: Trade) -> float:
        return trade.realized_profit if abs(trade.realized_profit) > 1e-12 else trade.floating_profit

    def _btc_weekend_relaxation_active(self, now: datetime) -> bool:
        if not self.config.hard_trade.btc_weekend_relaxation_enabled:
            return False
        if not str(self.config.symbol.base_symbol).upper().startswith("BTC") and not str(self.symbol).upper().startswith("BTC"):
            return False
        local = ensure_utc(now).astimezone(self.session_guard.timezone)
        return local.weekday() >= 5

    def _weekend_btc_signal_engine(self, now: datetime) -> SignalEngine:
        if not self._btc_weekend_relaxation_active(now):
            return self.signal_engine
        discount = self.config.hard_trade.btc_weekend_signal_score_discount
        strategy = self.config.strategy.model_copy(update={
            "minimum_signal_score": max(0, self.config.strategy.minimum_signal_score - discount),
        })
        return SignalEngine(strategy, self.config.signal_scoring, self.config.take_profit)

    def _weekend_btc_max_atr_multiplier(self, now: datetime) -> float | None:
        if not self._btc_weekend_relaxation_active(now):
            return None
        discount = self.config.hard_trade.btc_weekend_max_atr_multiplier_discount
        return max(
            self.config.stop_loss.minimum_atr_multiplier,
            self.config.stop_loss.maximum_atr_multiplier - discount,
        )

    def _apply_btc_weekend_setup_discount(self, now: datetime, threshold: float) -> float:
        if self._btc_weekend_relaxation_active(now):
            threshold -= self.config.hard_trade.btc_weekend_setup_win_rate_discount
        return max(50.0, threshold)

    def _base_setup_win_rate_threshold(self, entry_timeframe: str) -> float:
        return (
            self.config.hard_trade.m5_minimum_setup_win_rate
            if self.config.hard_trade.enabled and entry_timeframe == "M5"
            else self.config.hard_trade.minimum_setup_win_rate
            if self.config.hard_trade.enabled
            else 50.0
        )

    def _effective_setup_win_rate_threshold(self, now: datetime, entry_timeframe: str) -> float:
        return self._apply_btc_weekend_setup_discount(now, self._base_setup_win_rate_threshold(entry_timeframe))

    @staticmethod
    def _calculated_setup_win_rate(evaluation: SignalEvaluation, extra_rules: tuple[RuleResult, ...] = ()) -> float:
        rules = tuple(evaluation.rules) + extra_rules
        by_reason = {rule.reason_code: rule for rule in rules}
        score = min(float(evaluation.score), 100.0)
        score_component = score * 0.45
        value = 25.0 + score_component
        if score >= 95:
            value += 5.0
        elif score >= 85:
            value += 3.0
        elif score >= 75:
            value += 1.5

        bonus_rules = {
            "H4_TREND_ALIGNMENT": 2.0,
            "H1_TREND_ALIGNMENT": 2.0,
            "M15_EMA_ALIGNMENT": 1.5,
            "MARKET_STRUCTURE": 2.0,
            "M15_PULLBACK_QUALITY": 3.0,
            "M5_CANDLE_CONFIRMATION": 3.0,
            "M5_MACD_CONFIRMATION": 2.0,
            "M15_RSI_CONFIRMATION": 1.5,
            "M15_ADX_STRENGTH": 1.0,
            "RISK_REWARD_QUALITY": 2.5,
            "RELAXED_FOREX_SL_ATR_FOR_HIGH_SCORE": 1.0,
            "M1_SCALP_CANDLE_CONFIRMATION": 2.0,
            "M1_SCALP_MACD_MOMENTUM": 1.5,
            "M1_SCALP_QUALITY_CONFIRMATION": 2.0,
            "M1_SCALP_NO_LOCAL_EXTREME_CHASE": 1.5,
        }
        value += sum(points for reason, points in bonus_rules.items() if by_reason.get(reason) and by_reason[reason].passed)

        penalty_rules = {
            "M15_PULLBACK_QUALITY": 12.0,
            "M5_CANDLE_CONFIRMATION": 8.0,
            "M5_MACD_CONFIRMATION": 4.0,
            "M15_RSI_CONFIRMATION": 4.0,
            "M15_ADX_STRENGTH": 5.0,
            "RISK_REWARD_QUALITY": 8.0,
            "SPREAD_TOO_HIGH": 10.0,
            "ENTRY_PROFILE_SCORE_TOO_LOW": 5.0,
            "M1_SCALP_MANDATORY_CANDLE_CONFIRMATION": 8.0,
            "M1_SCALP_NO_SAME_TREND_CHASE": 8.0,
            "M1_SCALP_NO_LOCAL_EXTREME_CHASE": 8.0,
            "M1_SCALP_QUALITY_CONFIRMATION": 6.0,
        }
        value -= sum(points for reason, points in penalty_rules.items() if by_reason.get(reason) and not by_reason[reason].passed)

        rsi = evaluation.details.get("rsi")
        try:
            rsi_value = float(rsi)
            if evaluation.side is SignalSide.BUY and rsi_value > 68:
                value -= min(6.0, (rsi_value - 68) * 0.5)
            if evaluation.side is SignalSide.SELL and rsi_value < 32:
                value -= min(6.0, (32 - rsi_value) * 0.5)
        except (TypeError, ValueError):
            pass

        failed_mandatory = sum(1 for rule in rules if not rule.passed and rule.reason_code in penalty_rules)
        if failed_mandatory:
            value -= min(10.0, failed_mandatory * 2.0)

        return round(max(25.0, min(85.0, value)), 1)

    def _calculated_setup_win_rate_rule(
        self,
        evaluation: SignalEvaluation,
        extra_rules: tuple[RuleResult, ...] = (),
        threshold: float = 50.0,
        reason_code: str = "CALCULATED_SETUP_WIN_RATE_GATE",
    ) -> RuleResult:
        win_rate = self._calculated_setup_win_rate(evaluation, extra_rules)
        details = {
            "threshold": threshold,
            "win_rate": win_rate,
            "signal_score": evaluation.score,
            "signal_hash": evaluation.signal_hash,
            "source": "CURRENT_SETUP_RULE_SCORE",
        }
        return RuleResult(win_rate > threshold, reason_code, details, 0)

    def _adaptive_learning_rule(
        self,
        evaluation: SignalEvaluation,
        setup_timeframe: str,
        current_win_rate: float,
        base_threshold: float,
        proposed_entry_number: int = 1,
    ) -> tuple[RuleResult, float]:
        learning = self.config.adaptive_learning
        if not learning.enabled:
            return RuleResult(True, "ADAPTIVE_LEARNING_DISABLED", {"enabled": False}, 0), base_threshold

        cutoff = datetime.now(UTC) - timedelta(days=learning.lookback_days)
        bucket = learning.wr_bucket_size
        minimum_wr = current_win_rate - bucket
        maximum_wr = current_win_rate + bucket
        with self.database.transaction() as session:
            trades = list(session.scalars(select(Trade).where(
                Trade.symbol == self.symbol,
                Trade.side == evaluation.side.value,
                Trade.state == TradeState.CLOSED.value,
                Trade.closed_at.is_not(None),
                Trade.closed_at >= cutoff,
                Trade.estimated_win_rate.is_not(None),
            )))

        current_session_bucket = self._learning_session_bucket()
        similar = [
            trade for trade in trades
            if self._timeframe_from_key(trade.idempotency_key) == setup_timeframe
            and minimum_wr <= float(trade.estimated_win_rate or 0.0) <= maximum_wr
        ]
        same_session = [
            trade for trade in similar
            if self._learning_session_bucket(trade.opened_at or trade.entry_candle_time) == current_session_bucket
        ]
        addon_similar = [
            trade for trade in similar
            if int(trade.entry_number or 1) >= 2
        ] if proposed_entry_number >= 2 else []
        symbol_session = [
            trade for trade in trades
            if self._learning_session_bucket(trade.opened_at or trade.entry_candle_time) == current_session_bucket
        ]
        pnls = [float(trade.realized_profit if trade.realized_profit is not None else trade.floating_profit or 0.0) for trade in similar]
        wins = sum(1 for pnl in pnls if pnl > 0)
        losses = sum(1 for pnl in pnls if pnl < 0)
        total = len(similar)
        win_rate = wins / total * 100 if total else 0.0
        net_pnl = sum(pnls)
        gross_win = sum(pnl for pnl in pnls if pnl > 0)
        gross_loss = abs(sum(pnl for pnl in pnls if pnl < 0))
        profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
        average_win = gross_win / wins if wins else 0.0
        average_loss = gross_loss / losses if losses else 0.0
        average_win_loss_ratio = average_win / average_loss if average_loss > 0 else float("inf") if average_win > 0 else 0.0
        adverse_values = [float(trade.max_adverse_r or 0.0) for trade in (same_session or similar) if trade.max_adverse_r is not None]
        average_adverse_r = sum(adverse_values) / len(adverse_values) if adverse_values else 0.0
        addon_pnls = [float(trade.realized_profit if trade.realized_profit is not None else trade.floating_profit or 0.0) for trade in addon_similar]
        addon_wins = sum(1 for pnl in addon_pnls if pnl > 0)
        addon_win_rate = addon_wins / len(addon_pnls) * 100 if addon_pnls else 0.0
        symbol_session_pnls = [float(trade.realized_profit if trade.realized_profit is not None else trade.floating_profit or 0.0) for trade in symbol_session]
        symbol_session_wins = sum(1 for pnl in symbol_session_pnls if pnl > 0)
        symbol_session_win_rate = symbol_session_wins / len(symbol_session_pnls) * 100 if symbol_session_pnls else 0.0
        symbol_session_net_pnl = sum(symbol_session_pnls)
        details = {
            "symbol": self.symbol,
            "side": evaluation.side.value,
            "timeframe": setup_timeframe,
            "session_bucket_local_hour": current_session_bucket,
            "proposed_entry_number": proposed_entry_number,
            "lookback_days": learning.lookback_days,
            "sample_size": total,
            "same_session_sample_size": len(same_session),
            "wins": wins,
            "losses": losses,
            "historical_win_rate": round(win_rate, 1),
            "net_pnl": round(net_pnl, 2),
            "gross_win": round(gross_win, 2),
            "gross_loss": round(gross_loss, 2),
            "profit_factor": None if math.isinf(profit_factor) else round(profit_factor, 2),
            "average_win": round(average_win, 2),
            "average_loss": round(average_loss, 2),
            "average_win_loss_ratio": None if math.isinf(average_win_loss_ratio) else round(average_win_loss_ratio, 2),
            "average_max_adverse_r": round(average_adverse_r, 2),
            "addon_sample_size": len(addon_pnls),
            "addon_win_rate": round(addon_win_rate, 1),
            "symbol_session_sample_size": len(symbol_session_pnls),
            "symbol_session_win_rate": round(symbol_session_win_rate, 1),
            "symbol_session_net_pnl": round(symbol_session_net_pnl, 2),
            "current_setup_win_rate": current_win_rate,
            "wr_bucket": [round(minimum_wr, 1), round(maximum_wr, 1)],
            "base_threshold": base_threshold,
        }
        enough_to_block = total >= learning.block_min_samples
        enough_profit_factor_sample = total >= learning.profit_factor_min_samples and gross_loss > 0
        net_condition = net_pnl < 0 if learning.block_if_net_pnl_negative else True
        if enough_to_block and win_rate < learning.block_win_rate_below and net_condition:
            return RuleResult(False, "ADAPTIVE_LEARNING_BLOCK_BAD_SETUP_CLUSTER", details, 0), base_threshold
        if enough_profit_factor_sample and profit_factor < learning.block_profit_factor_below and net_condition:
            return RuleResult(False, "ADAPTIVE_LEARNING_BLOCK_NEGATIVE_PROFIT_FACTOR", details, 0), base_threshold
        if (
            enough_profit_factor_sample
            and average_win_loss_ratio < learning.min_average_win_loss_ratio
            and win_rate < 50.0
            and net_condition
        ):
            return RuleResult(False, "ADAPTIVE_LEARNING_BLOCK_POOR_AVG_WIN_LOSS", details, 0), base_threshold

        if (
            len(symbol_session_pnls) >= learning.symbol_lock_min_samples
            and symbol_session_win_rate < learning.symbol_lock_loss_rate_below
            and symbol_session_net_pnl < 0
        ):
            return RuleResult(False, "ADAPTIVE_RISK_SYMBOL_SESSION_LOCK", details, 0), base_threshold

        adaptive_threshold = base_threshold
        penalties: list[dict[str, float | str]] = []
        enough_to_raise = total >= learning.raise_threshold_min_samples
        if enough_to_raise and win_rate < learning.raise_threshold_win_rate_below and net_condition:
            adaptive_threshold += learning.threshold_penalty
            penalties.append({"reason": "LOW_CLUSTER_WIN_RATE", "penalty": learning.threshold_penalty})
        if enough_profit_factor_sample and profit_factor < learning.raise_threshold_profit_factor_below and net_condition:
            adaptive_threshold += learning.threshold_penalty
            penalties.append({"reason": "WEAK_PROFIT_FACTOR", "penalty": learning.threshold_penalty})
        if len(adverse_values) >= learning.drawdown_raise_min_samples and average_adverse_r >= learning.drawdown_pain_r:
            adaptive_threshold += learning.drawdown_penalty
            penalties.append({"reason": "HIGH_HISTORICAL_DRAWDOWN_R", "penalty": learning.drawdown_penalty})
        if proposed_entry_number >= 2 and len(addon_pnls) >= learning.addon_raise_min_samples and addon_win_rate < learning.addon_loss_rate_below and sum(addon_pnls) < 0:
            adaptive_threshold += learning.addon_penalty
            penalties.append({"reason": "WEAK_ADDON_HISTORY", "penalty": learning.addon_penalty})

        adaptive_threshold = min(learning.maximum_adaptive_threshold, adaptive_threshold)
        details["adaptive_threshold"] = adaptive_threshold
        details["risk_penalties"] = penalties
        if penalties:
            if len(penalties) == 1 and penalties[0]["reason"] == "LOW_CLUSTER_WIN_RATE":
                return RuleResult(True, "ADAPTIVE_LEARNING_RAISED_WR_THRESHOLD", details, 0), adaptive_threshold
            return RuleResult(True, "ADAPTIVE_RISK_RAISED_WR_THRESHOLD", details, 0), adaptive_threshold
        details["minimum_samples_for_block"] = learning.block_min_samples
        return RuleResult(True, "ADAPTIVE_LEARNING_PASS", details, 0), adaptive_threshold

    def recovery_mode_status(self) -> dict[str, Any]:
        recovery = self.config.recovery_mode
        default = {
            "enabled": recovery.enabled,
            "mode": "normal",
            "active": False,
            "required_win_rate": None,
            "trigger_basket_id": None,
            "trigger_basket_external_id": None,
            "trigger_closed_at": None,
            "trigger_loss": 0.0,
            "trigger_position_count": 0,
            "recovered_pnl": 0.0,
            "recovered_ratio": 1.0,
        }
        if not recovery.enabled:
            return default
        with self.database.transaction() as session:
            basket = session.scalar(
                select(Basket)
                .where(
                    Basket.status == BasketState.CLOSED.value,
                    Basket.closed_at.is_not(None),
                )
                .order_by(Basket.closed_at.desc(), Basket.id.desc())
                .limit(1)
            )
            if basket is None or basket.closed_at is None:
                return default
            basket_trade_count = int(session.scalar(select(func.count(Trade.id)).where(Trade.basket_id == basket.id)) or 0)
            basket_profit = float(basket.total_realized_profit or 0.0)
            if basket_profit >= 0:
                return {
                    **default,
                    "trigger_basket_id": basket.id,
                    "trigger_basket_external_id": basket.external_id,
                    "trigger_closed_at": ensure_utc(basket.closed_at).isoformat(),
                    "trigger_loss": 0.0,
                    "trigger_position_count": basket_trade_count,
                }
            closed_at = ensure_utc(basket.closed_at)
            recovered_pnl = float(session.scalar(
                select(func.coalesce(func.sum(Trade.realized_profit), 0.0)).where(
                    Trade.state == TradeState.CLOSED.value,
                    Trade.closed_at.is_not(None),
                    Trade.closed_at > closed_at,
                    Trade.symbol.in_(self.portfolio_symbols),
                )
            ) or 0.0)
        trigger_loss = abs(basket_profit)
        recovered_ratio = recovered_pnl / trigger_loss if trigger_loss > 0 else 1.0
        if trigger_loss < recovery.soft_minimum_loss_usd:
            mode = "normal"
        elif trigger_loss >= recovery.hard_minimum_loss_usd:
            mode = "hard"
        elif trigger_loss <= recovery.soft_maximum_loss_usd:
            mode = "soft"
        elif recovered_ratio >= recovery.normal_recovered_ratio:
            mode = "normal"
        elif recovered_ratio >= recovery.soft_recovered_ratio:
            mode = "soft"
        elif basket_trade_count < recovery.trigger_basket_position_count:
            mode = "hard"
        else:
            mode = "hard"
        active = mode != "normal"
        return {
            **default,
            "mode": mode,
            "active": active,
            "required_win_rate": (
                recovery.hard_minimum_setup_win_rate
                if mode == "hard"
                else recovery.soft_minimum_setup_win_rate
                if mode == "soft"
                else None
            ),
            "trigger_basket_id": basket.id,
            "trigger_basket_external_id": basket.external_id,
            "trigger_closed_at": closed_at.isoformat(),
            "trigger_loss": round(trigger_loss, 2),
            "trigger_position_count": basket_trade_count,
            "recovered_pnl": round(recovered_pnl, 2),
            "recovered_ratio": round(max(0.0, recovered_ratio), 4),
        }

    def _recovery_mode_rule(self, base_threshold: float) -> tuple[RuleResult, float]:
        status = self.recovery_mode_status()
        if not status["active"]:
            return RuleResult(True, "RECOVERY_MODE_NORMAL", status, 0), base_threshold
        threshold = max(base_threshold, float(status["required_win_rate"] or base_threshold))
        status = {**status, "base_threshold": base_threshold, "effective_threshold": threshold}
        return RuleResult(True, f"RECOVERY_MODE_{str(status['mode']).upper()}_WR_GATE", status, 0), threshold

    def _position_scope_symbols(self) -> tuple[str, ...]:
        if self._is_forex_runtime_symbol():
            return self._forex_runtime_symbols() or (self.symbol,)
        return tuple(symbol for symbol in self.portfolio_symbols if not self._is_forex_runtime_symbol(symbol))

    def _portfolio_positions(self) -> list:
        return [
            position
            for symbol in self._position_scope_symbols()
            for position in self.broker.positions(symbol, self.config.broker.magic_number)
        ]

    def _forex_group_positions(self) -> list:
        return [
            position
            for symbol in self._forex_runtime_symbols()
            for position in self.broker.positions(symbol, self.config.broker.magic_number)
        ]

    def _forex_trading_rules(self) -> tuple[RuleResult, ...]:
        if not self._is_forex_runtime_symbol():
            return ()
        if not self.config.forex_trading.enabled:
            return (
                RuleResult(
                    False,
                    "FOREX_MODE_DISABLED",
                    {"scope": "FOREX", "enabled": False},
                    0,
                ),
            )
        return ()

    def _hard_trade_rules(
        self,
        portfolio_positions: list,
        proposed_lot: float,
        same_side_count: int = 0,
        basket_floating_profit: float = 0.0,
        entry_distance_atr: float | None = None,
    ) -> tuple[RuleResult, ...]:
        hard_trade = self.config.hard_trade
        if not hard_trade.enabled:
            return ()
        open_count = len(portfolio_positions)
        scope = "FOREX" if self._is_forex_runtime_symbol() else "BTCUSD+XAUUSD"
        add_losing_ok = same_side_count == 0 or basket_floating_profit >= -hard_trade.max_losing_basket_add_usd
        add_distance_ok = same_side_count == 0 or (
            entry_distance_atr is not None and entry_distance_atr <= hard_trade.max_add_entry_distance_atr
        )
        rules = (
            RuleResult(
                proposed_lot <= hard_trade.max_lot_per_entry + 1e-12,
                "HARD_TRADE_MAX_LOT_PER_ENTRY",
                {"proposed_lot": proposed_lot, "maximum": hard_trade.max_lot_per_entry},
                0,
            ),
            RuleResult(
                add_losing_ok,
                "HARD_TRADE_NO_DEEP_LOSING_ADD",
                {
                    "same_side_count": same_side_count,
                    "basket_profit": basket_floating_profit,
                    "minimum_allowed_profit": -hard_trade.max_losing_basket_add_usd,
                },
                0,
            ),
            RuleResult(
                add_distance_ok,
                "HARD_TRADE_NO_FAR_CHASE_ADD",
                {
                    "same_side_count": same_side_count,
                    "entry_distance_atr": entry_distance_atr,
                    "maximum": hard_trade.max_add_entry_distance_atr,
                },
                0,
            ),
        )
        return rules

    def _forex_group_metrics(self) -> tuple[float, float, int]:
        forex_symbols = self._forex_runtime_symbols()
        if not forex_symbols:
            return 0.0, 0.0, 0
        positions = self._forex_group_positions()
        floating = sum(position.profit for position in positions)
        with self.database.transaction() as session:
            baskets = list(session.scalars(select(Basket).where(
                Basket.symbol.in_(forex_symbols),
                Basket.status.in_((BasketState.ACTIVE.value, BasketState.CLOSING.value, BasketState.CLOSE_FAILED.value)),
            )))
            realized = sum(float(basket.total_realized_profit or 0.0) for basket in baskets)
            initial_risk = sum(float(basket.initial_risk_amount or 0.0) for basket in baskets)
        return floating + realized, initial_risk, len(positions)

    def _forex_group_exit_decision(self, account_equity: float) -> BasketExitDecision:
        combined_profit, initial_risk, position_count = self._forex_group_metrics()
        if position_count <= 0:
            return BasketExitDecision(False, None, combined_profit, None)
        metrics = BasketMetrics(position_count, 0.0, 0.0, combined_profit, 0.0, combined_profit)
        return self.basket_manager.exit_decision(metrics, initial_risk, account_equity, None)

    def _close_own_forex_baskets_for_group(self, reason: CloseReason, threshold: float | None, profit: float) -> bool:
        if not self._is_forex_runtime_symbol():
            return False
        closed_any = False
        all_closed = True
        for basket in self._active_baskets():
            self._set_state(BotState.CLOSING_BASKET, f"FOREX_GROUP_{reason.value}", {"profit": profit, "threshold": threshold})
            closed = self.basket_manager.close_basket(basket.external_id, reason)
            closed_any = closed_any or closed
            all_closed = closed and all_closed
        if closed_any:
            self._pending_trend_reversal = False
            self._set_state(BotState.COOLDOWN, f"FOREX_GROUP_BASKET_CLOSED:{reason.value}")
        elif not all_closed:
            self._set_state(BotState.ENTRY_PAUSED, "FOREX_GROUP_BASKET_CLOSE_FAILED")
        return closed_any

    def _max_lot_per_entry(self) -> float | None:
        if not self.config.hard_trade.enabled:
            return self.config.risk.max_lot_per_entry
        if self.config.risk.max_lot_per_entry is None:
            return self.config.hard_trade.max_lot_per_entry
        return min(self.config.risk.max_lot_per_entry, self.config.hard_trade.max_lot_per_entry)

    def _fast_scalp_performance_rule(self) -> RuleResult:
        minimum = self.config.fast_scalp.minimum_historical_win_rate
        if minimum is None:
            return RuleResult(True, "FAST_SCALP_WIN_RATE_GATE_DISABLED", {}, 0)
        with self.database.transaction() as session:
            recent_closed = list(session.scalars(
                select(Trade)
                .where(Trade.symbol == self.symbol, Trade.state == TradeState.CLOSED.value)
                .order_by(Trade.closed_at.desc(), Trade.id.desc())
                .limit(self.config.fast_scalp.historical_win_rate_lookback * 3)
            ))
        fast_trades = [
            trade for trade in recent_closed
            if "_M1_" in trade.idempotency_key and trade.closed_at is not None
        ][:self.config.fast_scalp.historical_win_rate_lookback]
        total = len(fast_trades)
        wins = sum(self._closed_trade_profit(trade) > 0 for trade in fast_trades)
        losses = sum(self._closed_trade_profit(trade) < 0 for trade in fast_trades)
        win_rate = wins / total * 100 if total else 0.0
        details = {
            "closed_fast_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "minimum_win_rate": minimum,
            "minimum_trades": self.config.fast_scalp.historical_win_rate_min_trades,
            "lookback": self.config.fast_scalp.historical_win_rate_lookback,
        }
        if total < self.config.fast_scalp.historical_win_rate_min_trades:
            return RuleResult(False, "FAST_SCALP_WIN_RATE_SAMPLE_TOO_SMALL", details, 0)
        return RuleResult(win_rate >= minimum, "FAST_SCALP_WIN_RATE_GATE", details, 0)

    def _try_fast_scalp(self, now: datetime, daily_rules: tuple[RuleResult, ...], session_rules: tuple[RuleResult, ...]) -> bool:
        if not self.config.fast_scalp.enabled:
            return False
        if self.config.hard_trade.enabled and not self.config.hard_trade.allow_fast_scalp:
            return False
        latest_time = self.candles.latest_closed_time(self.symbol, self.config.fast_scalp.timeframe)
        candle_time = latest_time.to_pydatetime() if hasattr(latest_time, "to_pydatetime") else latest_time
        if self._last_scalp_candle and ensure_utc(candle_time) <= ensure_utc(self._last_scalp_candle):
            return False
        self._last_scalp_candle = candle_time
        m1 = self.indicators.calculate(self.candles.closed_candles(self.symbol, self.config.fast_scalp.timeframe, self.config.timeframes.candle_history))
        h4 = self.indicators.calculate(self.candles.closed_candles(self.symbol, "H4", self.config.timeframes.candle_history))
        h1 = self.indicators.calculate(self.candles.closed_candles(self.symbol, "H1", self.config.timeframes.candle_history))
        trend = self.trend_detector.detect(h4, h1)
        row = m1.iloc[-1]
        tick = self.broker.tick(self.symbol)
        evaluations = self._fast_scalp_evaluations(m1, trend)
        performance_rule = self._fast_scalp_performance_rule()
        opened_any = False
        evaluated_any = False
        for evaluation in evaluations:
            if evaluation.decision != "TRADE":
                continue
            evaluated_any = True
            if not performance_rule.passed:
                self._persist_decision(
                    trend.direction, evaluation, evaluation.rules + session_rules + (performance_rule,),
                    "NO_TRADE", performance_rule.reason_code, tick, row,
                )
                continue
            entry = tick.ask if evaluation.side is SignalSide.BUY else tick.bid
            plan = self._fast_scalp_plan(evaluation.side, entry, float(row.atr), float(tick.ask - tick.bid))
            entry_profile_rule = self.session_guard.entry_profile_rule(now, evaluation.score)
            spread_rule = self.spread_guard.evaluate(tick, self.spec.point, float(row.atr))
            if not entry_profile_rule.passed or not spread_rule.passed:
                reason = entry_profile_rule.reason_code if not entry_profile_rule.passed else spread_rule.reason_code
                self._persist_decision(trend.direction, evaluation, evaluation.rules + session_rules + (entry_profile_rule, spread_rule), "NO_TRADE", reason, tick, row, plan.stop_loss, plan.take_profit, plan.risk_reward)
                continue

            account = self.broker.account()
            try:
                sizing = PositionSizer.calculate(account.equity, self.config.risk.risk_per_entry_percent, plan.entry, plan.stop_loss, self.spec, self._fast_scalp_lot_cap())
            except OrderValidationError as exc:
                sizing_rule = RuleResult(False, "POSITION_SIZING_REJECTED", {"error": str(exc)})
                self._persist_decision(
                    trend.direction,
                    evaluation,
                    evaluation.rules + session_rules + (entry_profile_rule, spread_rule, sizing_rule),
                    "NO_TRADE",
                    str(exc),
                    tick,
                    row,
                    plan.stop_loss,
                    plan.take_profit,
                    plan.risk_reward,
                )
                continue
            positions = self.broker.positions(self.symbol, self.config.broker.magic_number)
            idempotency_key = f"{self.symbol}_{evaluation.side.value}_M1_{int(ensure_utc(candle_time).timestamp())}_{evaluation.signal_hash}"
            with self.database.transaction() as session:
                open_trades = list(session.scalars(select(Trade).where(Trade.symbol == self.symbol, Trade.state.in_((TradeState.OPEN.value, TradeState.PARTIALLY_CLOSED.value, TradeState.SUBMITTED.value)))))
                last_trade = session.scalar(select(Trade).where(Trade.symbol == self.symbol).order_by(Trade.opened_at.desc()).limit(1))
            total_risk_amount = sum(abs(item.entry_price - item.initial_stop_loss) / self.spec.trade_tick_size * self.spec.trade_tick_value * item.volume for item in open_trades)
            current_risk_percent = total_risk_amount / account.equity * 100 if account.equity > 0 else float("inf")
            proposed_risk_percent = sizing.loss_per_lot * sizing.volume / account.equity * 100 if account.equity > 0 else float("inf")
            nearest_distance = min((abs(entry - item.entry_price) / float(row.atr) for item in positions if item.side == evaluation.side.value), default=None)
            entry_cooldown_clear = not last_trade or not last_trade.opened_at or now - ensure_utc(last_trade.opened_at) >= timedelta(minutes=self.config.position_control.entry_cooldown_minutes)
            context = EntryContext(
                side=evaluation.side,
                open_position_sides=tuple(item.side for item in positions),
                open_position_count=len(positions),
                same_side_count=sum(item.side == evaluation.side.value for item in positions),
                basket_floating_profit=sum(item.profit for item in positions if item.side == evaluation.side.value),
                total_open_risk_percent=current_risk_percent,
                proposed_risk_percent=proposed_risk_percent,
                total_open_lot=sum(item.volume for item in positions),
                proposed_lot=sizing.volume,
                entry_distance_atr=nearest_distance,
                new_setup_candle=not self.duplicate_guard.candle_has_entry(self.symbol, candle_time, evaluation.side.value),
                entry_cooldown_clear=entry_cooldown_clear,
                cooldown_active=False,
                daily_risk_locked=False,
                idempotency_key_exists=self.duplicate_guard.key_exists(idempotency_key),
            )
            validation = self.entry_validator.validate(context)
            all_rules = evaluation.rules + session_rules + daily_rules + (entry_profile_rule, spread_rule) + validation.rules
            if not validation.passed:
                self._persist_decision(trend.direction, evaluation, all_rules, "NO_TRADE", validation.rejection_reason, tick, row, plan.stop_loss, plan.take_profit, plan.risk_reward)
                continue
            forex_rules = self._forex_trading_rules()
            all_rules = all_rules + forex_rules
            failed_forex_rule = next((rule for rule in forex_rules if not rule.passed), None)
            if failed_forex_rule is not None:
                self._persist_decision(trend.direction, evaluation, all_rules, "NO_TRADE", failed_forex_rule.reason_code, tick, row, plan.stop_loss, plan.take_profit, plan.risk_reward)
                continue
            hard_trade_rules = self._hard_trade_rules(
                self._portfolio_positions(),
                sizing.volume,
                context.same_side_count,
                context.basket_floating_profit,
                context.entry_distance_atr,
            )
            all_rules = all_rules + hard_trade_rules
            failed_hard_trade_rule = next((rule for rule in hard_trade_rules if not rule.passed), None)
            if failed_hard_trade_rule is not None:
                self._persist_decision(trend.direction, evaluation, all_rules, "NO_TRADE", failed_hard_trade_rule.reason_code, tick, row, plan.stop_loss, plan.take_profit, plan.risk_reward)
                continue
            win_rate_context_rules = (entry_profile_rule, spread_rule)
            win_rate_threshold = self._base_setup_win_rate_threshold("M1")
            recovery_rule, recovery_win_rate_threshold = self._recovery_mode_rule(win_rate_threshold)
            win_rate_threshold = self._apply_btc_weekend_setup_discount(now, recovery_win_rate_threshold)
            current_win_rate = self._calculated_setup_win_rate(evaluation, win_rate_context_rules)
            adaptive_rule, adaptive_win_rate_threshold = self._adaptive_learning_rule(
                evaluation,
                "M1",
                current_win_rate,
                win_rate_threshold,
                len(positions) + 1,
            )
            all_rules = all_rules + (recovery_rule, adaptive_rule)
            if not adaptive_rule.passed:
                self._persist_decision(trend.direction, evaluation, all_rules, "NO_TRADE", adaptive_rule.reason_code, tick, row, plan.stop_loss, plan.take_profit, plan.risk_reward)
                continue
            win_rate_rule = self._calculated_setup_win_rate_rule(
                evaluation,
                win_rate_context_rules,
                adaptive_win_rate_threshold,
                "HARD_TRADE_SETUP_WIN_RATE_GATE" if self.config.hard_trade.enabled else "CALCULATED_SETUP_WIN_RATE_GATE",
            )
            all_rules = all_rules + (win_rate_rule,)
            if not win_rate_rule.passed:
                self._persist_decision(trend.direction, evaluation, all_rules, "NO_TRADE", win_rate_rule.reason_code, tick, row, plan.stop_loss, plan.take_profit, plan.risk_reward)
                continue
            existing_basket = self._active_basket(evaluation.side.value)
            actual_risk = sizing.loss_per_lot * sizing.volume
            basket = self.basket_manager.ensure_active(evaluation.side.value, actual_risk if existing_basket is None else 0)
            intent = OrderIntent(self.symbol, idempotency_key, evaluation.signal_hash, candle_time, basket.id, basket.external_id, len(positions) + 1, plan, sizing, float(row.atr))
            outcome = self.execution.submit(intent)
            if outcome.success:
                if existing_basket is not None:
                    self.basket_manager.add_initial_risk(basket.external_id, actual_risk)
                with self.database.transaction() as session:
                    trade = session.get(Trade, outcome.trade_id) if outcome.trade_id is not None else None
                    if trade is not None:
                        trade.estimated_win_rate = current_win_rate
                self._persist_decision(trend.direction, evaluation, all_rules, "OPENED", None, tick, row, plan.stop_loss, plan.take_profit, plan.risk_reward)
                opened_any = True
                continue
            if existing_basket is None:
                self.basket_manager.discard_if_empty(basket.external_id, outcome.reason)
            self._persist_decision(trend.direction, evaluation, all_rules, "NO_TRADE", outcome.reason, tick, row, plan.stop_loss, plan.take_profit, plan.risk_reward)
        if not evaluated_any:
            evaluation = evaluations[0]
            self._persist_decision(trend.direction, evaluation, evaluation.rules + session_rules, "NO_TRADE", evaluation.rejection_reason, tick, row)
        return opened_any

    def _try_m15_quick_trade(self, now: datetime, daily_rules: tuple[RuleResult, ...], session_rules: tuple[RuleResult, ...], trend: TrendAssessment) -> bool:
        if not self.config.m15_quick_trade.enabled:
            return False
        m15 = self.indicators.calculate(self.candles.closed_candles(self.symbol, "M15", self.config.timeframes.candle_history))
        m5 = self.indicators.calculate(self.candles.closed_candles(self.symbol, "M5", self.config.timeframes.candle_history))
        row = m15.iloc[-1]
        tick = self.broker.tick(self.symbol)
        evaluation = self._m15_quick_evaluation(m15, m5)
        if evaluation.decision != "TRADE":
            self._persist_decision(trend.direction, evaluation, evaluation.rules + session_rules, "NO_TRADE", evaluation.rejection_reason, tick, row)
            return False
        entry = tick.ask if evaluation.side is SignalSide.BUY else tick.bid
        try:
            plan = self._m15_quick_plan(evaluation.side, entry, float(row.atr), float(tick.ask - tick.bid))
        except OrderValidationError as exc:
            rule = RuleResult(False, "M15_QUICK_PLAN_REJECTED", {"error": str(exc)})
            self._persist_decision(trend.direction, evaluation, evaluation.rules + session_rules + (rule,), "NO_TRADE", str(exc), tick, row)
            return False
        entry_profile_rule = self.session_guard.entry_profile_rule(now, evaluation.score)
        spread_rule = self.spread_guard.evaluate(tick, self.spec.point, float(row.atr))
        if not entry_profile_rule.passed or not spread_rule.passed:
            reason = entry_profile_rule.reason_code if not entry_profile_rule.passed else spread_rule.reason_code
            self._persist_decision(trend.direction, evaluation, evaluation.rules + session_rules + (entry_profile_rule, spread_rule), "NO_TRADE", reason, tick, row, plan.stop_loss, plan.take_profit, plan.risk_reward)
            return False
        account = self.broker.account()
        try:
            sizing = self._m15_quick_sizing(account.equity, plan)
        except OrderValidationError as exc:
            rule = RuleResult(False, "POSITION_SIZING_REJECTED", {"error": str(exc)})
            self._persist_decision(trend.direction, evaluation, evaluation.rules + session_rules + (entry_profile_rule, spread_rule, rule), "NO_TRADE", str(exc), tick, row, plan.stop_loss, plan.take_profit, plan.risk_reward)
            return False
        positions = self.broker.positions(self.symbol, self.config.broker.magic_number)
        candle_time = row.time.to_pydatetime() if hasattr(row.time, "to_pydatetime") else row.time
        idempotency_key = f"{self.symbol}_{evaluation.side.value}_M15Q_{int(ensure_utc(candle_time).timestamp())}_{evaluation.signal_hash}"
        with self.database.transaction() as session:
            open_trades = list(session.scalars(select(Trade).where(Trade.symbol == self.symbol, Trade.state.in_((TradeState.OPEN.value, TradeState.PARTIALLY_CLOSED.value, TradeState.SUBMITTED.value)))))
            last_trade = session.scalar(select(Trade).where(Trade.symbol == self.symbol).order_by(Trade.opened_at.desc()).limit(1))
        total_risk_amount = sum(abs(item.entry_price - item.initial_stop_loss) / self.spec.trade_tick_size * self.spec.trade_tick_value * item.volume for item in open_trades)
        current_risk_percent = total_risk_amount / account.equity * 100 if account.equity > 0 else float("inf")
        proposed_risk_percent = sizing.loss_per_lot * sizing.volume / account.equity * 100 if account.equity > 0 else float("inf")
        nearest_distance = min((abs(entry - item.entry_price) / float(row.atr) for item in positions), default=None)
        entry_cooldown_clear = not last_trade or not last_trade.opened_at or now - ensure_utc(last_trade.opened_at) >= timedelta(minutes=self.config.position_control.entry_cooldown_minutes)
        context = EntryContext(
            side=evaluation.side, open_position_sides=tuple(item.side for item in positions), open_position_count=len(positions),
            same_side_count=sum(item.side == evaluation.side.value for item in positions),
            basket_floating_profit=sum(item.profit for item in positions if item.side == evaluation.side.value),
            total_open_risk_percent=current_risk_percent, proposed_risk_percent=proposed_risk_percent,
            total_open_lot=sum(item.volume for item in positions), proposed_lot=sizing.volume,
            entry_distance_atr=nearest_distance, new_setup_candle=not self.duplicate_guard.candle_has_entry(self.symbol, candle_time, evaluation.side.value),
            entry_cooldown_clear=entry_cooldown_clear, cooldown_active=False, daily_risk_locked=False,
            idempotency_key_exists=self.duplicate_guard.key_exists(idempotency_key),
        )
        validation = self.entry_validator.validate(context)
        all_rules = evaluation.rules + session_rules + daily_rules + (entry_profile_rule, spread_rule) + validation.rules
        if not validation.passed:
            self._persist_decision(trend.direction, evaluation, all_rules, "NO_TRADE", validation.rejection_reason, tick, row, plan.stop_loss, plan.take_profit, plan.risk_reward)
            return False
        hard_trade_rules = self._hard_trade_rules(self._portfolio_positions(), sizing.volume, context.same_side_count, context.basket_floating_profit, context.entry_distance_atr)
        all_rules = all_rules + hard_trade_rules
        failed_hard_trade_rule = next((rule for rule in hard_trade_rules if not rule.passed), None)
        if failed_hard_trade_rule is not None:
            self._persist_decision(trend.direction, evaluation, all_rules, "NO_TRADE", failed_hard_trade_rule.reason_code, tick, row, plan.stop_loss, plan.take_profit, plan.risk_reward)
            return False
        current_win_rate = self._calculated_setup_win_rate(evaluation, (entry_profile_rule, spread_rule))
        base_threshold = self.config.m15_quick_trade.minimum_setup_win_rate
        recovery_rule, _ = self._recovery_mode_rule(base_threshold)
        adaptive_rule, adaptive_threshold = self._adaptive_learning_rule(evaluation, "M15Q", current_win_rate, base_threshold, len(positions) + 1)
        win_rate_rule = self._calculated_setup_win_rate_rule(evaluation, (entry_profile_rule, spread_rule), adaptive_threshold, "M15_QUICK_SETUP_WIN_RATE_GATE")
        all_rules = all_rules + (recovery_rule, adaptive_rule, win_rate_rule)
        if not adaptive_rule.passed:
            self._persist_decision(trend.direction, evaluation, all_rules, "NO_TRADE", adaptive_rule.reason_code, tick, row, plan.stop_loss, plan.take_profit, plan.risk_reward)
            return False
        if not win_rate_rule.passed:
            self._persist_decision(trend.direction, evaluation, all_rules, "NO_TRADE", win_rate_rule.reason_code, tick, row, plan.stop_loss, plan.take_profit, plan.risk_reward)
            return False
        existing_basket = self._active_basket(evaluation.side.value)
        actual_risk = sizing.loss_per_lot * sizing.volume
        basket = self.basket_manager.ensure_active(evaluation.side.value, actual_risk if existing_basket is None else 0)
        intent = OrderIntent(self.symbol, idempotency_key, evaluation.signal_hash, candle_time, basket.id, basket.external_id, len(positions) + 1, plan, sizing, float(row.atr))
        outcome = self.execution.submit(intent)
        if outcome.success:
            if existing_basket is not None:
                self.basket_manager.add_initial_risk(basket.external_id, actual_risk)
            with self.database.transaction() as session:
                trade = session.get(Trade, outcome.trade_id) if outcome.trade_id is not None else None
                if trade is not None:
                    trade.estimated_win_rate = current_win_rate
            self._persist_decision(trend.direction, evaluation, all_rules, "OPENED", None, tick, row, plan.stop_loss, plan.take_profit, plan.risk_reward)
            return True
        if existing_basket is None:
            self.basket_manager.discard_if_empty(basket.external_id, outcome.reason)
        self._persist_decision(trend.direction, evaluation, all_rules, "NO_TRADE", outcome.reason, tick, row, plan.stop_loss, plan.take_profit, plan.risk_reward)
        return False

    def signal_cycle(self) -> None:
        if not self._signal_lock.acquire(blocking=False):
            return
        try:
            if not self._ensure_connection() or self._manual_pause:
                return
            if self._is_forex_runtime_symbol() and not self.config.forex_trading.enabled:
                self.health.record(
                    "entry_control",
                    "OK",
                    "Forex mode disabled, entry scan skipped for open forex runtime symbol",
                    {"symbol": self.symbol},
                )
                return
            now = datetime.now(UTC)
            cooldown = self.cooldown_guard.active(now)
            if cooldown:
                self._set_state(BotState.COOLDOWN, f"COOLDOWN_UNTIL:{ensure_utc(cooldown.expires_at).isoformat()}")
                return
            daily_allowed, _, daily_rules = self._daily_status(now)
            if not daily_allowed:
                self._set_state(BotState.RISK_PAUSED, next(rule.reason_code for rule in daily_rules if not rule.passed))
                return
            if self.state in (BotState.COOLDOWN, BotState.RISK_PAUSED):
                self._set_state(BotState.RUNNING, "ENTRY_GUARDS_CLEARED")
            if self.state is not BotState.RUNNING:
                return
            setup_timeframe = self.config.hard_trade.preferred_setup_timeframe if self.config.hard_trade.enabled else self.config.timeframes.setup
            entry_timeframe = self.config.hard_trade.preferred_entry_timeframe if self.config.hard_trade.enabled else self.config.timeframes.entry
            latest_time = self.candles.latest_closed_time(self.symbol, entry_timeframe)
            candle_time = latest_time.to_pydatetime() if hasattr(latest_time, "to_pydatetime") else latest_time
            if self._last_signal_candle and ensure_utc(candle_time) <= ensure_utc(self._last_signal_candle):
                return
            self._last_signal_candle = candle_time
            self.health.set_last_candle(candle_time)
            session_allowed, session_rules = self.session_guard.evaluate(now)
            if not session_allowed:
                self._persist_decision(TrendDirection.UNCERTAIN, None, session_rules, "NO_TRADE", next(rule.reason_code for rule in session_rules if not rule.passed))
                return
            self._try_fast_scalp(now, daily_rules, session_rules)

            signal_engine = self._weekend_btc_signal_engine(now)
            btc_weekend_max_atr_multiplier = self._weekend_btc_max_atr_multiplier(now)
            frames = {
                timeframe: self.indicators.calculate(self.candles.closed_candles(self.symbol, timeframe, self.config.timeframes.candle_history))
                for timeframe in ("H4", "H1", setup_timeframe, entry_timeframe)
            }
            self._store_indicators(frames)
            trend = self.trend_detector.detect(frames["H4"], frames["H1"])
            setup_row = frames[setup_timeframe].iloc[-1]
            tick = self.broker.tick(self.symbol)
            intended_side = SignalSide.BUY if trend.direction is TrendDirection.BULLISH else SignalSide.SELL if trend.direction is TrendDirection.BEARISH else SignalSide.NO_TRADE
            if intended_side is SignalSide.NO_TRADE:
                if self._try_m15_quick_trade(now, daily_rules, session_rules, trend):
                    return
                evaluation = signal_engine.evaluate(trend, frames[setup_timeframe], frames[entry_timeframe], self.config.take_profit.default_risk_reward)
                self._persist_decision(trend.direction, evaluation, evaluation.rules + session_rules, "NO_TRADE", evaluation.rejection_reason, tick, setup_row)
                return
            entry = tick.ask if intended_side is SignalSide.BUY else tick.bid
            try:
                plan = self.risk_manager.plan(
                    intended_side,
                    entry,
                    float(setup_row.atr),
                    float(setup_row.last_swing_low),
                    float(setup_row.last_swing_high),
                    self.spec,
                    btc_weekend_max_atr_multiplier,
                )
            except OrderValidationError as exc:
                fallback = signal_engine.evaluate(trend, frames[setup_timeframe], frames[entry_timeframe], self.config.take_profit.default_risk_reward)
                if (
                    "maximum ATR distance" in str(exc)
                    and self._is_forex_runtime_symbol()
                    and fallback.score >= self.config.stop_loss.relaxed_forex_minimum_signal_score
                ):
                    try:
                        plan = self.risk_manager.plan(
                            intended_side,
                            entry,
                            float(setup_row.atr),
                            float(setup_row.last_swing_low),
                            float(setup_row.last_swing_high),
                            self.spec,
                            self.config.stop_loss.relaxed_forex_maximum_atr_multiplier,
                        )
                    except OrderValidationError as relaxed_exc:
                        rule = RuleResult(False, "SL_TP_PLAN_REJECTED", {"error": str(relaxed_exc), "relaxed_forex": True})
                        self._persist_decision(trend.direction, fallback, fallback.rules + session_rules + (rule,), "NO_TRADE", str(relaxed_exc), tick, setup_row)
                        return
                else:
                    rule = RuleResult(False, "SL_TP_PLAN_REJECTED", {"error": str(exc)})
                    self._persist_decision(trend.direction, fallback, fallback.rules + session_rules + (rule,), "NO_TRADE", str(exc), tick, setup_row)
                    return
            else:
                fallback = None
            if fallback is not None:
                relaxed_rule = RuleResult(True, "RELAXED_FOREX_SL_ATR_FOR_HIGH_SCORE", {
                    "score": fallback.score,
                    "minimum_score": self.config.stop_loss.relaxed_forex_minimum_signal_score,
                    "maximum_atr_multiplier": self.config.stop_loss.relaxed_forex_maximum_atr_multiplier,
                    "stop_atr_multiple": plan.stop_atr_multiple,
                })
            else:
                relaxed_rule = None
            evaluation = signal_engine.evaluate(trend, frames[setup_timeframe], frames[entry_timeframe], plan.risk_reward)
            entry_profile_rule = self.session_guard.entry_profile_rule(now, evaluation.score)
            spread_rule = self.spread_guard.evaluate(tick, self.spec.point, float(setup_row.atr))
            if evaluation.decision != "TRADE" or not entry_profile_rule.passed or not spread_rule.passed:
                reason = (
                    evaluation.rejection_reason
                    if evaluation.decision != "TRADE"
                    else entry_profile_rule.reason_code
                    if not entry_profile_rule.passed
                    else spread_rule.reason_code
                )
                self._persist_decision(
                    trend.direction,
                    evaluation,
                    evaluation.rules + session_rules + tuple(rule for rule in (relaxed_rule, entry_profile_rule, spread_rule) if rule is not None),
                    "NO_TRADE",
                    reason,
                    tick,
                    setup_row,
                    plan.stop_loss,
                    plan.take_profit,
                    plan.risk_reward,
                )
                return

            account = self.broker.account()
            try:
                sizing = PositionSizer.calculate(account.equity, self.config.risk.risk_per_entry_percent, plan.entry, plan.stop_loss, self.spec, self._max_lot_per_entry())
            except OrderValidationError as exc:
                sizing_rule = RuleResult(False, "POSITION_SIZING_REJECTED", {"error": str(exc)})
                self._persist_decision(
                    trend.direction,
                    evaluation,
                    evaluation.rules + session_rules + (entry_profile_rule, spread_rule, sizing_rule),
                    "NO_TRADE",
                    str(exc),
                    tick,
                    setup_row,
                    plan.stop_loss,
                    plan.take_profit,
                    plan.risk_reward,
                )
                return
            positions = self.broker.positions(self.symbol, self.config.broker.magic_number)
            idempotency_key = f"{self.symbol}_{intended_side.value}_{entry_timeframe}_{int(candle_time.timestamp())}_{evaluation.signal_hash}"
            with self.database.transaction() as session:
                open_trades = list(session.scalars(select(Trade).where(Trade.symbol == self.symbol, Trade.state.in_((TradeState.OPEN.value, TradeState.PARTIALLY_CLOSED.value, TradeState.SUBMITTED.value)))))
                last_trade = session.scalar(select(Trade).where(Trade.symbol == self.symbol).order_by(Trade.opened_at.desc()).limit(1))
            total_risk_amount = sum(abs(item.entry_price - item.initial_stop_loss) / self.spec.trade_tick_size * self.spec.trade_tick_value * item.volume for item in open_trades)
            current_risk_percent = total_risk_amount / account.equity * 100 if account.equity > 0 else float("inf")
            proposed_risk_percent = sizing.loss_per_lot * sizing.volume / account.equity * 100 if account.equity > 0 else float("inf")
            nearest_distance = min((abs(entry - item.entry_price) / float(setup_row.atr) for item in positions), default=None)
            entry_cooldown_clear = not last_trade or not last_trade.opened_at or now - ensure_utc(last_trade.opened_at) >= timedelta(minutes=self.config.position_control.entry_cooldown_minutes)
            context = EntryContext(
                side=intended_side, open_position_sides=tuple(item.side for item in positions), open_position_count=len(positions),
                same_side_count=sum(item.side == intended_side.value for item in positions),
                basket_floating_profit=sum(item.profit for item in positions if item.side == intended_side.value),
                total_open_risk_percent=current_risk_percent, proposed_risk_percent=proposed_risk_percent,
                total_open_lot=sum(item.volume for item in positions), proposed_lot=sizing.volume,
                entry_distance_atr=nearest_distance, new_setup_candle=not self.duplicate_guard.candle_has_entry(self.symbol, candle_time, intended_side.value),
                entry_cooldown_clear=entry_cooldown_clear, cooldown_active=False, daily_risk_locked=False,
                idempotency_key_exists=self.duplicate_guard.key_exists(idempotency_key),
            )
            validation = self.entry_validator.validate(context)
            all_rules = evaluation.rules + session_rules + daily_rules + tuple(rule for rule in (relaxed_rule, entry_profile_rule, spread_rule) if rule is not None) + validation.rules
            if not validation.passed:
                self._persist_decision(trend.direction, evaluation, all_rules, "NO_TRADE", validation.rejection_reason, tick, setup_row, plan.stop_loss, plan.take_profit, plan.risk_reward)
                return
            forex_rules = self._forex_trading_rules()
            all_rules = all_rules + forex_rules
            failed_forex_rule = next((rule for rule in forex_rules if not rule.passed), None)
            if failed_forex_rule is not None:
                self._persist_decision(trend.direction, evaluation, all_rules, "NO_TRADE", failed_forex_rule.reason_code, tick, setup_row, plan.stop_loss, plan.take_profit, plan.risk_reward)
                return
            hard_trade_rules = self._hard_trade_rules(
                self._portfolio_positions(),
                sizing.volume,
                context.same_side_count,
                context.basket_floating_profit,
                context.entry_distance_atr,
            )
            all_rules = all_rules + hard_trade_rules
            failed_hard_trade_rule = next((rule for rule in hard_trade_rules if not rule.passed), None)
            if failed_hard_trade_rule is not None:
                self._persist_decision(trend.direction, evaluation, all_rules, "NO_TRADE", failed_hard_trade_rule.reason_code, tick, setup_row, plan.stop_loss, plan.take_profit, plan.risk_reward)
                return
            win_rate_context_rules = (entry_profile_rule, spread_rule)
            win_rate_threshold = self._base_setup_win_rate_threshold(entry_timeframe)
            recovery_rule, recovery_win_rate_threshold = self._recovery_mode_rule(win_rate_threshold)
            win_rate_threshold = self._apply_btc_weekend_setup_discount(now, recovery_win_rate_threshold)
            current_win_rate = self._calculated_setup_win_rate(evaluation, win_rate_context_rules)
            adaptive_rule, adaptive_win_rate_threshold = self._adaptive_learning_rule(
                evaluation,
                setup_timeframe,
                current_win_rate,
                win_rate_threshold,
                len(positions) + 1,
            )
            all_rules = all_rules + (recovery_rule, adaptive_rule)
            if not adaptive_rule.passed:
                self._persist_decision(trend.direction, evaluation, all_rules, "NO_TRADE", adaptive_rule.reason_code, tick, setup_row, plan.stop_loss, plan.take_profit, plan.risk_reward)
                return
            win_rate_rule = self._calculated_setup_win_rate_rule(
                evaluation,
                win_rate_context_rules,
                adaptive_win_rate_threshold,
                "HARD_TRADE_SETUP_WIN_RATE_GATE" if self.config.hard_trade.enabled else "CALCULATED_SETUP_WIN_RATE_GATE",
            )
            all_rules = all_rules + (win_rate_rule,)
            if not win_rate_rule.passed:
                self._persist_decision(trend.direction, evaluation, all_rules, "NO_TRADE", win_rate_rule.reason_code, tick, setup_row, plan.stop_loss, plan.take_profit, plan.risk_reward)
                return

            if self._stop_event.is_set() or self._manual_pause or self.state is not BotState.RUNNING:
                self._persist_decision(trend.direction, evaluation, all_rules, "NO_TRADE", "BOT_NOT_RUNNING_AT_EXECUTION_BOUNDARY", tick, setup_row, plan.stop_loss, plan.take_profit, plan.risk_reward)
                return

            existing_basket = self._active_basket(intended_side.value)
            actual_risk = sizing.loss_per_lot * sizing.volume
            basket = self.basket_manager.ensure_active(intended_side.value, actual_risk if existing_basket is None else 0)
            intent = OrderIntent(self.symbol, idempotency_key, evaluation.signal_hash, candle_time, basket.id, basket.external_id, len(positions) + 1, plan, sizing, float(setup_row.atr))
            outcome = self.execution.submit(intent)
            if outcome.success:
                if existing_basket is not None:
                    self.basket_manager.add_initial_risk(basket.external_id, actual_risk)
                with self.database.transaction() as session:
                    trade = session.get(Trade, outcome.trade_id) if outcome.trade_id is not None else None
                    if trade is not None:
                        trade.estimated_win_rate = self._calculated_setup_win_rate(evaluation, win_rate_context_rules)
                self._persist_decision(trend.direction, evaluation, all_rules, "OPENED", None, tick, setup_row, plan.stop_loss, plan.take_profit, plan.risk_reward)
            else:
                if existing_basket is None:
                    self.basket_manager.discard_if_empty(basket.external_id, outcome.reason)
                self._persist_decision(trend.direction, evaluation, all_rules, "NO_TRADE", outcome.reason, tick, setup_row, plan.stop_loss, plan.take_profit, plan.risk_reward)
        finally:
            self._signal_lock.release()

    def position_cycle(self) -> None:
        if self.state in (BotState.STOPPED, BotState.STARTING):
            return
        # Serialise basket inspection with signal submission. Without this,
        # the management loop can observe the new basket in the milliseconds
        # before its order is reserved/confirmed and mistake it for an exit.
        if not self._signal_lock.acquire(blocking=False):
            return
        try:
            # MT5's Python adapter is also serialized by this lock. Concurrent
            # terminal_info/candle/position calls can deadlock the native API.
            if not self._ensure_connection():
                return
            self._cleanup_old_closed_trades()
            positions = self.broker.positions(self.symbol, self.config.broker.magic_number)
            baskets = self._active_baskets()
            if positions and not baskets:
                self.health.set_broker_synchronized(False)
                self._set_state(BotState.ENTRY_PAUSED, "POSITIONS_WITHOUT_ACTIVE_BASKET", {"tickets": [item.ticket for item in positions]})
                return
            self.health.set_broker_synchronized(True)
            now = datetime.now(UTC)
            daily_close_reason: CloseReason | None = None
            daily_close_threshold: float | None = None
            try:
                _, _, daily_rules = self._daily_status(now)
                daily_close_reason, daily_close_threshold = self._daily_close_trigger(daily_rules)
            except Exception as exc:
                # Daily accounting is an entry guard; it must never disable management
                # of positions that are already exposed to the market.
                self.health.record("daily_risk", "ERROR", "Daily statistics update failed", {"error": str(exc)})
            if not baskets:
                return
            account = self.broker.account()
            if daily_close_reason:
                all_closed = True
                for basket in baskets:
                    metrics = self.basket_manager.synchronize(basket.external_id)
                    basket_exit = self.basket_manager.exit_decision(metrics, basket.initial_risk_amount, account.equity, basket.external_id)
                    close_reason = (
                        CloseReason.TAKE_PROFIT
                        if basket_exit.should_close and basket_exit.reason is CloseReason.TAKE_PROFIT
                        else daily_close_reason
                    )
                    threshold = basket_exit.threshold if close_reason is CloseReason.TAKE_PROFIT else daily_close_threshold
                    self._set_state(BotState.CLOSING_BASKET, close_reason.value, {"profit": metrics.combined_profit, "threshold": threshold})
                    all_closed = self.basket_manager.close_basket(basket.external_id, close_reason) and all_closed
                if all_closed:
                    self._pending_trend_reversal = False
                    self._set_state(BotState.COOLDOWN, f"PORTFOLIO_DAILY_CLOSE:{daily_close_reason.value}")
                else:
                    self._set_state(BotState.ENTRY_PAUSED, "PORTFOLIO_DAILY_CLOSE_FAILED")
                return
            if self._is_forex_runtime_symbol():
                forex_decision = self._forex_group_exit_decision(account.equity)
                if forex_decision.should_close and forex_decision.reason is not None:
                    if self._close_own_forex_baskets_for_group(
                        forex_decision.reason,
                        forex_decision.threshold,
                        forex_decision.current_profit,
                    ):
                        return
            for basket in baskets:
                basket_positions = self.basket_manager.basket_positions(basket.external_id, positions)
                if not basket_positions:
                    metrics = self.basket_manager.synchronize(basket.external_id)
                    with self.database.transaction() as session:
                        basket_trade_count = int(session.scalar(select(func.count(Trade.id)).where(Trade.basket_id == basket.id)) or 0)
                    broker_side_single_tp = metrics.combined_profit >= 0 and basket_trade_count <= 1
                    inferred_reason = (
                        CloseReason.BROKER_EXIT
                        if broker_side_single_tp
                        else CloseReason.TAKE_PROFIT
                        if metrics.combined_profit >= 0
                        else CloseReason.STOP_LOSS
                    )
                    if self.basket_manager.finalize_empty(basket.external_id, inferred_reason):
                        cooldown = None if broker_side_single_tp else self.cooldown_guard.activate(inferred_reason, basket.external_id, now)
                        if cooldown is not None and not self._manual_pause:
                            self._set_state(BotState.COOLDOWN, f"BROKER_SIDE_BASKET_EXIT:{inferred_reason.value}")
                    continue
                metrics = self.basket_manager.synchronize(basket.external_id)
                exit_decision = self.basket_manager.exit_decision(metrics, basket.initial_risk_amount, account.equity, basket.external_id)
                priority_reason: CloseReason | None = None
                threshold: float | None = None
                if self.session_guard.should_close_for_weekend(now):
                    priority_reason = CloseReason.WEEKEND
                elif exit_decision.should_close:
                    priority_reason = exit_decision.reason
                    threshold = exit_decision.threshold
                if priority_reason:
                    self._set_state(BotState.CLOSING_BASKET, priority_reason.value, {"profit": metrics.combined_profit, "threshold": threshold})
                    closed = self.basket_manager.close_basket(basket.external_id, priority_reason)
                    if closed:
                        self._pending_trend_reversal = False
                        self.cooldown_guard.activate(priority_reason, basket.external_id, now)
                        self._set_state(BotState.COOLDOWN, f"BASKET_CLOSED:{priority_reason.value}")
                    else:
                        self._set_state(BotState.ENTRY_PAUSED, "BASKET_CLOSE_FAILED")
                    return
            latest_time = self.candles.latest_closed_time(self.symbol, "M5")
            management_time = latest_time.to_pydatetime() if hasattr(latest_time, "to_pydatetime") else latest_time
            management_due = self.config.hard_trade.enabled or self._last_management_candle is None or ensure_utc(management_time) > ensure_utc(self._last_management_candle)
            if management_due:
                m5_frame = self.indicators.calculate(self.candles.closed_candles(self.symbol, "M5", self.config.timeframes.candle_history))
                self._latest_management_atr = float(m5_frame.iloc[-1].atr)
                m15_frame = self.indicators.calculate(self.candles.closed_candles(self.symbol, "M15", self.config.timeframes.candle_history))
                h4_frame = self.indicators.calculate(self.candles.closed_candles(self.symbol, "H4", self.config.timeframes.candle_history))
                h1_frame = self.indicators.calculate(self.candles.closed_candles(self.symbol, "H1", self.config.timeframes.candle_history))
                current_trend = self.trend_detector.detect(h4_frame, h1_frame)
                rotation = self.signal_engine.evaluate(current_trend, m15_frame, m5_frame, self.config.take_profit.default_risk_reward)
                revalidation = self.position_manager.revalidate(
                    positions,
                    current_trend,
                    m15_frame,
                    m5_frame,
                    rotation,
                    str(int(ensure_utc(management_time).timestamp())),
                )
                if revalidation.closed:
                    for active in self._active_baskets():
                        self.basket_manager.synchronize(active.external_id)
                    positions = self.broker.positions(self.symbol, self.config.broker.magic_number)
                active_baskets = self._active_baskets()
                self._pending_trend_reversal = (
                    (self.config.hard_trade.enabled or not self.config.position_control.allow_opposite_positions)
                    and any(self.exit_signal_engine.trend_reversal(active.direction, current_trend).passed for active in active_baskets)
                )
                self._last_management_candle = management_time
            close_reason = CloseReason.TREND_REVERSAL if self._pending_trend_reversal else None
            if close_reason:
                all_closed = True
                for active in self._active_baskets():
                    metrics = self.basket_manager.synchronize(active.external_id)
                    self._set_state(BotState.CLOSING_BASKET, close_reason.value, {"profit": metrics.combined_profit})
                    all_closed = self.basket_manager.close_basket(active.external_id, close_reason) and all_closed
                if all_closed:
                    self._pending_trend_reversal = False
                    self._set_state(BotState.COOLDOWN, f"BASKET_CLOSED:{close_reason.value}")
                else:
                    self._set_state(BotState.ENTRY_PAUSED, "BASKET_CLOSE_FAILED")
                return
            if self._latest_management_atr is None:
                frame = self.indicators.calculate(self.candles.closed_candles(self.symbol, "M5", self.config.timeframes.candle_history))
                self._latest_management_atr = float(frame.iloc[-1].atr)
            self.position_manager.manage(positions, self._latest_management_atr)
        finally:
            self._signal_lock.release()
