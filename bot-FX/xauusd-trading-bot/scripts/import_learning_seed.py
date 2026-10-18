"""Import sanitized learning seed records into a fresh local database."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import get_app_settings
from app.database import Database
from app.models.trade import Trade
from app.utils.enums import TradeState


DEFAULT_SEED = PROJECT_ROOT / os.getenv("LEARNING_SEED_PATH", "data/learning_seed.jsonl")


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def trade_from_seed(record: dict[str, Any]) -> Trade:
    seed_id = str(record["seed_id"])
    symbol = str(record.get("symbol") or "UNKNOWN")
    side = str(record.get("side") or "UNKNOWN")
    timeframe = str(record.get("timeframe") or "NA")
    entry_time = parse_dt(record.get("entry_candle_time")) or parse_dt(record.get("opened_at")) or datetime.utcnow()
    return Trade(
        basket_id=None,
        broker_ticket=None,
        idempotency_key=f"seed_{symbol}_{side}_{timeframe}_{seed_id}",
        symbol=symbol,
        side=side,
        state=TradeState.CLOSED.value,
        volume=float(record.get("initial_volume") or 0.0),
        initial_volume=float(record.get("initial_volume") or 0.0),
        entry_price=float(record.get("entry_price") or 0.0),
        stop_loss=float(record.get("initial_stop_loss") or 0.0),
        initial_stop_loss=float(record.get("initial_stop_loss") or 0.0),
        take_profit=float(record.get("take_profit") or 0.0),
        realized_profit=float(record.get("realized_profit") or 0.0),
        floating_profit=float(record.get("floating_profit") or 0.0),
        estimated_win_rate=record.get("estimated_win_rate"),
        entry_number=record.get("entry_number"),
        initial_risk_amount=record.get("initial_risk_amount"),
        max_adverse_profit=float(record.get("max_adverse_profit") or 0.0),
        max_favorable_profit=float(record.get("max_favorable_profit") or 0.0),
        max_adverse_r=float(record.get("max_adverse_r") or 0.0),
        max_favorable_r=float(record.get("max_favorable_r") or 0.0),
        signal_hash=str(record.get("setup_fingerprint") or seed_id),
        entry_candle_time=entry_time,
        partial_levels_completed=[],
        break_even_applied=bool(record.get("break_even_applied") or False),
        opened_at=parse_dt(record.get("opened_at")),
        closed_at=parse_dt(record.get("closed_at")),
        close_reason=record.get("close_reason"),
    )


def import_seed(path: Path) -> tuple[int, int]:
    load_dotenv()
    database = Database(get_app_settings().database_url)
    database.create_schema()
    inserted = 0
    skipped = 0
    with database.transaction() as session:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            trade = trade_from_seed(record)
            exists = session.query(Trade.id).filter(Trade.idempotency_key == trade.idempotency_key).first()
            if exists:
                skipped += 1
                continue
            session.add(trade)
            inserted += 1
    return inserted, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Import sanitized learning seed records.")
    parser.add_argument("--path", type=Path, default=DEFAULT_SEED)
    args = parser.parse_args()
    inserted, skipped = import_seed(args.path)
    print(f"Imported {inserted} learning seed records, skipped {skipped} existing records.")


if __name__ == "__main__":
    main()
