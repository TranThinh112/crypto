from __future__ import annotations

import json
import argparse
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "trading_bot.db"
API = "http://127.0.0.1:8000"
POLL_SECONDS = 1.0
POSITION_LOG_SECONDS = 5.0
MAX_LOG_BYTES = 10 * 1024 * 1024
MAX_ROTATED_LOGS = 5


def rotate_log_if_needed(path: Path) -> None:
    if not path.exists() or path.stat().st_size < MAX_LOG_BYTES:
        return
    oldest = path.with_name(f"{path.name}.{MAX_ROTATED_LOGS}")
    if oldest.exists():
        oldest.unlink()
    for index in range(MAX_ROTATED_LOGS - 1, 0, -1):
        current = path.with_name(f"{path.name}.{index}")
        if current.exists():
            current.replace(path.with_name(f"{path.name}.{index + 1}"))
    path.replace(path.with_name(f"{path.name}.1"))


def log(path: Path, message: str) -> None:
    rotate_log_if_needed(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")


def get_json(path: str) -> dict | list | None:
    try:
        with urllib.request.urlopen(API + path, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"error": str(exc)}


def table_cols(cur: sqlite3.Cursor, table: str) -> list[str]:
    return [row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()]


def signal_rows_after(cur: sqlite3.Cursor, last_id: int) -> list[dict]:
    cols = table_cols(cur, "signal_decisions")
    rows = cur.execute(
        f"SELECT {', '.join(cols)} FROM signal_decisions WHERE id > ? ORDER BY id ASC",
        (last_id,),
    ).fetchall()
    values = []
    for row in rows:
        item = dict(zip(cols, row))
        if isinstance(item.get("rule_results"), str):
            try:
                item["rule_results"] = json.loads(item["rule_results"])
            except json.JSONDecodeError:
                pass
        values.append(item)
    return values


def trades_after(cur: sqlite3.Cursor, start_ts: str) -> list[dict]:
    cols = table_cols(cur, "trades")
    available = set(cols)
    where = []
    params = []
    for col in ("opened_at", "created_at", "updated_at"):
        if col in available:
            where.append(f"{col} >= ?")
            params.append(start_ts)
    if not where:
        return []
    rows = cur.execute(
        f"SELECT {', '.join(cols)} FROM trades WHERE {' OR '.join(where)} ORDER BY id ASC",
        tuple(params),
    ).fetchall()
    return [dict(zip(cols, row)) for row in rows]


def open_trades(cur: sqlite3.Cursor) -> list[dict]:
    cols = table_cols(cur, "trades")
    rows = cur.execute(
        f"SELECT {', '.join(cols)} FROM trades WHERE state IN ('OPEN', 'PARTIALLY_CLOSED', 'SUBMITTED') ORDER BY id ASC"
    ).fetchall()
    return [dict(zip(cols, row)) for row in rows]


def classify(sig: dict) -> dict:
    rules = sig.get("rule_results") or []
    dict_rules = [rule for rule in rules if isinstance(rule, dict)]
    failed = [rule for rule in dict_rules if not rule.get("passed", False)]
    wr_rules = [rule for rule in dict_rules if "WIN_RATE" in str(rule.get("reason_code", ""))]
    failed_wr = [rule for rule in wr_rules if not rule.get("passed", False)]
    passed_wr = [rule for rule in wr_rules if rule.get("passed", False)]
    hard_rules = [rule for rule in dict_rules if str(rule.get("reason_code", "")).startswith("HARD_TRADE")]

    if failed_wr:
        category = "approved_but_failed_winrate"
    elif sig.get("decision") == "OPENED":
        category = "passed_and_opened"
    elif passed_wr:
        category = "passed_winrate_but_not_opened"
    else:
        category = "rejected_early"

    wr = wr_threshold = wr_passed = None
    if wr_rules:
        details = wr_rules[-1].get("details") or {}
        wr = details.get("win_rate")
        wr_threshold = details.get("threshold") or details.get("minimum_win_rate")
        wr_passed = wr_rules[-1].get("passed")

    return {
        "category": category,
        "win_rate": wr,
        "win_rate_threshold": wr_threshold,
        "win_rate_passed": wr_passed,
        "failed_rules": [rule.get("reason_code") for rule in failed],
        "wr_rules": [rule.get("reason_code") for rule in wr_rules],
        "hard_rules": [
            {"reason_code": rule.get("reason_code"), "passed": rule.get("passed"), "details": rule.get("details")}
            for rule in hard_rules
        ],
    }


def summarize_position(position: dict) -> dict:
    entry = position.get("entry_price")
    current = position.get("current_price")
    stop_loss = position.get("stop_loss")
    take_profit = position.get("take_profit")
    side = str(position.get("side", "")).upper()
    price_move = None
    distance_to_sl = None
    distance_to_tp = None
    try:
        entry_value = float(entry)
        current_value = float(current)
        if side == "BUY":
            price_move = current_value - entry_value
        elif side == "SELL":
            price_move = entry_value - current_value
    except (TypeError, ValueError):
        pass
    try:
        current_value = float(current)
        sl_value = float(stop_loss)
        tp_value = float(take_profit)
        if side == "BUY":
            distance_to_sl = current_value - sl_value
            distance_to_tp = tp_value - current_value
        elif side == "SELL":
            distance_to_sl = sl_value - current_value
            distance_to_tp = current_value - tp_value
    except (TypeError, ValueError):
        pass
    return {
        "ticket": position.get("ticket"),
        "symbol": position.get("symbol"),
        "side": position.get("side"),
        "volume": position.get("volume"),
        "entry_price": entry,
        "current_price": current,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "profit": position.get("profit"),
        "price_move_from_entry": price_move,
        "distance_to_sl": distance_to_sl,
        "distance_to_tp": distance_to_tp,
        "opened_at": position.get("opened_at"),
        "comment": position.get("comment"),
    }


def position_signature(position: dict) -> tuple:
    summary = summarize_position(position)
    return (
        summary.get("ticket"),
        summary.get("current_price"),
        summary.get("stop_loss"),
        summary.get("take_profit"),
        summary.get("profit"),
        summary.get("volume"),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor Hard Trade signal decisions.")
    parser.add_argument("--minutes", type=float, default=30.0)
    parser.add_argument("--name", default="30m")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    duration_seconds = max(1.0, args.minutes * 60)
    safe_name = "".join(ch for ch in args.name if ch.isalnum() or ch in ("-", "_")) or "monitor"
    out = ROOT / "data" / f"hard_trade_monitor_{safe_name}.json"
    log_path = ROOT / "data" / f"hard_trade_monitor_{safe_name}.log"
    log_path.write_text("", encoding="utf-8")
    start = datetime.now(timezone.utc)
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    last_id = cur.execute("SELECT COALESCE(MAX(id),0) FROM signal_decisions").fetchone()[0]
    signals = []
    snapshots = []
    position_events = []
    tracked_positions: dict[str, tuple] = {}
    last_position_log = 0.0
    initial = {"config": get_json("/config"), "status": get_json("/status"), "positions": get_json("/positions")}
    log(log_path, json.dumps({"event": "MONITOR_START", "started_at": start.isoformat(), "last_signal_id": last_id, "minutes": args.minutes}, ensure_ascii=False))

    end_time = time.time() + duration_seconds
    last_snapshot = 0.0
    try:
        while time.time() < end_time:
            conn.commit()
            for sig in signal_rows_after(cur, last_id):
                last_id = max(last_id, int(sig["id"]))
                sig["_classification"] = classify(sig)
                signals.append(sig)
                log(log_path, json.dumps({"event": "SETUP", **sig}, ensure_ascii=False, default=str))

            now = time.time()
            if now - last_snapshot >= 60:
                snapshots.append(
                    {
                        "at": datetime.now(timezone.utc).isoformat(),
                        "status": get_json("/status"),
                        "positions": get_json("/positions"),
                        "latest": get_json("/signals/latest"),
                    }
                )
                last_snapshot = now
            if now - last_position_log >= POSITION_LOG_SECONDS:
                positions = get_json("/positions")
                if not isinstance(positions, list):
                    positions = []
                current_keys = set()
                for position in positions:
                    key = str(position.get("ticket") or position.get("comment") or position)
                    current_keys.add(key)
                    signature = position_signature(position)
                    event_type = "POSITION_OPEN_TRACKED" if key not in tracked_positions else "POSITION_UPDATE"
                    if tracked_positions.get(key) != signature:
                        event = {
                            "event": event_type,
                            "at": datetime.now(timezone.utc).isoformat(),
                            "position": summarize_position(position),
                        }
                        position_events.append(event)
                        log(log_path, json.dumps(event, ensure_ascii=False, default=str))
                        tracked_positions[key] = signature
                for key in sorted(set(tracked_positions) - current_keys):
                    event = {
                        "event": "POSITION_CLOSED_OR_MISSING",
                        "at": datetime.now(timezone.utc).isoformat(),
                        "position_key": key,
                        "open_trades": open_trades(cur),
                    }
                    position_events.append(event)
                    log(log_path, json.dumps(event, ensure_ascii=False, default=str))
                    tracked_positions.pop(key, None)
                last_position_log = now
            time.sleep(POLL_SECONDS)
    finally:
        final = {
            "started_at": start.isoformat(),
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "initial": initial,
            "final": {"config": get_json("/config"), "status": get_json("/status"), "positions": get_json("/positions")},
            "signals": signals,
            "snapshots": snapshots,
            "position_events": position_events,
            "trades": trades_after(cur, start.isoformat()),
        }
        out.write_text(json.dumps(final, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        categories = {}
        for sig in signals:
            category = sig["_classification"]["category"]
            categories[category] = categories.get(category, 0) + 1
        log(log_path, json.dumps({"event": "MONITOR_DONE", "total": len(signals), "categories": categories, "out": str(out)}, ensure_ascii=False))
        conn.close()


if __name__ == "__main__":
    main()
