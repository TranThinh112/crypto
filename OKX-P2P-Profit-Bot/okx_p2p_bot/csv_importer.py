from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

import pandas as pd

from .models import Order
from .normalize import normalize_side, normalize_status, parse_datetime, parse_vietnam_number


def read_order_file(file: BinaryIO | str | Path) -> list[Order]:
    name = getattr(file, "name", str(file))
    suffix = Path(name).suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(file)
    else:
        df = pd.read_csv(file)
    return orders_from_okx_dataframe(df, source=Path(name).name)


def orders_from_okx_dataframe(df: pd.DataFrame, source: str = "CSV") -> list[Order]:
    orders: list[Order] = []
    for _, row in df.fillna("").iterrows():
        order_id = str(row.get("Số lệnh", "")).strip()
        side = normalize_side(str(row.get("Loại lệnh", "")).strip())
        status = normalize_status(str(row.get("Trạng thái", "")).strip())
        price = parse_vietnam_number(row.get("Giá"))
        usdt = parse_vietnam_number(row.get("Khối lượng"), decimal_hint=True)
        vnd = parse_vietnam_number(row.get("Số tiền"))
        time_text = normalize_csv_time(row.get("Ngày tạo lệnh", ""))
        warnings: list[str] = []
        if not time_text:
            warnings.append("Thiếu thời gian")
        if not side:
            warnings.append("Loại lệnh không xác định")
        if not status:
            warnings.append("Trạng thái không xác định")
        if usdt is None:
            warnings.append("Thiếu số lượng")
        if price is None:
            warnings.append("Thiếu đơn giá")
        orders.append(
            Order(
                order_id=order_id,
                side=side,
                status=status,
                time_text=time_text,
                usdt=usdt,
                vnd=vnd,
                unit_price=price,
                source=source,
                raw_text="",
                needs_review=bool(warnings),
                warnings=warnings,
                timestamp=parse_datetime(time_text),
            )
        )
    return orders


def normalize_csv_time(value: object) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M:%S %d/%m/%Y")
    text = str(value).strip()
    if not text:
        return ""
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return text
    return parsed.strftime("%H:%M:%S %d/%m/%Y")
