import asyncio

from spot_ai_bot.config import Settings
from spot_ai_bot.models import AssetGroup, TradeProposal
from spot_ai_bot.telegram import TelegramNotifier, _looks_corrupted, _u, format_portfolio_item


def test_vietnamese_message_templates_are_valid_unicode():
    samples = [
        _u("Da ket noi OKX."),
        _u("OKX da ket noi va bot da lay duoc so du tai khoan."),
        _u("MongoDB da ket noi thanh cong. Bot da san sang luu du lieu scan thi truong vao database: "),
        _u("xu huong"),
        _u("thanh khoan"),
        _u("bien dong"),
    ]

    joined = "\n".join(samples)

    assert "?" not in joined
    assert "\u00c3\u201e" not in joined
    assert "\u00c3\u00a1\u00c2\u00ba" not in joined
    assert "\u0110\u00e3 k\u1ebft n\u1ed1i OKX." in joined
    assert "s\u1ed1 d\u01b0 t\u00e0i kho\u1ea3n" in joined


def test_corrupted_vietnamese_detector_blocks_mojibake():
    assert _looks_corrupted("OKX ?? k?t n?i")
    assert _looks_corrupted("\u00c3\u201e\u00c2\u0090\u00c3\u00a1\u00c2\u00bb\u00c2\u0081 xu\u00c3\u00a1\u00c2\u00ba\u00c2\u00a5t")
    assert not _looks_corrupted(_u("Da ket noi OKX."))


def test_buy_filled_message_is_detailed_vietnamese():
    sent = []
    notifier = TelegramNotifier(Settings())
    proposal = TradeProposal(
        group=AssetGroup.crypto,
        symbol="BTCUSDT",
        action="BUY",
        amount_usd=1,
        status="live_filled",
        strategy_reason="test",
        quantity=0.00001537,
        average_price=65060.8,
        filled_notional_usd=1,
        buy_sequence="#1.1",
        exchange_order_id="3768485835261992960",
    )

    async def fake_send_text(text):
        sent.append(text)

    notifier.send_text = fake_send_text

    asyncio.run(notifier.buy_filled(proposal))

    message = sent[0]
    assert "\u2705 L\u1ec7nh mua th\u00e0nh c\u00f4ng" in message
    assert "\U0001f4cc #1.1. BTC/USDT" in message
    assert "\U0001f4b0 S\u1ed1 ti\u1ec1n mua: 1 USDT" in message
    assert "\U0001f4c8 Gi\u00e1 mua trung b\u00ecnh: 65060.8 USDT" in message
    assert "\U0001fa99 S\u1ed1 coin mua \u0111\u01b0\u1ee3c: 0.00001537 BTC" in message
    assert "\U0001f9fe M\u00e3 l\u1ec7nh OKX: 3768485835261992960" in message
    assert not _looks_corrupted(message)

def test_portfolio_item_formats_pnl_in_vietnamese():
    message = format_portfolio_item(
        {
            "asset": "BTC",
            "quantity": 0.0001,
            "price_usdt": 65000,
            "value_usdt": 6.5,
            "pnl_usdt": 3.123456,
            "pnl_pct": 20.987654,
        }
    )

    assert "S\u1ed1 l\u01b0\u1ee3ng: 0.0001" in message
    assert "T\u1ec9 gi\u00e1 hi\u1ec7n t\u1ea1i: 65000 USDT" in message
    assert "PnL: +3.12346 USDT (+20.98765%)" in message
    assert not _looks_corrupted(message)
