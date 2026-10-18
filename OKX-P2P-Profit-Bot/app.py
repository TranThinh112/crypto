from __future__ import annotations

import math
from io import BytesIO

import pandas as pd
import streamlit as st

from okx_p2p_bot.calculator import BUY_GROUP_THRESHOLD_USD, calculate_sales
from okx_p2p_bot.csv_importer import read_order_file
from okx_p2p_bot.normalize import parse_vietnam_number
from okx_p2p_bot.ocr import image_to_text
from okx_p2p_bot.parser import dedupe_orders, orders_from_rows, parse_orders_from_text
from okx_p2p_bot.storage import (
    count_orders,
    load_daily_summaries,
    load_latest_inventory_snapshot,
    load_orders,
    purge_cutoff_date,
    purge_old_orders,
    save_daily_summaries,
    save_inventory_snapshot,
    save_orders,
)


ORDER_COLUMNS = {
    "time_text": "Thời gian",
    "order_id": "ID lệnh",
    "side": "Loại lệnh",
    "status": "Trạng thái",
    "usdt": "Khối lượng USDT",
    "vnd": "Số tiền VND",
    "unit_price": "Đơn giá",
    "avg_buy_price": "Giá mua TB",
}
SALE_COLUMNS = {
    "time_text": "Thời gian",
    "order_id": "ID lệnh",
    "usdt": "USDT bán",
    "vnd": "Số tiền VND",
    "sell_price": "Giá bán",
    "applied_buy_price": "Giá mua áp dụng",
    "spread": "Lãi/USDT",
    "profit": "Lãi lệnh",
    "check_status": "Kiểm tra dữ liệu",
    "buy_price_source": "Nguồn giá mua",
}


def sort_orders_newest_first(df: pd.DataFrame) -> pd.DataFrame:
    if "time_text" not in df.columns or df.empty:
        return df
    sorted_df = df.copy()
    sorted_df["_sort_time"] = pd.to_datetime(sorted_df["time_text"], format="%H:%M:%S %d/%m/%Y", errors="coerce")
    sorted_df = sorted_df.sort_values("_sort_time", ascending=False, na_position="last")
    return sorted_df.drop(columns=["_sort_time"])


def to_vietnamese_columns(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    visible_cols = [col for col in mapping if col in df.columns]
    return df[visible_cols].rename(columns=mapping)


def one_based_index(df: pd.DataFrame) -> pd.DataFrame:
    display = df.copy()
    display.index = range(1, len(display) + 1)
    return display


def descending_index(df: pd.DataFrame) -> pd.DataFrame:
    display = df.copy()
    display.index = range(len(display), 0, -1)
    return display


def format_int_vn(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    number = parse_vietnam_number(value)
    if number is None or not math.isfinite(number):
        return ""
    return f"{int(round(number)):,}".replace(",", ".")


def format_signed_int_vn(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    number = parse_vietnam_number(value)
    if number is None or not math.isfinite(number):
        return ""
    sign = "+" if number > 0 else ""
    return f"{sign}{int(round(number)):,}".replace(",", ".")


def format_float_vn(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    number = parse_vietnam_number(value, decimal_hint=True)
    if number is None or not math.isfinite(number):
        return ""
    text = f"{number:,.2f}".rstrip("0").rstrip(".")
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def format_order_display(df: pd.DataFrame) -> pd.DataFrame:
    display = to_vietnamese_columns(df, ORDER_COLUMNS).copy()
    for col in ("Số tiền VND", "Đơn giá", "Giá mua TB"):
        if col in display.columns:
            display[col] = display[col].apply(format_int_vn)
    if "Khối lượng USDT" in display.columns:
        display["Khối lượng USDT"] = display["Khối lượng USDT"].apply(format_float_vn)
    return display


def format_sale_display(df: pd.DataFrame) -> pd.DataFrame:
    display = to_vietnamese_columns(df, SALE_COLUMNS).copy()
    for col in ("Số tiền VND", "Giá bán", "Giá mua áp dụng", "Lãi/USDT"):
        if col in display.columns:
            display[col] = display[col].apply(format_int_vn)
    if "Lãi lệnh" in display.columns:
        display["Lãi lệnh"] = display["Lãi lệnh"].apply(format_signed_int_vn)
    if "USDT bán" in display.columns:
        display["USDT bán"] = display["USDT bán"].apply(format_float_vn)
    return display


def color_profit(row: pd.Series) -> list[str]:
    styles = []
    for col in row.index:
        if col in {"Lãi lệnh", "Tổng lãi"}:
            value = str(row[col]).strip()
            if value.startswith("+"):
                styles.append("color: #22c55e; font-weight: 700")
            elif value.startswith("-"):
                styles.append("color: #ef4444; font-weight: 700")
            else:
                styles.append("")
        else:
            styles.append("")
    return styles

def color_sale_buy_price_source(row: pd.Series, average_buy_order_ids: set[str]) -> list[str]:
    base = color_profit(row)
    if str(row.get("ID lệnh", "")).strip() in average_buy_order_ids:
        return [
            "background-color: #5a1717; color: #ffe1e1; font-weight: 700" if col == "Giá mua áp dụng" else style
            for col, style in zip(row.index, base)
        ]
    return base


def sales_by_day(sale_df: pd.DataFrame) -> pd.DataFrame:
    if sale_df.empty:
        return pd.DataFrame(columns=["Ngày", "Số lệnh mua", "Số lệnh bán", "Tổng USDT", "Số tiền VND", "Giá mua TB", "Giá bán TB", "Tổng lãi", "Spread trung bình", "Trạng thái"])
    valid = sale_df[sale_df["profit"].notna()].copy()
    if valid.empty:
        return pd.DataFrame(columns=["Ngày", "Số lệnh mua", "Số lệnh bán", "Tổng USDT", "Số tiền VND", "Giá mua TB", "Giá bán TB", "Tổng lãi", "Spread trung bình", "Trạng thái"])
    valid["Ngày"] = pd.to_datetime(valid["time_text"], format="%H:%M:%S %d/%m/%Y", errors="coerce").dt.strftime("%d/%m/%Y")
    grouped = valid.groupby("Ngày", as_index=False).agg(
        **{
            "Số lệnh bán": ("order_id", "count"),
            "Tổng USDT": ("usdt", "sum"),
            "Số tiền VND": ("vnd", "sum"),
            "Tổng lãi": ("profit", "sum"),
        }
    )
    grouped["Spread trung bình"] = grouped["Tổng lãi"] / grouped["Tổng USDT"]
    grouped["_sort_date"] = pd.to_datetime(grouped["Ngày"], format="%d/%m/%Y", errors="coerce")
    return grouped.sort_values("_sort_date", ascending=False).drop(columns=["_sort_date"])


def orders_by_day(orders) -> pd.DataFrame:
    rows = []
    for order in orders:
        if order.status != "Đã thực hiện" or not order.timestamp:
            continue
        rows.append(
            {
                "Ngày": order.timestamp.strftime("%d/%m/%Y"),
                "Loại lệnh": order.side,
                "USDT": order.usdt,
                "Số tiền VND": order.vnd,
            }
        )
    if not rows:
        return pd.DataFrame(columns=["Ngày", "Số lệnh mua", "Giá mua TB", "Giá bán TB"])
    df = pd.DataFrame(rows)
    grouped_rows = []
    for day, day_df in df.groupby("Ngày"):
        buy_df = day_df[day_df["Loại lệnh"] == "Mua"]
        sell_df = day_df[day_df["Loại lệnh"] == "Bán"]
        buy_usdt = buy_df["USDT"].sum()
        sell_usdt = sell_df["USDT"].sum()
        grouped_rows.append(
            {
                "Ngày": day,
                "Số lệnh mua": int(len(buy_df)),
                "Giá mua TB": buy_df["Số tiền VND"].sum() / buy_usdt if buy_usdt else None,
                "Giá bán TB": sell_df["Số tiền VND"].sum() / sell_usdt if sell_usdt else None,
            }
        )
    return pd.DataFrame(grouped_rows)


def daily_summary(orders, sale_df: pd.DataFrame) -> pd.DataFrame:
    sales = sales_by_day(sale_df)
    order_stats = orders_by_day(orders)
    columns = ["Ngày", "Số lệnh mua", "Số lệnh bán", "Tổng USDT", "Số tiền VND", "Giá mua TB", "Giá bán TB", "Tổng lãi", "Spread trung bình", "Trạng thái"]
    if sales.empty and order_stats.empty:
        return pd.DataFrame(columns=columns)
    if sales.empty:
        merged = order_stats.copy()
    elif order_stats.empty:
        merged = sales.copy()
    else:
        merged = order_stats.merge(sales, on="Ngày", how="outer")
    for col in columns:
        if col not in merged.columns:
            merged[col] = None
    for col in ("Số lệnh mua", "Số lệnh bán", "Tổng USDT", "Số tiền VND", "Tổng lãi"):
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)
    if "Số lệnh bán" in merged.columns:
        merged["Số lệnh bán"] = merged["Số lệnh bán"].astype(int)
    merged["Trạng thái"] = merged["Số lệnh bán"].apply(lambda value: "Chưa có lệnh bán" if int(value or 0) == 0 else "")
    return merged[columns]


def merge_archived_daily_summary(live_df: pd.DataFrame, archived_df: pd.DataFrame) -> pd.DataFrame:
    columns = ["Ngày", "Số lệnh mua", "Số lệnh bán", "Tổng USDT", "Số tiền VND", "Giá mua TB", "Giá bán TB", "Tổng lãi", "Spread trung bình", "Trạng thái"]
    frames = []
    if not archived_df.empty:
        frames.append(archived_df)
    if not live_df.empty:
        frames.append(live_df)
    if not frames:
        return pd.DataFrame(columns=columns)
    merged = pd.concat(frames, ignore_index=True)
    merged = merged.drop_duplicates(subset=["Ngày"], keep="last")
    for col in columns:
        if col not in merged.columns:
            merged[col] = None
    merged["_sort_date"] = pd.to_datetime(merged["Ngày"], format="%d/%m/%Y", errors="coerce")
    return merged.sort_values("_sort_date", ascending=False).drop(columns=["_sort_date"])[columns]

def orders_for_day(orders, day: str):
    return [order for order in orders if order.timestamp and order.timestamp.strftime("%d/%m/%Y") == day]


def format_daily_display(df: pd.DataFrame) -> pd.DataFrame:
    display = df.copy()
    for col in ("Số tiền VND", "Spread trung bình", "Giá mua TB", "Giá bán TB"):
        if col in display.columns:
            display[col] = display[col].apply(format_int_vn)
    if "Tổng lãi" in display.columns:
        display["Tổng lãi"] = display["Tổng lãi"].apply(format_signed_int_vn)
    if "Tổng USDT" in display.columns:
        display["Tổng USDT"] = display["Tổng USDT"].apply(format_float_vn)
    return display


def add_daily_total_row(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    total_usdt = df["Tổng USDT"].sum() if "Tổng USDT" in df.columns else 0
    total_profit = df["Tổng lãi"].sum() if "Tổng lãi" in df.columns else 0
    total_row = {
        "Ngày": "Tổng cộng",
        "Số lệnh mua": df["Số lệnh mua"].sum() if "Số lệnh mua" in df.columns else 0,
        "Số lệnh bán": df["Số lệnh bán"].sum() if "Số lệnh bán" in df.columns else 0,
        "Tổng USDT": total_usdt,
        "Số tiền VND": df["Số tiền VND"].sum() if "Số tiền VND" in df.columns else 0,
        "Giá mua TB": None,
        "Giá bán TB": None,
        "Tổng lãi": total_profit,
        "Spread trung bình": total_profit / total_usdt if total_usdt else None,
    }
    return pd.concat([df, pd.DataFrame([total_row])], ignore_index=True)


def color_daily_profit(row: pd.Series) -> list[str]:
    styles = color_profit(row)
    if row.get("Ngày") == "Tổng cộng":
        styles = [f"{style}; font-weight: 800" if style else "font-weight: 800" for style in styles]
    return styles


def add_grouped_total_row(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    total_row = {
        "Giá bán": "Tổng cộng",
        "Giá mua áp dụng": "",
        "Chênh lệch": "",
        "Số lệnh bán": df["Số lệnh bán"].sum() if "Số lệnh bán" in df.columns else 0,
        "Tổng USDT": df["Tổng USDT"].sum() if "Tổng USDT" in df.columns else 0,
        "Tổng lãi": df["Tổng lãi"].sum() if "Tổng lãi" in df.columns else 0,
    }
    return pd.concat([df, pd.DataFrame([total_row])], ignore_index=True)


def color_grouped_total(row: pd.Series) -> list[str]:
    styles = []
    if row.get("Giá bán") == "Tổng cộng":
        for col in row.index:
            style = "font-weight: 800; background-color: #1f2937"
            if col == "Tổng lãi":
                style += "; color: #22c55e"
            styles.append(style)
        return styles
    for col in row.index:
        if col == "Tổng lãi":
            value = str(row[col]).strip()
            if value.startswith("+"):
                styles.append("color: #22c55e; font-weight: 700")
            elif value.startswith("-"):
                styles.append("color: #ef4444; font-weight: 700")
            else:
                styles.append("")
        else:
            styles.append("")
    return styles


def best_worst_grouped_profit(df: pd.DataFrame) -> pd.DataFrame:
    output_cols = ["Loại thống kê", "Giá bán", "Giá mua áp dụng", "Chênh lệch", "Số lệnh bán", "Tổng USDT", "Tổng lãi"]
    if df.empty or "Tổng lãi" not in df.columns:
        return pd.DataFrame(columns=output_cols)
    valid = df.dropna(subset=["Tổng lãi"]).copy()
    if "Chênh lệch" not in valid.columns and {"Giá bán", "Giá mua áp dụng"}.issubset(valid.columns):
        valid["Chênh lệch"] = valid["Giá bán"] - valid["Giá mua áp dụng"]
    required_cols = output_cols[1:]
    if any(col not in valid.columns for col in required_cols):
        return pd.DataFrame(columns=output_cols)
    if valid.empty:
        return pd.DataFrame(columns=output_cols)
    best = valid.loc[valid["Tổng lãi"].idxmax()].copy()
    worst = valid.loc[valid["Tổng lãi"].idxmin()].copy()
    best["Loại thống kê"] = "Cặp lãi cao nhất"
    worst["Loại thống kê"] = "Cặp lãi thấp nhất"
    return pd.DataFrame([best, worst]).reindex(columns=output_cols)

def format_grouped_profit_extremes(df: pd.DataFrame) -> pd.DataFrame:
    display = df.copy()
    for col in ("Giá bán", "Giá mua áp dụng", "Chênh lệch"):
        if col in display.columns:
            display[col] = display[col].apply(format_int_vn)
    if "Tổng USDT" in display.columns:
        display["Tổng USDT"] = display["Tổng USDT"].apply(format_float_vn)
    if "Tổng lãi" in display.columns:
        display["Tổng lãi"] = display["Tổng lãi"].apply(format_signed_int_vn)
    return display

def selected_day_sales(sales, day: str):
    if not day:
        return sales
    selected = []
    for sale in sales:
        parsed = pd.to_datetime(sale.time_text, format="%H:%M:%S %d/%m/%Y", errors="coerce")
        if not pd.isna(parsed) and parsed.strftime("%d/%m/%Y") == day:
            selected.append(sale)
    return selected


def summarize_sale_rows(sales) -> tuple[dict, list[dict]]:
    valid_sales = [sale for sale in sales if sale.profit is not None]
    total_usdt = sum(sale.usdt or 0 for sale in valid_sales)
    total_profit = sum(sale.profit or 0 for sale in valid_sales)
    summary = {
        "Tổng số lệnh bán hợp lệ": len(valid_sales),
        "Tổng USDT đã bán": total_usdt,
        "Tổng doanh thu VND": sum(sale.vnd or 0 for sale in valid_sales),
        "Tổng lãi VND": total_profit,
        "Spread trung bình": total_profit / total_usdt if total_usdt else None,
        "Giá mua hiện tại": None,
        "Số dòng thiếu dữ liệu/cần kiểm tra": sum(1 for sale in sales if sale.check_status != "OK"),
    }
    grouped_map: dict[tuple[float, float], dict] = {}
    for sale in valid_sales:
        if sale.sell_price is None or sale.applied_buy_price is None or sale.usdt is None:
            continue
        key = (sale.sell_price, sale.applied_buy_price)
        grouped_map.setdefault(key, {"Chênh lệch": sale.sell_price - sale.applied_buy_price, "Số lệnh bán": 0, "Tổng USDT": 0.0, "Tổng lãi": 0.0})
        grouped_map[key]["Số lệnh bán"] += 1
        grouped_map[key]["Tổng USDT"] += sale.usdt
        grouped_map[key]["Tổng lãi"] += sale.profit or 0
    grouped = [{"Giá bán": key[0], "Giá mua áp dụng": key[1], **value} for key, value in grouped_map.items()]
    return summary, grouped


def latest_buy_price(orders) -> float | None:
    completed_buys = [
        order
        for order in orders
        if order.side == "Mua" and order.status == "Đã thực hiện" and order.unit_price is not None and order.timestamp is not None
    ]
    if not completed_buys:
        return None
    return max(completed_buys, key=lambda order: order.timestamp).unit_price


def average_buy_price_for_orders(orders) -> float | None:
    completed_buys = [
        order
        for order in orders
        if order.side == "Mua" and order.status == "Đã thực hiện" and order.usdt and order.vnd is not None
    ]
    total_usdt = sum(order.usdt or 0 for order in completed_buys)
    total_vnd = sum(order.vnd or 0 for order in completed_buys)
    return total_vnd / total_usdt if total_usdt else None


def average_buy_prices_by_order(orders) -> dict[str, float]:
    inventory_usdt = 0.0
    inventory_cost = 0.0
    buy_streak_usdt = 0.0
    buy_streak_cost = 0.0
    buy_streak_inventory_usdt = 0.0
    buy_streak_inventory_cost = 0.0
    cycle_ready = False
    buy_cluster_active = False
    last_side = None
    prices: dict[str, float] = {}
    valid_orders = [order for order in orders if order.status == "Đã thực hiện" and order.timestamp]
    valid_orders.sort(key=lambda order: order.timestamp)
    for order in valid_orders:
        if order.side == "Mua" and order.unit_price is not None and order.usdt:
            if inventory_usdt <= 1e-9:
                inventory_usdt = 0.0
                inventory_cost = 0.0
                buy_streak_usdt = 0.0
                buy_streak_cost = 0.0
                buy_streak_inventory_usdt = 0.0
                buy_streak_inventory_cost = 0.0
                buy_cluster_active = True
                cycle_ready = False
            buy_cost = order.vnd if order.vnd is not None else order.usdt * order.unit_price
            inventory_usdt += order.usdt
            inventory_cost += buy_cost
            buy_streak_usdt += order.usdt
            buy_streak_cost += buy_cost
            buy_streak_inventory_usdt += order.usdt
            buy_streak_inventory_cost += buy_cost
            if buy_streak_usdt >= BUY_GROUP_THRESHOLD_USD or inventory_usdt > 0:
                cycle_ready = True
            avg_price = inventory_cost / inventory_usdt if inventory_usdt else order.unit_price
            if order.order_id:
                prices[str(order.order_id)] = avg_price
            last_side = "Mua"
        elif order.side == "Bán" and order.usdt and inventory_usdt:
            avg_price = inventory_cost / inventory_usdt
            sold_usdt = min(order.usdt, inventory_usdt)
            inventory_cost -= sold_usdt * avg_price
            inventory_usdt -= sold_usdt
            if inventory_usdt <= 1e-9:
                inventory_usdt = 0.0
                inventory_cost = 0.0
                buy_streak_usdt = 0.0
                buy_streak_cost = 0.0
                buy_cluster_active = False
                cycle_ready = False
            last_side = "Bán"
    return prices

def current_average_buy_price(orders) -> float | None:
    inventory_usdt = 0.0
    inventory_cost = 0.0
    buy_streak_usdt = 0.0
    buy_streak_cost = 0.0
    buy_streak_inventory_usdt = 0.0
    buy_streak_inventory_cost = 0.0
    current_buy_price = None
    cycle_ready = False
    buy_cluster_active = False
    last_side = None
    valid_orders = [order for order in orders if order.status == "Đã thực hiện" and order.timestamp]
    valid_orders.sort(key=lambda order: order.timestamp)
    for order in valid_orders:
        if order.side == "Mua" and order.unit_price is not None and order.usdt:
            if inventory_usdt <= 1e-9:
                inventory_usdt = 0.0
                inventory_cost = 0.0
                buy_streak_usdt = 0.0
                buy_streak_cost = 0.0
                buy_streak_inventory_usdt = 0.0
                buy_streak_inventory_cost = 0.0
                buy_cluster_active = True
                cycle_ready = False
            buy_cost = order.vnd if order.vnd is not None else order.usdt * order.unit_price
            inventory_usdt += order.usdt
            inventory_cost += buy_cost
            buy_streak_usdt += order.usdt
            buy_streak_cost += buy_cost
            buy_streak_inventory_usdt += order.usdt
            buy_streak_inventory_cost += buy_cost
            if buy_streak_usdt >= BUY_GROUP_THRESHOLD_USD or inventory_usdt > 0:
                cycle_ready = True
            current_buy_price = inventory_cost / inventory_usdt if inventory_usdt else order.unit_price
            last_side = "Mua"
        elif order.side == "Bán" and order.usdt and inventory_usdt:
            avg_price = inventory_cost / inventory_usdt
            sold_usdt = min(order.usdt, inventory_usdt)
            inventory_cost -= sold_usdt * avg_price
            inventory_usdt -= sold_usdt
            if inventory_usdt <= 1e-9:
                inventory_usdt = 0.0
                inventory_cost = 0.0
                buy_streak_usdt = 0.0
                buy_streak_cost = 0.0
                buy_cluster_active = False
                cycle_ready = False
            last_side = "Bán"
    return current_buy_price if cycle_ready else None

def color_order_side(row: pd.Series) -> list[str]:
    side = row.get("Loại lệnh", "")
    if side == "Mua":
        return ["background-color: #063f2b; color: #d9ffe9" if col == "Loại lệnh" else "" for col in row.index]
    if side == "Bán":
        return ["background-color: #5a1717; color: #ffe1e1" if col == "Loại lệnh" else "" for col in row.index]
    return ["" for _ in row.index]


st.set_page_config(page_title="OKX P2P Profit Bot", layout="wide")
st.title("OKX P2P Profit Bot")

uploaded_files = st.file_uploader(
    "Upload file OKX P2P",
    type=["csv", "xlsx", "xls", "png", "jpg", "jpeg"],
    accept_multiple_files=True,
    help="Ưu tiên CSV/Excel export từ OKX để có dữ liệu chính xác nhất. Ảnh chỉ là phương án dự phòng.",
)
initial_buy_input = st.text_input("Giá mua ban đầu (tùy chọn)", placeholder="Ví dụ: 25.812")

if "raw_orders" not in st.session_state:
    st.session_state.raw_orders = []
if "selected_day" not in st.session_state:
    st.session_state.selected_day = ""

def orders_to_rows(orders) -> list[dict]:
    return [
        {
            "time_text": order.time_text,
            "order_id": order.order_id,
            "side": order.side,
            "status": order.status,
            "usdt": order.usdt,
            "vnd": order.vnd,
            "unit_price": order.unit_price,
            "source": order.source,
            "raw_text": order.raw_text,
            "needs_review": order.needs_review,
        }
        for order in orders
    ]


db_cols = st.columns([1, 1, 2])
with db_cols[0]:
    if st.button("Lưu vào database"):
        orders_to_save = orders_from_rows(st.session_state.raw_orders)
        saved_count = save_orders(orders_to_save)
        all_db_orders = load_orders()
        all_sales, _, _ = calculate_sales(all_db_orders, None)
        all_sale_df = pd.DataFrame([sale.__dict__ for sale in all_sales])
        saved_days = save_daily_summaries(daily_summary(all_db_orders, all_sale_df))
        cutoff_date = purge_cutoff_date(10)
        if cutoff_date:
            snapshot_orders = [
                order for order in all_db_orders
                if order.timestamp and order.timestamp.date().isoformat() < cutoff_date
            ]
            if snapshot_orders:
                _, snapshot_summary, _ = calculate_sales(snapshot_orders, None)
                save_inventory_snapshot(
                    cutoff_date,
                    {
                        "inventory_usdt": 0.0,
                        "inventory_cost": 0.0,
                        "current_buy_price": snapshot_summary.get("Giá mua hiện tại"),
                        "last_cycle_buy_price": snapshot_summary.get("Giá mua hiện tại"),
                    },
                )
        deleted_count = purge_old_orders(10)
        st.success(f"Đã lưu/cập nhật {saved_count} lệnh, lưu {saved_days} ngày thống kê, xóa {deleted_count} lệnh chi tiết cũ hơn 10 ngày.")
with db_cols[1]:
    if st.button("Nạp từ database"):
        db_orders = load_orders()
        st.session_state.raw_orders = orders_to_rows(db_orders)
        st.success(f"Đã nạp {len(db_orders)} lệnh từ database.")
with db_cols[2]:
    st.caption(f"Database local: {count_orders()} lệnh đã lưu. Import trùng ID sẽ được cập nhật, không nhân đôi.")

if st.button("Phân tích", type="primary"):
    parsed_orders = []
    for uploaded in uploaded_files or []:
        ext = uploaded.name.lower().rsplit(".", 1)[-1]
        if ext in {"csv", "xlsx", "xls"}:
            try:
                parsed_orders.extend(read_order_file(uploaded))
            except Exception as exc:
                st.warning(f"Không đọc được file {uploaded.name}: {exc}")
        else:
            try:
                text = image_to_text(uploaded.getvalue())
                parsed_orders.extend(parse_orders_from_text(text, source=uploaded.name))
            except RuntimeError as exc:
                st.warning(str(exc))
    st.session_state.raw_orders = [
        {
            "time_text": order.time_text,
            "order_id": order.order_id,
            "side": order.side,
            "status": order.status,
            "usdt": order.usdt,
            "vnd": order.vnd,
            "unit_price": order.unit_price,
            "source": order.source,
            "raw_text": order.raw_text,
            "needs_review": order.needs_review,
        }
        for order in parsed_orders
    ]

raw_orders_list = orders_from_rows(st.session_state.raw_orders)
db_orders_list = load_orders() if count_orders() > 0 else []
if raw_orders_list and db_orders_list:
    combined_all_orders = dedupe_orders(raw_orders_list + db_orders_list)
else:
    combined_all_orders = raw_orders_list or db_orders_list

db_orders_for_stats = combined_all_orders
detail_orders = orders_for_day(combined_all_orders, st.session_state.selected_day) if st.session_state.selected_day else (raw_orders_list if raw_orders_list else combined_all_orders)

detail_title = "Dữ liệu lệnh"
if st.session_state.selected_day:
    detail_title += f" ngày {st.session_state.selected_day}"
st.subheader(detail_title)
if st.session_state.selected_day and st.button("Đóng chi tiết ngày"):
    st.session_state.selected_day = ""
    st.rerun()
if st.session_state.selected_day and db_orders_for_stats:
    selected_day_end = pd.to_datetime(st.session_state.selected_day, format="%d/%m/%Y", errors="coerce")
    day_orders_for_buy_metric = [
        order
        for order in db_orders_for_stats
        if order.timestamp and not pd.isna(selected_day_end) and order.timestamp.date() <= selected_day_end.date()
    ]
    current_cycle_price = current_average_buy_price(day_orders_for_buy_metric)
    selected_day_buy_price = average_buy_price_for_orders(detail_orders)
    metric_cols = st.columns(2)
    metric_cols[0].metric("Giá mua TB vòng đang áp dụng", format_int_vn(current_cycle_price) or "-")
    metric_cols[1].metric("Giá mua TB riêng ngày", format_int_vn(selected_day_buy_price) or "-")
elif db_orders_for_stats:
    current_cycle_price = current_average_buy_price(db_orders_for_stats)
    st.metric("Giá mua TB vòng hiện tại", format_int_vn(current_cycle_price) or "-")
editor_df = pd.DataFrame(orders_to_rows(detail_orders)).fillna("")
if editor_df.empty:
    editor_df = pd.DataFrame(columns=["time_text", "order_id", "side", "status", "usdt", "vnd", "unit_price", "source", "raw_text", "needs_review"])
if "_row_id" not in editor_df.columns:
    editor_df["_row_id"] = range(len(editor_df))
avg_price_orders = detail_orders
avg_price_map = average_buy_prices_by_order(avg_price_orders)
editor_df["avg_buy_price"] = editor_df.apply(
    lambda row: avg_price_map.get(str(row.get("order_id", "")), "") if row.get("side") == "Mua" else "",
    axis=1,
)

show_cancelled = False
show_incomplete = False
display_df = editor_df
required_cols = ["side", "usdt", "vnd", "unit_price"]
incomplete_mask = pd.Series(False, index=editor_df.index)
for col in required_cols:
    if col in editor_df.columns:
        incomplete_mask = incomplete_mask | editor_df[col].astype(str).str.strip().isin(["", "None", "nan"])
cancelled_mask = editor_df["status"].astype(str).str.strip() == "Đã hủy" if "status" in editor_df.columns else pd.Series(False, index=editor_df.index)
if not show_cancelled and "status" in display_df.columns:
    display_df = display_df[~cancelled_mask]
if not show_incomplete:
    display_df = display_df[~incomplete_mask.reindex(display_df.index, fill_value=False)]
display_df = sort_orders_newest_first(display_df)

full_data_missing_status = editor_df[
    ~incomplete_mask
    & editor_df["status"].astype(str).str.strip().isin(["", "None", "nan"])
]
if not full_data_missing_status.empty:
    st.warning(
        f"Có {len(full_data_missing_status)} dòng đã đọc được số tiền/giá nhưng thiếu trạng thái. "
        "Các dòng này chưa được tính lãi cho tới khi OCR đọc được hoặc bạn sửa status thành Đã thực hiện."
    )

st.dataframe(descending_index(format_order_display(display_df)).style.apply(color_order_side, axis=1), width="stretch")

initial_buy_price = parse_vietnam_number(initial_buy_input) if initial_buy_input.strip() else None
initial_state = None if initial_buy_price is not None else load_latest_inventory_snapshot()
orders = detail_orders
calc_orders = db_orders_for_stats if st.session_state.selected_day and db_orders_for_stats else detail_orders
sales, summary, grouped = calculate_sales(calc_orders, initial_buy_price, initial_state)
if st.session_state.selected_day:
    sales = selected_day_sales(sales, st.session_state.selected_day)
    summary, grouped = summarize_sale_rows(sales)
    selected_day_end = pd.to_datetime(st.session_state.selected_day, format="%d/%m/%Y", errors="coerce")
    day_orders_for_buy = [
        order
        for order in calc_orders
        if order.timestamp and not pd.isna(selected_day_end) and order.timestamp.date() <= selected_day_end.date()
    ]
    summary["Giá mua hiện tại"] = current_average_buy_price(day_orders_for_buy)
elif summary.get("Giá mua hiện tại") is None:
    summary["Giá mua hiện tại"] = current_average_buy_price(calc_orders)
cancelled_count = sum(1 for order in orders if order.status == "Đã hủy")
unknown_status_count = sum(
    1
    for order in orders
    if not order.status and order.side and order.usdt is not None and order.vnd is not None and order.unit_price is not None
)

sale_df = pd.DataFrame([sale.__dict__ for sale in sales])
sale_df = sort_orders_newest_first(sale_df)
grouped_df = pd.DataFrame(grouped)
summary_df = pd.DataFrame([summary])

st.subheader("Bảng chi tiết từng lệnh bán")
if cancelled_count or unknown_status_count:
    st.info(f"Đã bỏ qua {cancelled_count} dòng Đã hủy và {unknown_status_count} dòng chưa rõ trạng thái.")
average_buy_sale_ids = set(sale_df.loc[sale_df.get("buy_price_source", "") == "Giá mua TB", "order_id"].astype(str)) if not sale_df.empty and "buy_price_source" in sale_df.columns else set()
st.dataframe(
    descending_index(format_sale_display(sale_df)).style.apply(color_sale_buy_price_source, axis=1, average_buy_order_ids=average_buy_sale_ids),
    width="stretch",
    column_config={"Nguồn giá mua": None},
)

st.subheader("Thống kê theo ngày")
stats_orders = db_orders_for_stats if db_orders_for_stats else orders_from_rows(st.session_state.raw_orders)
stats_sales, _, _ = calculate_sales(stats_orders, initial_buy_price, initial_state)
stats_sale_df = pd.DataFrame([sale.__dict__ for sale in stats_sales])
live_daily_df = daily_summary(stats_orders, stats_sale_df)
daily_df = merge_archived_daily_summary(live_daily_df, load_daily_summaries())
daily_display_df = format_daily_display(daily_df)
daily_total_display_df = format_daily_display(add_daily_total_row(daily_df).tail(1)) if not daily_df.empty else pd.DataFrame()
if not daily_df.empty:
    day_options = [""] + daily_df["Ngày"].astype(str).tolist()
    current_index = day_options.index(st.session_state.selected_day) if st.session_state.selected_day in day_options else 0
    selected_day = st.selectbox(
        "Xem chi tiết ngày",
        day_options,
        index=current_index,
        format_func=lambda value: "Chọn ngày để xem chi tiết" if value == "" else value,
    )
    if selected_day != st.session_state.selected_day:
        st.session_state.selected_day = selected_day
        st.rerun()
st.dataframe(one_based_index(daily_display_df).style.apply(color_daily_profit, axis=1), width="stretch")
if not daily_total_display_df.empty:
    st.dataframe(
        daily_total_display_df.style.apply(color_daily_profit, axis=1),
        width="stretch",
        hide_index=True,
        height=72,
    )

st.subheader("Gom nhóm theo cặp giá bán/giá mua")
grouped_display_df = grouped_df.copy()
if "Chênh lệch" not in grouped_display_df.columns and {"Giá bán", "Giá mua áp dụng"}.issubset(grouped_display_df.columns):
    grouped_display_df["Chênh lệch"] = grouped_display_df["Giá bán"] - grouped_display_df["Giá mua áp dụng"]
if "Tổng lãi" in grouped_display_df.columns:
    grouped_display_df = grouped_display_df.sort_values("Tổng lãi", ascending=False)
grouped_display_df = add_grouped_total_row(grouped_display_df)
for col in ("Giá bán", "Giá mua áp dụng", "Chênh lệch"):
    if col in grouped_display_df.columns:
        grouped_display_df[col] = grouped_display_df[col].apply(lambda value: value if isinstance(value, str) and value else format_int_vn(value))
if "Tổng lãi" in grouped_display_df.columns:
    grouped_display_df["Tổng lãi"] = grouped_display_df["Tổng lãi"].apply(format_signed_int_vn)
if "Tổng USDT" in grouped_display_df.columns:
    grouped_display_df["Tổng USDT"] = grouped_display_df["Tổng USDT"].apply(format_float_vn)
st.dataframe(
    one_based_index(grouped_display_df).style.apply(color_grouped_total, axis=1),
    width="stretch",
    height=min(38 + 36 * (len(grouped_display_df) + 1), 900),
    column_config={
        "Giá bán": st.column_config.TextColumn("Giá bán", width="small"),
        "Giá mua áp dụng": st.column_config.TextColumn("Giá mua áp dụng", width="small"),
        "Chênh lệch": st.column_config.TextColumn("Chênh lệch /U", width=58),
        "Số lệnh bán": st.column_config.NumberColumn("Số lệnh bán", width=58),
        "Tổng USDT": st.column_config.TextColumn("Tổng USDT", width="small"),
        "Tổng lãi": st.column_config.TextColumn("Tổng lãi", width="small"),
    },
)

grouped_extremes_df = best_worst_grouped_profit(grouped_df)
if not grouped_extremes_df.empty:
    st.caption("Cặp lãi cao nhất / thấp nhất")
    st.dataframe(
        one_based_index(format_grouped_profit_extremes(grouped_extremes_df)).style.apply(color_profit, axis=1),
        width="stretch",
        hide_index=True,
        column_config={
            "Loại thống kê": st.column_config.TextColumn("Loại thống kê", width="medium"),
            "Giá bán": st.column_config.TextColumn("Giá bán", width="small"),
            "Giá mua áp dụng": st.column_config.TextColumn("Giá mua áp dụng", width="small"),
            "Chênh lệch": st.column_config.TextColumn("Chênh lệch /U", width=58),
            "Số lệnh bán": st.column_config.NumberColumn("Số lệnh bán", width=58),
            "Tổng USDT": st.column_config.TextColumn("Tổng USDT", width="small"),
            "Tổng lãi": st.column_config.TextColumn("Tổng lãi", width="small"),
        },
    )

st.subheader("Tổng kết")
summary_display_df = summary_df.copy()
for col in ("Tổng doanh thu VND", "Tổng lãi VND", "Spread trung bình", "Giá mua hiện tại"):
    if col in summary_display_df.columns:
        summary_display_df[col] = summary_display_df[col].apply(format_int_vn)
if "Tổng USDT đã bán" in summary_display_df.columns:
    summary_display_df["Tổng USDT đã bán"] = summary_display_df["Tổng USDT đã bán"].apply(format_float_vn)
st.dataframe(one_based_index(summary_display_df), width="stretch")

export_sale_df = format_sale_display(sale_df)
csv_bytes = export_sale_df.to_csv(index=False).encode("utf-8-sig")
st.download_button("Xuất CSV", csv_bytes, "okx_p2p_profit.csv", "text/csv")

excel_buffer = BytesIO()
with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
    export_sale_df.to_excel(writer, sheet_name="Chi tiet lenh ban", index=False)
    format_daily_display(daily_df).to_excel(writer, sheet_name="Thong ke ngay", index=False)
    grouped_df.to_excel(writer, sheet_name="Gom nhom", index=False)
    summary_df.to_excel(writer, sheet_name="Tong ket", index=False)
st.download_button(
    "Xuất Excel",
    excel_buffer.getvalue(),
    "okx_p2p_profit.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

