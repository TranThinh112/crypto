from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from .models import Order
from .normalize import parse_datetime


DB_PATH = Path(__file__).resolve().parents[1] / "okx_p2p_orders.db"


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                side TEXT NOT NULL,
                status TEXT NOT NULL,
                time_text TEXT NOT NULL,
                timestamp TEXT,
                usdt REAL,
                vnd REAL,
                unit_price REAL,
                source TEXT,
                raw_text TEXT,
                needs_review INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_summaries (
                day TEXT PRIMARY KEY,
                buy_count INTEGER,
                sell_count INTEGER,
                total_usdt REAL,
                total_vnd REAL,
                avg_buy_price REAL,
                avg_sell_price REAL,
                total_profit REAL,
                avg_spread REAL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory_snapshots (
                cutoff_date TEXT PRIMARY KEY,
                inventory_usdt REAL,
                inventory_cost REAL,
                current_buy_price REAL,
                last_cycle_buy_price REAL,
                updated_at TEXT NOT NULL
            )
            """
        )


def save_orders(orders: list[Order]) -> int:
    init_db()
    saved = 0
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        for index, order in enumerate(orders):
            key = order.order_id.strip() if order.order_id else f"manual:{order.time_text}:{order.side}:{order.usdt}:{order.vnd}:{index}"
            conn.execute(
                """
                INSERT INTO orders (
                    order_id, side, status, time_text, timestamp, usdt, vnd, unit_price,
                    source, raw_text, needs_review, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET
                    side = excluded.side,
                    status = excluded.status,
                    time_text = excluded.time_text,
                    timestamp = excluded.timestamp,
                    usdt = excluded.usdt,
                    vnd = excluded.vnd,
                    unit_price = excluded.unit_price,
                    source = excluded.source,
                    raw_text = excluded.raw_text,
                    needs_review = excluded.needs_review,
                    updated_at = excluded.updated_at
                """,
                (
                    key,
                    order.side,
                    order.status,
                    order.time_text,
                    order.timestamp.isoformat() if order.timestamp else None,
                    order.usdt,
                    order.vnd,
                    order.unit_price,
                    order.source,
                    order.raw_text,
                    int(order.needs_review),
                    now,
                ),
            )
            saved += 1
    return saved


def load_orders() -> list[Order]:
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT * FROM orders ORDER BY timestamp DESC, time_text DESC").fetchall()
    orders: list[Order] = []
    for row in rows:
        timestamp = parse_datetime(row["time_text"])
        orders.append(
            Order(
                order_id=row["order_id"],
                side=row["side"],
                status=row["status"],
                time_text=row["time_text"],
                usdt=row["usdt"],
                vnd=row["vnd"],
                unit_price=row["unit_price"],
                source=row["source"] or "Database",
                raw_text=row["raw_text"] or "",
                needs_review=bool(row["needs_review"]),
                warnings=[],
                timestamp=timestamp,
            )
        )
    return orders


def count_orders() -> int:
    init_db()
    with connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0])

def save_daily_summaries(df: pd.DataFrame) -> int:
    init_db()
    if df.empty:
        return 0
    saved = 0
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        for _, row in df.iterrows():
            day = str(row.get("Ngày", "")).strip()
            if not day or day == "Tổng cộng":
                continue
            conn.execute(
                """
                INSERT INTO daily_summaries (
                    day, buy_count, sell_count, total_usdt, total_vnd,
                    avg_buy_price, avg_sell_price, total_profit, avg_spread, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(day) DO UPDATE SET
                    buy_count = excluded.buy_count,
                    sell_count = excluded.sell_count,
                    total_usdt = excluded.total_usdt,
                    total_vnd = excluded.total_vnd,
                    avg_buy_price = excluded.avg_buy_price,
                    avg_sell_price = excluded.avg_sell_price,
                    total_profit = excluded.total_profit,
                    avg_spread = excluded.avg_spread,
                    updated_at = excluded.updated_at
                """,
                (
                    day,
                    _int_or_none(row.get("Số lệnh mua")),
                    _int_or_none(row.get("Số lệnh bán")),
                    _float_or_none(row.get("Tổng USDT")),
                    _float_or_none(row.get("Số tiền VND")),
                    _float_or_none(row.get("Giá mua TB")),
                    _float_or_none(row.get("Giá bán TB")),
                    _float_or_none(row.get("Tổng lãi")),
                    _float_or_none(row.get("Spread trung bình")),
                    now,
                ),
            )
            saved += 1
    return saved

def load_daily_summaries() -> pd.DataFrame:
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT * FROM daily_summaries").fetchall()
    data = [
        {
            "Ngày": row["day"],
            "Số lệnh mua": row["buy_count"],
            "Số lệnh bán": row["sell_count"],
            "Tổng USDT": row["total_usdt"],
            "Số tiền VND": row["total_vnd"],
            "Giá mua TB": row["avg_buy_price"],
            "Giá bán TB": row["avg_sell_price"],
            "Tổng lãi": row["total_profit"],
            "Spread trung bình": row["avg_spread"],
        }
        for row in rows
    ]
    return pd.DataFrame(data)

def save_inventory_snapshot(cutoff_date: str, state: dict) -> None:
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO inventory_snapshots (
                cutoff_date, inventory_usdt, inventory_cost,
                current_buy_price, last_cycle_buy_price, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cutoff_date) DO UPDATE SET
                inventory_usdt = excluded.inventory_usdt,
                inventory_cost = excluded.inventory_cost,
                current_buy_price = excluded.current_buy_price,
                last_cycle_buy_price = excluded.last_cycle_buy_price,
                updated_at = excluded.updated_at
            """,
            (
                cutoff_date,
                _float_or_none(state.get("inventory_usdt")),
                _float_or_none(state.get("inventory_cost")),
                _float_or_none(state.get("current_buy_price")),
                _float_or_none(state.get("last_cycle_buy_price")),
                now,
            ),
        )

def load_latest_inventory_snapshot() -> dict | None:
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM inventory_snapshots ORDER BY cutoff_date DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return {
        "inventory_usdt": row["inventory_usdt"],
        "inventory_cost": row["inventory_cost"],
        "current_buy_price": row["current_buy_price"],
        "last_cycle_buy_price": row["last_cycle_buy_price"],
    }

def purge_cutoff_date(max_days: int = 10) -> str | None:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT MAX(timestamp) FROM orders WHERE timestamp IS NOT NULL").fetchone()
    latest_text = row[0] if row else None
    if not latest_text:
        return None
    latest = datetime.fromisoformat(latest_text)
    return (latest - timedelta(days=max_days - 1)).date().isoformat()

def purge_old_orders(max_days: int = 10) -> int:
    init_db()
    with connect() as conn:
        cutoff = purge_cutoff_date(max_days)
        if not cutoff:
            return 0
        deleted = conn.execute(
            "DELETE FROM orders WHERE timestamp IS NOT NULL AND date(timestamp) < ?",
            (cutoff,),
        ).rowcount
    return int(deleted or 0)

def _float_or_none(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)

def _int_or_none(value) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)
