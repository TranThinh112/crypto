from __future__ import annotations

from collections import defaultdict
from typing import Optional

from .models import Order, SaleResult

BUY_GROUP_THRESHOLD_USD = 400.0


def calculate_sales(
    orders: list[Order],
    initial_buy_price: Optional[float] = None,
    initial_state: Optional[dict] = None,
) -> tuple[list[SaleResult], dict, list[dict]]:
    valid_orders = [order for order in orders if order.status != "Đã hủy"]
    valid_orders.sort(key=lambda order: order.timestamp or __import__("datetime").datetime.max)

    initial_state = initial_state or {}
    current_buy_price = initial_state.get("current_buy_price", initial_buy_price)
    last_cycle_buy_price = initial_state.get("last_cycle_buy_price", current_buy_price)
    inventory_usdt = float(initial_state.get("inventory_usdt") or 0.0)
    inventory_cost = float(initial_state.get("inventory_cost") or 0.0)
    buy_group_prices: set[float] = set()
    buy_streak_usdt = 0.0
    buy_streak_cost = 0.0
    buy_streak_inventory_usdt = 0.0
    buy_streak_inventory_cost = 0.0
    buy_streak_prices: set[float] = set()
    buy_cluster_active = False
    cycle_ready = initial_buy_price is not None
    last_side: str | None = None
    sales: list[SaleResult] = []

    for order in valid_orders:
        if order.status != "Đã thực hiện":
            continue
        if order.side == "Mua" and order.unit_price is not None:
            buy_usdt = order.usdt or 0
            buy_cost = order.vnd if order.vnd is not None else buy_usdt * order.unit_price
            if inventory_usdt <= 1e-9:
                inventory_usdt = 0.0
                inventory_cost = 0.0
                buy_group_prices = set()
                buy_streak_usdt = 0.0
                buy_streak_cost = 0.0
                buy_streak_inventory_usdt = 0.0
                buy_streak_inventory_cost = 0.0
                buy_streak_prices = set()
                buy_cluster_active = True
                cycle_ready = False
            if buy_usdt > 0:
                inventory_usdt += buy_usdt
                inventory_cost += buy_cost
                buy_group_prices.add(round(order.unit_price, 8))
                current_buy_price = inventory_cost / inventory_usdt
                last_cycle_buy_price = current_buy_price
                cycle_ready = True
            else:
                current_buy_price = order.unit_price
                last_cycle_buy_price = current_buy_price
                buy_group_prices.add(round(order.unit_price, 8))
            last_side = "Mua"
            continue

        if order.side != "Bán":
            continue

        issues = list(order.warnings)
        spread = None
        profit = None
        using_old_buy_price = current_buy_price is not None and inventory_usdt <= 1e-9
        applied_buy_price = current_buy_price if current_buy_price is not None else last_cycle_buy_price
        if using_old_buy_price:
            buy_price_source = "Giá mua cũ"
        elif len(buy_group_prices) > 1 and applied_buy_price is not None:
            buy_price_source = "Giá mua TB"
        else:
            buy_price_source = "Giá mua vòng"
        if applied_buy_price is None:
            issues.append("Thiếu giá mua")
        if order.usdt is None or order.unit_price is None:
            issues.append("Thiếu dữ liệu tính lãi")
        if not issues and applied_buy_price is not None and order.usdt is not None and order.unit_price is not None:
            spread = order.unit_price - applied_buy_price
            profit = (order.vnd - order.usdt * applied_buy_price) if order.vnd is not None else order.usdt * spread
            if inventory_usdt > 0:
                sold_usdt = min(order.usdt, inventory_usdt)
                inventory_cost -= sold_usdt * applied_buy_price
                inventory_usdt -= sold_usdt
                if inventory_usdt <= 1e-9:
                    inventory_usdt = 0.0
                    inventory_cost = 0.0
                    buy_group_prices = set()
                    buy_cluster_active = False
                    current_buy_price = last_cycle_buy_price
                    cycle_ready = False
                    last_cycle_buy_price = applied_buy_price

        last_side = "Bán"
        sales.append(SaleResult(
            time_text=order.time_text,
            order_id=order.order_id,
            usdt=order.usdt,
            vnd=order.vnd,
            sell_price=order.unit_price,
            applied_buy_price=applied_buy_price,
            spread=spread,
            profit=profit,
            check_status=", ".join(dict.fromkeys(issues)) if issues else "OK",
            buy_price_source=buy_price_source if not issues else "",
        ))

    grouped_map = defaultdict(lambda: {"Chênh lệch": 0.0, "Số lệnh bán": 0, "Tổng USDT": 0.0, "Tổng lãi": 0.0})
    for sale in sales:
        if sale.profit is None or sale.sell_price is None or sale.applied_buy_price is None or sale.usdt is None:
            continue
        key = (sale.sell_price, sale.applied_buy_price)
        grouped_map[key]["Chênh lệch"] = sale.sell_price - sale.applied_buy_price
        grouped_map[key]["Số lệnh bán"] += 1
        grouped_map[key]["Tổng USDT"] += sale.usdt
        grouped_map[key]["Tổng lãi"] += sale.profit

    grouped = [
        {
            "Giá bán": sell_price,
            "Giá mua áp dụng": buy_price,
            **values,
        }
        for (sell_price, buy_price), values in sorted(grouped_map.items())
    ]

    valid_sales = [sale for sale in sales if sale.profit is not None]
    total_usdt = sum(sale.usdt or 0 for sale in valid_sales)
    total_profit = sum(sale.profit or 0 for sale in valid_sales)
    summary = {
        "Tổng số lệnh bán hợp lệ": len(valid_sales),
        "Tổng USDT đã bán": total_usdt,
        "Tổng doanh thu VND": sum(sale.vnd or 0 for sale in valid_sales),
        "Tổng lãi VND": total_profit,
        "Spread trung bình": total_profit / total_usdt if total_usdt else None,
        "Giá mua hiện tại": current_buy_price,
        "Số dòng thiếu dữ liệu/cần kiểm tra": sum(1 for sale in sales if sale.check_status != "OK"),
    }
    return sales, summary, grouped
