"""Secret-safe JSON structured logging with rotation."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class JsonFormatter(logging.Formatter):
    ALLOWED_EXTRA = ("event_type", "symbol", "basket_id", "trade_id", "bot_state", "context")

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(), "level": record.levelname,
            "event_type": getattr(record, "event_type", "APPLICATION"), "symbol": getattr(record, "symbol", None),
            "basket_id": getattr(record, "basket_id", None), "trade_id": getattr(record, "trade_id", None),
            "bot_state": getattr(record, "bot_state", None), "message": record.getMessage(),
            "context": getattr(record, "context", {}),
        }
        if record.exc_info:
            payload["context"] = {**payload["context"], "exception": self.formatException(record.exc_info)}
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(log_dir: Path, level: str = "INFO") -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = JsonFormatter()
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level.upper())

    def handler(filename: str, handler_level: int = logging.DEBUG) -> RotatingFileHandler:
        value = RotatingFileHandler(log_dir / filename, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
        value.setLevel(handler_level)
        value.setFormatter(formatter)
        return value

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)
    root.addHandler(handler("application.log"))
    root.addHandler(handler("error.log", logging.ERROR))
    for name, filename in (("trading", "trading.log"), ("execution", "execution.log"), ("risk", "risk.log")):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.addHandler(handler(filename))
        logger.propagate = True
