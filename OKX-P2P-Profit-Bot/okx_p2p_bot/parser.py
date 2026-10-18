from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Iterable

from .models import Order
from .normalize import normalize_side, normalize_status, parse_datetime, parse_vietnam_number


TIME_RE = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?\s+\d{1,2}/\d{1,2}/\d{4}")
ID_RE = re.compile(r"(?:ID|Mã|Ma|Lệnh|Lenh)[:\s#-]*([A-Z0-9-]{6,})", re.I)
BARE_ID_RE = re.compile(r"\b([0-9]{10,}|[A-Z0-9]{10,})\b")
USDT_RE = re.compile(r"([\d.,]+)\s*USDT", re.I)
VND_RE = re.compile(r"([\d.,]+)\s*VND", re.I)
NUMBER_RE = re.compile(r"(?<![\d:])\d[\d.,]*(?![\d:/])")


def split_order_blocks(text: str) -> list[str]:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        starts_new = bool(TIME_RE.search(line)) and current
        if starts_new:
            blocks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(current)
    return [" ".join(block) for block in blocks]


def parse_orders_from_text(text: str, source: str = "OCR") -> list[Order]:
    orders: list[Order] = []
    for block in split_order_blocks(text):
        order = parse_order_block(block, source)
        if order.side or order.timestamp or order.usdt or order.unit_price:
            orders.append(order)
    return dedupe_orders(merge_complementary_orders(orders))


def merge_complementary_orders(orders: list[Order]) -> list[Order]:
    merged = list(orders)
    for fragment in orders:
        if not fragment.timestamp:
            continue
        if order_quality(fragment) > 4:
            continue
        target = find_merge_target(fragment, merged)
        if target is None or target is fragment:
            continue
        copy_missing_fields(target, fragment)
        refresh_order(target)
        fragment.merged_into = True
    return merged


def find_merge_target(fragment: Order, orders: list[Order]) -> Order | None:
    best_score: tuple[float, int] | None = None
    best_order: Order | None = None
    for candidate in orders:
        if candidate is fragment or not candidate.timestamp or candidate.source != fragment.source:
            continue
        seconds = abs((candidate.timestamp - fragment.timestamp).total_seconds())
        if seconds > 90:
            continue
        if not can_merge(candidate, fragment):
            continue
        score = (seconds, -order_quality(candidate))
        if best_score is None or score < best_score:
            best_score = score
            best_order = candidate
    return best_order


def can_merge(candidate: Order, fragment: Order) -> bool:
    complementary = (
        (not candidate.status and bool(fragment.status))
        or (not candidate.side and bool(fragment.side))
        or (candidate.usdt is None and fragment.usdt is not None)
        or (candidate.vnd is None and fragment.vnd is not None)
        or (candidate.unit_price is None and fragment.unit_price is not None)
        or (not candidate.order_id and bool(fragment.order_id))
    )
    if not complementary:
        return False
    for field in ("side", "status", "order_id"):
        left = getattr(candidate, field)
        right = getattr(fragment, field)
        if left and right and left != right:
            return False
    return True


def copy_missing_fields(target: Order, fragment: Order) -> None:
    for field in ("order_id", "side", "status", "time_text", "usdt", "vnd", "unit_price"):
        if getattr(target, field) in (None, "") and getattr(fragment, field) not in (None, ""):
            setattr(target, field, getattr(fragment, field))
    if fragment.raw_text and fragment.raw_text not in target.raw_text:
        target.raw_text = f"{target.raw_text} {fragment.raw_text}".strip()


def refresh_order(order: Order) -> None:
    if order.usdt and order.vnd:
        inferred_price = round(order.vnd / order.usdt)
        if 20_000 <= inferred_price <= 30_000 and (order.unit_price is None or order.unit_price < 10_000):
            order.unit_price = float(inferred_price)
    warnings: list[str] = []
    if not order.time_text:
        warnings.append("Thiếu thời gian")
    if not order.side:
        warnings.append("Loại lệnh không xác định")
    if not order.status:
        warnings.append("Trạng thái không xác định")
    if order.usdt is None:
        warnings.append("Thiếu số lượng")
    if order.unit_price is None:
        warnings.append("Thiếu đơn giá")
    order.warnings = warnings
    order.needs_review = bool(warnings)


def dedupe_orders(orders: list[Order]) -> list[Order]:
    orders = remove_partial_duplicate_ids([order for order in orders if not order.merged_into])
    best_by_key: dict[str, Order] = {}
    no_key: list[Order] = []
    for order in orders:
        key = order.order_id or order.time_text
        if not key:
            no_key.append(order)
            continue
        existing = best_by_key.get(key)
        if existing is None or order_quality(order) > order_quality(existing):
            best_by_key[key] = order
    return list(best_by_key.values()) + no_key


def remove_partial_duplicate_ids(orders: list[Order]) -> list[Order]:
    keep: list[Order] = []
    for order in orders:
        partial_duplicate = False
        for other in orders:
            if order is other:
                continue
            if order.source != other.source:
                continue
            if is_partial_id_duplicate(order, other) or is_near_duplicate_without_id(order, other):
                partial_duplicate = True
                break
        if not partial_duplicate:
            keep.append(order)
    return keep


def is_partial_id_duplicate(order: Order, other: Order) -> bool:
    if not order.order_id or not other.order_id or order.order_id == other.order_id:
        return False
    if order.order_id not in other.order_id or len(order.order_id) >= len(other.order_id):
        return False
    if not values_close(order.usdt, other.usdt, tolerance=0.01):
        return False
    if order.timestamp and other.timestamp:
        return abs((order.timestamp - other.timestamp).total_seconds()) <= 10 * 60
    return False


def is_near_duplicate_without_id(order: Order, other: Order) -> bool:
    if order.order_id or not other.order_id:
        return False
    if order.side and other.side and order.side != other.side:
        return False
    if order.status and other.status and order.status != other.status:
        return False
    same_usdt = values_close(order.usdt, other.usdt, tolerance=0.01)
    same_vnd = values_close(order.vnd, other.vnd, tolerance=1)
    same_price = values_close(order.unit_price, other.unit_price, tolerance=10)
    if same_usdt and same_vnd and same_price:
        return True
    if not order.timestamp or not other.timestamp:
        return False
    seconds = abs((order.timestamp - other.timestamp).total_seconds())
    return seconds <= 60 and same_usdt and (same_vnd or same_price)


def values_close(left: float | None, right: float | None, tolerance: float) -> bool:
    if left is None or right is None:
        return False
    return abs(left - right) <= tolerance


def order_quality(order: Order) -> int:
    fields = [order.order_id, order.side, order.status, order.time_text, order.usdt, order.vnd, order.unit_price]
    return sum(1 for field in fields if field not in (None, ""))


def parse_order_block(block: str, source: str = "OCR") -> Order:
    side = normalize_side(block)
    status = normalize_status(block)
    time_match = TIME_RE.search(block)
    time_text = time_match.group(0) if time_match else ""
    order_id_match = ID_RE.search(block)
    bare_order_id_match = BARE_ID_RE.search(block)
    usdt_values = [parse_vietnam_number(match.group(1), decimal_hint=True) for match in USDT_RE.finditer(block)]
    vnd_values = [parse_vietnam_number(match.group(1)) for match in VND_RE.finditer(block)]

    unit_price = None
    vnd = None
    usdt = usdt_values[0] if usdt_values else None
    if vnd_values:
        if usdt and len(vnd_values) >= 2:
            unit_price = vnd_values[-1]
            vnd = max(vnd_values[:-1])
        elif usdt and len(vnd_values) == 1:
            candidate = vnd_values[0]
            if candidate < 100_000:
                unit_price = candidate
            else:
                vnd = candidate
        else:
            vnd = max(vnd_values)
    if unit_price is None and usdt and vnd:
        unit_price = round(vnd / usdt, 6)

    if usdt is None or vnd is None or unit_price is None:
        table_values = infer_table_numbers(block)
        usdt = usdt if usdt is not None else table_values.get("usdt")
        vnd = vnd if vnd is not None else table_values.get("vnd")
        unit_price = unit_price if unit_price is not None else table_values.get("unit_price")

    if usdt and vnd:
        inferred_price = round(vnd / usdt)
        if 20_000 <= inferred_price <= 30_000 and (unit_price is None or unit_price < 10_000):
            unit_price = float(inferred_price)

    warnings: list[str] = []
    if not time_text:
        warnings.append("Thiếu thời gian")
    if not side:
        warnings.append("Loại lệnh không xác định")
    if not status:
        warnings.append("Trạng thái không xác định")
    if usdt is None:
        warnings.append("Thiếu số lượng")
    if unit_price is None:
        warnings.append("Thiếu đơn giá")

    order_id = order_id_match.group(1) if order_id_match else (bare_order_id_match.group(1) if bare_order_id_match else "")
    timestamp = choose_best_timestamp(time_text, order_id)
    if timestamp is not None and timestamp != parse_datetime(time_text):
        time_text = timestamp.strftime("%H:%M:%S %d/%m/%Y")

    return Order(
        order_id=order_id,
        side=side,
        status=status,
        time_text=time_text,
        usdt=usdt,
        vnd=vnd,
        unit_price=unit_price,
        source=source,
        raw_text=block,
        needs_review=bool(warnings),
        warnings=warnings,
        timestamp=timestamp,
    )


def choose_best_timestamp(time_text: str, order_id: str) -> datetime | None:
    parsed_time = parse_datetime(time_text)
    id_time = infer_timestamp_from_order_id(order_id)
    if parsed_time is None:
        return id_time
    if id_time is None:
        return parsed_time
    if parsed_time.date() == id_time.date() and abs(parsed_time.hour - id_time.hour) == 10:
        return id_time
    if parsed_time.date() == id_time.date() and parsed_time.minute == id_time.minute and parsed_time.hour != id_time.hour:
        return id_time
    # OKX order IDs observed in these screenshots are one hour ahead of the displayed local time.
    if abs((parsed_time - id_time).total_seconds()) > 2 * 3600:
        return id_time
    if parsed_time.hour < 6 and id_time.hour >= 6:
        return id_time
    return parsed_time


def infer_timestamp_from_order_id(order_id: str) -> datetime | None:
    digits = re.sub(r"\D", "", order_id or "")
    if len(digits) < 12:
        return None
    try:
        raw = datetime.strptime(digits[:12], "%y%m%d%H%M%S")
    except ValueError:
        return None
    return raw - timedelta(hours=1)


def infer_table_numbers(block: str) -> dict[str, float]:
    without_time = TIME_RE.sub(" ", block)
    without_id = BARE_ID_RE.sub(" ", without_time, count=1)
    numbers = [match.group(0) for match in NUMBER_RE.finditer(without_id)]
    parsed = [parse_vietnam_number(value, decimal_hint=True) for value in numbers]
    parsed = [value for value in parsed if value is not None]
    result: dict[str, float] = {}
    usdt_candidates = [value for value in parsed if 0 < value < 100_000 and not float(value).is_integer()]
    price_candidates = [value for value in parsed if 10_000 <= value <= 100_000]
    vnd_candidates = [value for value in parsed if value >= 100_000]
    if usdt_candidates:
        result["usdt"] = usdt_candidates[0]
    elif parsed and 0 < parsed[0] < 100_000:
        result["usdt"] = parsed[0]
    if vnd_candidates:
        result["vnd"] = max(vnd_candidates)
    if price_candidates:
        result["unit_price"] = price_candidates[-1]
    return result


def orders_from_rows(rows: Iterable[dict]) -> list[Order]:
    orders: list[Order] = []
    for row in rows:
        time_text = str(row.get("time_text") or row.get("Thời gian") or "")
        warnings = []
        order_id = str(row.get("order_id") or row.get("ID lệnh") or "")
        timestamp = choose_best_timestamp(time_text, order_id)
        if timestamp is not None and timestamp != parse_datetime(time_text):
            time_text = timestamp.strftime("%H:%M:%S %d/%m/%Y")
        side = normalize_side(str(row.get("side") or row.get("Loại") or ""))
        status = normalize_status(str(row.get("status") or row.get("Trạng thái") or ""))
        usdt = parse_vietnam_number(row.get("usdt") or row.get("USDT"), decimal_hint=True)
        vnd = parse_vietnam_number(row.get("vnd") or row.get("VND"))
        unit_price = parse_vietnam_number(row.get("unit_price") or row.get("Đơn giá"))
        if not timestamp:
            warnings.append("Thiếu thời gian")
        if not side:
            warnings.append("Loại lệnh không xác định")
        if not status:
            warnings.append("Trạng thái không xác định")
        if usdt is None:
            warnings.append("Thiếu số lượng")
        if unit_price is None:
            warnings.append("Thiếu đơn giá")
        orders.append(Order(
            order_id=order_id,
            side=side,
            status=status,
            time_text=time_text,
            usdt=usdt,
            vnd=vnd,
            unit_price=unit_price,
            source=str(row.get("source") or row.get("Nguồn") or "Manual"),
            raw_text=str(row.get("raw_text") or row.get("OCR thô") or ""),
            needs_review=bool(row.get("needs_review") or row.get("Cần kiểm tra") or warnings),
            warnings=warnings,
            timestamp=timestamp,
        ))
    return orders
