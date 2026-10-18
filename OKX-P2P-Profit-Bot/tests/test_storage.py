from pathlib import Path

from okx_p2p_bot.models import Order
from okx_p2p_bot.storage import connect


def test_sqlite_upsert_schema(tmp_path: Path):
    db_path = tmp_path / "orders.db"
    with connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE orders (
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
        order = Order(
            order_id="260828173713339",
            side="Bán",
            status="Đã thực hiện",
            time_text="16:37:14 28/08/2026",
            usdt=6.0,
            vnd=155100,
            unit_price=25850,
        )
        for price in (25850, 25860):
            conn.execute(
                """
                INSERT INTO orders (order_id, side, status, time_text, usdt, vnd, unit_price, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET unit_price = excluded.unit_price
                """,
                (order.order_id, order.side, order.status, order.time_text, order.usdt, order.vnd, price, "now"),
            )
        rows = conn.execute("SELECT * FROM orders").fetchall()

    assert len(rows) == 1
    assert rows[0]["unit_price"] == 25860
