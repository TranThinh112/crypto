import pandas as pd

from okx_p2p_bot.calculator import calculate_sales
from okx_p2p_bot.parser import orders_from_rows


def test_profit_with_initial_buy_price():
    rows = pd.read_csv("sample_orders.csv").to_dict("records")
    sales, summary, grouped = calculate_sales(orders_from_rows(rows), initial_buy_price=25812)

    assert summary["Tổng số lệnh bán hợp lệ"] == 5
    assert round(summary["Tổng lãi VND"], 2) == 7970.51
    assert [sale for sale in sales if sale.order_id == "S005"][0].buy_price_source == "Giá mua TB"
    assert len(grouped) == 4
    assert all(sale.order_id != "S006" for sale in sales)


def test_missing_initial_buy_price_marks_early_sales():
    rows = pd.read_csv("sample_orders.csv").to_dict("records")
    sales, summary, _ = calculate_sales(orders_from_rows(rows), initial_buy_price=None)

    early = [sale for sale in sales if sale.order_id in {"S001", "S002"}]
    assert all("Thiếu giá mua" in sale.check_status for sale in early)
    assert summary["Tổng số lệnh bán hợp lệ"] == 3

def test_new_buy_cycle_starts_after_inventory_is_sold_out():
    rows = [
        {"time_text": "10:00:00 28/08/2026", "order_id": "B001", "side": "Mua", "status": "Đã thực hiện", "usdt": 200, "vnd": 5162000, "unit_price": 25810},
        {"time_text": "11:00:00 28/08/2026", "order_id": "B002", "side": "Mua", "status": "Đã thực hiện", "usdt": 200, "vnd": 5164000, "unit_price": 25820},
        {"time_text": "12:00:00 28/08/2026", "order_id": "S001", "side": "Bán", "status": "Đã thực hiện", "usdt": 400, "vnd": 10376000, "unit_price": 25940},
        {"time_text": "13:00:00 29/08/2026", "order_id": "B003", "side": "Mua", "status": "Đã thực hiện", "usdt": 400, "vnd": 10356000, "unit_price": 25890},
        {"time_text": "14:00:00 29/08/2026", "order_id": "S002", "side": "Bán", "status": "Đã thực hiện", "usdt": 10, "vnd": 259400, "unit_price": 25940},
    ]

    sales, _, _ = calculate_sales(orders_from_rows(rows))

    first_cycle_sale = [sale for sale in sales if sale.order_id == "S001"][0]
    second_cycle_sale = [sale for sale in sales if sale.order_id == "S002"][0]
    assert first_cycle_sale.applied_buy_price == 25815
    assert first_cycle_sale.buy_price_source == "Giá mua TB"
    assert second_cycle_sale.applied_buy_price == 25890
    assert second_cycle_sale.buy_price_source == "Giá mua vòng"

def test_sell_group_keeps_latest_buy_group_price_until_new_buy_group():
    rows = [
        {"time_text": "10:00:00 28/08/2026", "order_id": "B001", "side": "Mua", "status": "Đã thực hiện", "usdt": 400, "vnd": 10324800, "unit_price": 25812},
        {"time_text": "11:00:00 28/08/2026", "order_id": "S001", "side": "Bán", "status": "Đã thực hiện", "usdt": 10, "vnd": 258500, "unit_price": 25850},
        {"time_text": "12:00:00 28/08/2026", "order_id": "S002", "side": "Bán", "status": "Đã thực hiện", "usdt": 5, "vnd": 129250, "unit_price": 25850},
    ]

    sales, _, _ = calculate_sales(orders_from_rows(rows))

    second_sale = [sale for sale in sales if sale.order_id == "S002"][0]
    assert second_sale.applied_buy_price == 25812
    assert second_sale.buy_price_source == "Giá mua vòng"

def test_sales_after_inventory_is_empty_keep_previous_buy_price():
    rows = [
        {"time_text": "10:00:00 28/08/2026", "order_id": "B001", "side": "Mua", "status": "Đã thực hiện", "usdt": 10, "vnd": 258120, "unit_price": 25812},
        {"time_text": "11:00:00 28/08/2026", "order_id": "S001", "side": "Bán", "status": "Đã thực hiện", "usdt": 10, "vnd": 258500, "unit_price": 25850},
        {"time_text": "12:00:00 28/08/2026", "order_id": "S002", "side": "Bán", "status": "Đã thực hiện", "usdt": 5, "vnd": 129250, "unit_price": 25850},
    ]

    sales, summary, _ = calculate_sales(orders_from_rows(rows))

    second_sale = [sale for sale in sales if sale.order_id == "S002"][0]
    assert second_sale.check_status == "OK"
    assert second_sale.applied_buy_price == 25812
    assert second_sale.buy_price_source == "Giá mua cũ"
    assert summary["Tổng số lệnh bán hợp lệ"] == 2

def test_interleaved_sale_uses_current_average_buy_price_before_400_usdt():
    rows = [
        {"time_text": "10:00:00 28/08/2026", "order_id": "B001", "side": "Mua", "status": "Đã thực hiện", "usdt": 399, "vnd": 10298970, "unit_price": 25812},
        {"time_text": "11:00:00 28/08/2026", "order_id": "S001", "side": "Bán", "status": "Đã thực hiện", "usdt": 10, "vnd": 258500, "unit_price": 25850},
        {"time_text": "12:00:00 28/08/2026", "order_id": "B002", "side": "Mua", "status": "Đã thực hiện", "usdt": 5, "vnd": 129250, "unit_price": 25850},
    ]

    sales, summary, _ = calculate_sales(orders_from_rows(rows))

    assert sales[0].check_status == "OK"
    assert round(sales[0].applied_buy_price, 2) == 25811.95
    assert summary["Tổng số lệnh bán hợp lệ"] == 1

def test_buy_on_later_day_is_added_to_remaining_inventory():
    rows = [
        {"time_text": "10:00:00 20/09/2026", "order_id": "B001", "side": "Mua", "status": "Đã thực hiện", "usdt": 100, "vnd": 2580000, "unit_price": 25800},
        {"time_text": "11:00:00 20/09/2026", "order_id": "S001", "side": "Bán", "status": "Đã thực hiện", "usdt": 20, "vnd": 517000, "unit_price": 25850},
        {"time_text": "09:00:00 21/09/2026", "order_id": "B002", "side": "Mua", "status": "Đã thực hiện", "usdt": 30, "vnd": 774000, "unit_price": 25800},
        {"time_text": "10:00:00 21/09/2026", "order_id": "S002", "side": "Bán", "status": "Đã thực hiện", "usdt": 10, "vnd": 258500, "unit_price": 25850},
    ]

    sales, summary, _ = calculate_sales(orders_from_rows(rows))

    second_sale = [sale for sale in sales if sale.order_id == "S002"][0]
    assert second_sale.applied_buy_price == 25800
    assert summary["Giá mua hiện tại"] == 25800
