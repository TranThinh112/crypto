"""Create a GitHub-safe learning seed from the local learning export.

The live export contains broker ticket IDs and idempotency keys from real
orders. This script keeps the behavioral learning fields and removes local
broker identifiers so the resulting JSONL can be committed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data" / "learning_export.jsonl"
DEFAULT_TARGET = ROOT / "data" / "learning_seed.jsonl"

DROP_FIELDS = {
    "broker_ticket",
    "idempotency_key",
    "trade_id",
    "basket_id",
    "exported_at",
}


def clean_record(record: dict[str, Any], index: int) -> dict[str, Any]:
    cleaned = {key: value for key, value in record.items() if key not in DROP_FIELDS}
    fingerprint = str(cleaned.get("setup_fingerprint") or "")
    source = "|".join([
        str(cleaned.get("symbol") or ""),
        str(cleaned.get("side") or ""),
        str(cleaned.get("timeframe") or ""),
        str(cleaned.get("entry_candle_time") or cleaned.get("opened_at") or ""),
        fingerprint,
        str(index),
    ])
    cleaned["seed_id"] = hashlib.sha256(source.encode("utf-8")).hexdigest()[:20]
    cleaned["source"] = "sanitized_learning_seed"
    return dict(sorted(cleaned.items()))


def sanitize(source: Path, target: Path) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with source.open("r", encoding="utf-8") as src, target.open("w", encoding="utf-8") as dst:
        for line in src:
            text = line.strip()
            if not text:
                continue
            record = json.loads(text)
            count += 1
            dst.write(json.dumps(clean_record(record, count), ensure_ascii=False, sort_keys=True) + "\n")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Sanitize learning_export.jsonl for GitHub.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args()
    count = sanitize(args.source, args.target)
    print(f"Wrote {count} sanitized learning records to {args.target}")


if __name__ == "__main__":
    main()
