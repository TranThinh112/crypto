from okx_p2p_bot.normalize import normalize_status
from okx_p2p_bot.parser import choose_best_timestamp, parse_orders_from_text


def test_fuzzy_completed_status():
    assert normalize_status("Da thyc hien") == "Đã thực hiện"
    assert normalize_status("Dã thuc hién") == "Đã thực hiện"
    assert normalize_status("Da th... hien") == "Đã thực hiện"
    assert normalize_status("Đã thục h") == "Đã thực hiện"
    assert normalize_status("Đã thực biê") == "Đã thực hiện"


def test_infers_missing_leading_digit_unit_price():
    order = parse_orders_from_text(
        "260828073338267 Ban 15.46 400000 2860 Da thuc hien 06:33:39 28/08/2026"
    )[0]

    assert order.status == "Đã thực hiện"
    assert order.unit_price == 25873.0


def test_merges_status_fragment_near_same_time():
    orders = parse_orders_from_text(
        "\n".join(
            [
                "260828122826379 Ban 27.08 700000 25840 11:28:27 28/08/2026",
                "Da thuc hien 11:28:20 28/08/2026",
            ]
        )
    )

    assert len(orders) == 1
    assert orders[0].status == "Đã thực hiện"
    assert orders[0].usdt == 27.08


def test_removes_partial_duplicate_order_id():
    orders = parse_orders_from_text(
        "\n".join(
            [
                "260828072518679 Ban 23.2 600000 25860 Da thuc hien 06:26:19 28/08/2026",
                "8072518679 Ban 23.2 600000 25860 Da thuc hien 06:26:19 28/08/2026",
            ]
        )
    )

    assert len(orders) == 1
    assert orders[0].order_id == "260828072518679"


def test_corrects_bad_ocr_time_from_order_id():
    timestamp = choose_best_timestamp("19:13:25 28/08/2026", "260828121323638")

    assert timestamp.strftime("%H:%M:%S %d/%m/%Y") == "11:13:23 28/08/2026"


def test_corrects_missing_hour_digit_from_order_id():
    timestamp = choose_best_timestamp("1:31:21 28/08/2026", "260828123120667")

    assert timestamp.strftime("%H:%M:%S %d/%m/%Y") == "11:31:20 28/08/2026"


def test_removes_no_id_duplicate_even_when_time_is_bad():
    orders = parse_orders_from_text(
        "\n".join(
            [
                "260828123055485 Ban 15.47 400000 25840 Da thuc hien 11:30:57 28/08/2026",
                "Ban 15.47 400000 25840 Da thuc hien 1:31:21 28/08/2026",
            ]
        )
    )

    assert len(orders) == 1
    assert orders[0].order_id == "260828123055485"
