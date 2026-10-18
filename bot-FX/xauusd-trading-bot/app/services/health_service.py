"""Runtime health aggregation and persistent health events."""

from __future__ import annotations

import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.broker.mt5_client import BrokerClient
from app.database import Database
from app.models.event_log import HealthEvent


class HealthService:
    def __init__(self, database: Database, broker: BrokerClient, symbol: str, project_path: Path) -> None:
        self.database = database
        self.broker = broker
        self.symbol = symbol
        self.project_path = project_path
        self._heartbeats: dict[str, datetime] = {}
        self._last_candle_time: datetime | None = None
        self._broker_synchronized = False
        self._lock = threading.Lock()

    def heartbeat(self, component: str) -> None:
        with self._lock:
            self._heartbeats[component] = datetime.now(UTC)

    def set_last_candle(self, value: datetime) -> None:
        with self._lock:
            self._last_candle_time = value

    def set_broker_synchronized(self, value: bool) -> None:
        with self._lock:
            self._broker_synchronized = value

    def record(self, component: str, status: str, message: str, details: dict[str, Any] | None = None) -> None:
        with self.database.transaction() as session:
            session.add(HealthEvent(component=component, status=status, message=message, details=details or {}))

    def snapshot(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        connected = self.broker.is_connected()
        tick_age: float | None = None
        account: dict[str, float] | None = None
        if connected:
            try:
                tick_age = max(0.0, (now - self.broker.tick(self.symbol).time).total_seconds())
                value = self.broker.account()
                account = {"equity": value.equity, "free_margin": value.margin_free, "margin_level": value.margin_level}
            except Exception:
                connected = False
        disk = shutil.disk_usage(self.project_path)
        with self._lock:
            heartbeat_ages = {name: (now - value).total_seconds() for name, value in self._heartbeats.items()}
            candle_age = (now - self._last_candle_time).total_seconds() if self._last_candle_time else None
            synchronized = self._broker_synchronized
        healthy = connected and self.database.healthcheck() and synchronized and tick_age is not None and tick_age <= 30 and all(age <= 30 for age in heartbeat_ages.values())
        return {
            "healthy": healthy, "mt5_connected": connected, "database_connected": self.database.healthcheck(),
            "last_tick_age_seconds": tick_age, "last_candle_age_seconds": candle_age,
            "loop_heartbeat_age_seconds": heartbeat_ages, "broker_synchronized": synchronized,
            "account": account, "disk_free_bytes": disk.free, "checked_at": now.isoformat(),
        }
