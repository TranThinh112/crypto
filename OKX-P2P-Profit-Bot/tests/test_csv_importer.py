import pandas as pd

from okx_p2p_bot.csv_importer import orders_from_okx_dataframe


def test_imports_okx_csv_columns():
    df = pd.DataFrame(
        [
            {
                "Số lệnh": "260828173713339",
                "Loại lệnh": "Bán",
                "Tiền mã hóa": "usdt",
                "Đồng tiền": "VND",
                "Phương thức thanh toán": "Bank Transfer",
                "Giá": 25850,
                "Khối lượng": 6.0,
                "Số tiền": 155100,
                "Trạng thái": "Đã thực hiện",
                "Ngày tạo lệnh": "2026-08-28 16:37:14",
            }
        ]
    )

    order = orders_from_okx_dataframe(df)[0]

    assert order.order_id == "260828173713339"
    assert order.side == "Bán"
    assert order.status == "Đã thực hiện"
    assert order.usdt == 6.0
    assert order.vnd == 155100.0
    assert order.unit_price == 25850.0
    assert order.time_text == "16:37:14 28/08/2026"
