import httpx
from decimal import Decimal, InvalidOperation
from datetime import timezone
from zoneinfo import ZoneInfo

from spot_ai_bot.config import Settings
from spot_ai_bot.db import active_shortlist_entries
from spot_ai_bot.models import PositionManagementProposal, TradeProposal


class TelegramNotifier:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def send_text(self, text: str) -> None:
        if not self.settings.telegram_bot_token or not self.settings.telegram_chat_id:
            return
        if _looks_corrupted(text):
            raise ValueError("Refusing to send a corrupted Vietnamese Telegram message.")
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        payload = {"chat_id": self.settings.telegram_chat_id, "text": text}
        if self.settings.telegram_message_thread_id:
            payload["message_thread_id"] = self.settings.telegram_message_thread_id
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()

    async def send_text_with_buttons(self, text: str, buttons: list[list[dict]]) -> None:
        if not self.settings.telegram_bot_token or not self.settings.telegram_chat_id:
            return
        if _looks_corrupted(text):
            raise ValueError("Refusing to send a corrupted Vietnamese Telegram message.")
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": self.settings.telegram_chat_id,
            "text": text,
            "reply_markup": {"inline_keyboard": buttons},
        }
        if self.settings.telegram_message_thread_id:
            payload["message_thread_id"] = self.settings.telegram_message_thread_id
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()

    async def set_commands(self) -> dict | None:
        if not self.settings.telegram_bot_token:
            return None
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/setMyCommands"
        payload = {
            "commands": [
                {"command": "menu", "description": _u("Mo bang dieu khien")},
                {"command": "setup", "description": _u("Mo menu setup")},
                {"command": "guard", "description": "Xem Market Guard"},
                {"command": "lichsumua", "description": _u("Lich su lenh mua")},
                {"command": "taisan", "description": _u("Danh muc tai san")},
                {"command": "quanly", "description": _u("Quan ly tai san")},
                {"command": "shortlist", "description": _u("Danh sach shortlist")},
            ]
        }
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    async def proposal(self, proposal: TradeProposal) -> None:
        if proposal.status == "live_filled":
            await self.buy_filled(proposal)
            return
        advisor = proposal.advisor
        text = (
            f"{_u('De xuat giao dich')} [{proposal.group.value.upper()}]\n"
            f"{_u('Hanh dong')}: {_translate_action(proposal.action)} {proposal.symbol}\n"
            f"{_u('So tien')}: {proposal.amount_usd} USD\n"
            f"{_u('Trang thai')}: {_translate_status(proposal.status)}\n"
            f"{_u('Chien luoc')}: {_translate_strategy_reason(proposal.strategy_reason)}\n"
            f"{_u('Y kien AI')}: {advisor.opinion if advisor else _u('khong co')} "
            f"({advisor.confidence if advisor else _u('khong co')})\n"
            f"{_u('Rui ro')}: {', '.join(proposal.risk_notes) if proposal.risk_notes else _u('on')}"
        )
        await self.send_text(text)

    async def buy_filled(self, proposal: TradeProposal) -> None:
        await self.send_text(format_buy_filled(proposal))

    async def menu(self) -> None:
        text = (
            f"{_u('icon_menu')} {_u('Menu dieu khien')}\n"
            f"/menu - {_u('Mo bang dieu khien')}\n"
            f"/setup - {_u('Mo menu setup')}\n"
            f"/guard - Xem Market Guard\n"
            f"/lichsumua - {_u('Lich su lenh mua')}\n"
            f"/taisan - {_u('Danh muc tai san')}\n"
            f"/quanly - {_u('Quan ly tai san')}\n"
            f"/shortlist - {_u('Danh sach shortlist')}"
        )
        await self.send_text(text)

    async def buy_history(self, items: list[dict]) -> None:
        if not items:
            await self.send_text(f"{_u('icon_history')} {_u('Chua co lich su mua nao')}")
            return
        rows = [f"{_u('icon_history')} {_u('Lich su lenh mua')}"]
        for item in items[:10]:
            rows.append(format_buy_history_item(item))
        await self.send_text("\n\n".join(rows))

    async def portfolio(self, portfolio: dict) -> None:
        assets = portfolio.get("assets") or []
        if not assets:
            await self.send_text(f"{_u('icon_wallet')} {_u('Chua co tai san spot nao')}")
            return
        rows = [
            f"{_u('icon_wallet')} {_u('Danh muc tai san')}",
            f"{_u('Nguon')}: OKX Trading cash + Funding",
        ]
        if portfolio.get("cache_hit"):
            rows.append(f"{_u('Du lieu cache')}: {portfolio.get('cache_seconds')}s")
        known_pnl = portfolio.get("known_pnl_usdt")
        if known_pnl:
            rows.append(f"{_u('PnL da co gia von')}: {_format_signed(known_pnl, 5)} USDT")
        for item in [asset for asset in assets if asset.get("asset") not in {"USDT", "USDC", "USD"}][:20]:
            rows.append(format_portfolio_item(item))
        if len(rows) == 2:
            rows.append(_u("Chua co coin nao du nguong hien thi"))
        await self.send_text("\n\n".join(rows))

    async def position_management(self, report: dict) -> None:
        proposals = report.get("proposals") or []
        if not proposals:
            await self.send_text(f"{_u('icon_guard')} {_u('Chua co coin nao can quan ly')}")
            return
        rows = [
            f"{_u('icon_guard')} {_u('Quan ly tai san')}",
            f"{_u('So lenh AI da goi')}: {report.get('ai_calls', 0)}",
        ]
        for proposal in proposals[:10]:
            rows.append(format_position_management_item(proposal))
        await self.send_text("\n\n".join(rows))

    async def scan_summary(self, snapshot: dict) -> None:
        candidates = snapshot.get("candidates", [])
        rows = []
        for candidate in candidates[:6]:
            metadata = candidate.get("metadata") or {}
            rows.append(_format_candidate(candidate, metadata))
        text = (
            f"Crypto Spot AI Bot - {_u('quet thi truong')}\n"
            f"{_u('San')}: {snapshot.get('exchange')}\n"
            f"{_u('Nguon du lieu')}: {_translate_source(snapshot.get('data_source'))}\n"
            f"{_u('So ma theo doi')}: {snapshot.get('candidate_count')}\n"
            + ("\n".join(rows) if rows else _u("Khong co ma nao."))
        )
        if snapshot.get("fallback_reason"):
            text += f"\n{_u('Ly do dung du lieu du phong')}: {snapshot.get('fallback_reason')}"
        if snapshot.get("shortlist_count") is not None:
            text += f"\n{_u('Ma vao shortlist')}: {snapshot.get('shortlist_count')}"
        await self.send_text(text)

    async def shortlist(self, items: list[dict]) -> None:
        if not items:
            await self.send_text(f"{_u('icon_history')} {_u('Chua co shortlist nao')}")
            return
        rows = [f"{_u('icon_history')} {_u('Danh sach shortlist')}"]
        for item in items[:10]:
            rows.append(_format_shortlist_item(item))
        await self.send_text("\n\n".join(rows))

    async def scan_alert(self, alert: dict) -> None:
        rows = []
        for candidate in alert.get("candidates", [])[:6]:
            metadata = candidate.get("metadata") or {}
            rows.append(_format_candidate(candidate, metadata))
        text = (
            f"Crypto Spot AI Bot - {_u('canh bao')}\n"
            f"{alert.get('title')}\n"
            f"{alert.get('detail')}\n"
            + ("\n".join(rows) if rows else "")
        ).strip()
        await self.send_text(text)

    async def top_scan_report(self, snapshot: dict, top_candidates: list[dict], report_no: int) -> None:
        created_at = snapshot.get("created_at")
        rows = [
            f"\U0001f4ca {_u('Bao cao scan dinh ky')} #{report_no}",
            f"{_u('Ngay gio')}: {_format_local_time(created_at)}",
            f"{_u('San')}: {str(snapshot.get('exchange') or '').upper()}",
            f"{_u('So ma theo doi')}: {snapshot.get('candidate_count', 0)}",
            "",
            f"\U0001f3c6 Top 5 {_u('cap diem cao nhat')}:",
        ]
        if not top_candidates:
            rows.append(_u("Khong co ma nao."))
        for index, candidate in enumerate(top_candidates, start=1):
            metadata = candidate.get("metadata") or {}
            rows.append(
                f"{_rank_icon(index)} {index}. {_display_pair(str(candidate.get('symbol') or ''))}\n"
                f"   \U0001f4b5 {_u('Gia')}: {_format_number(candidate.get('price'), 8)} USDT\n"
                f"   \U0001f5c2\ufe0f {_u('Nhom')}: {_translate_sector(metadata.get('crypto_sector'))}\n"
                f"   \U0001f4ca {_u('Diem')}: {_format_number(candidate.get('composite_score'), 4)}"
            )
        await self.send_text("\n".join(rows))

    async def watchlist_care_alert(self, event: dict) -> None:
        symbol = str(event.get("symbol") or "")
        status = str(event.get("status") or "-")
        text = (
            f"Watchlist Care\n"
            f"Cap: {_display_pair(symbol)}\n"
            f"Trang thai: {status}\n"
            f"Ly do: {event.get('status_reason') or '-'}\n"
            f"Gia: {_format_number(event.get('price_usdt'), 8)} USDT\n"
            f"Invalidation: {_format_number(event.get('invalidation_price_usdt'), 8)} USDT\n"
            f"TP: {', '.join(_format_number(x, 8) for x in (event.get('take_profit_zones_usdt') or []))}"
        )
        buttons = [
            [
                {"text": "Approve Buy", "callback_data": f"trade:approve_buy:{symbol}"},
                {"text": "Watch Only", "callback_data": f"trade:watch_only:{symbol}"},
            ],
            [
                {"text": "Reject", "callback_data": f"trade:reject:{symbol}"},
                {"text": "Snooze 1h", "callback_data": f"trade:snooze_1h:{symbol}"},
            ],
        ]
        await self.send_text_with_buttons(text, buttons)

    async def mongodb_connected(self, database: str) -> None:
        await self.send_text(
            _u(
                "MongoDB da ket noi thanh cong. "
                "Bot da san sang luu du lieu scan thi truong vao database: "
            )
            + database
            + "."
        )

    async def okx_connected(self) -> None:
        await self.send_text(_u("Da ket noi OKX."))

    async def okx_balance_loaded(self, currency_count: int, nonzero_currency_count: int) -> None:
        await self.send_text(
            _u("OKX da ket noi va bot da lay duoc so du tai khoan.")
            + f"\n{_u('So loai tai san trong phan hoi')}: {currency_count}"
            + f"\n{_u('So loai tai san co so du khac 0')}: {nonzero_currency_count}"
        )


def _format_candidate(candidate: dict, metadata: dict) -> str:
    return (
        f"{candidate.get('symbol')}: {candidate.get('price')} "
        f"| {_u('xu huong')} {candidate.get('trend_score')} "
        f"| {_u('thanh khoan')} {candidate.get('liquidity_score')} "
        f"| {_u('bien dong')} {candidate.get('volatility_score', '-')} "
        f"| {_u('thay doi')} {metadata.get('change_pct', '-')}"
    )

def format_buy_filled(proposal: TradeProposal) -> str:
    pair = _display_pair(proposal.symbol)
    base_asset = pair.split("/")[0]
    sequence = proposal.buy_sequence or "#?"
    return (
        f"{_u('icon_success')} {_u('Lenh mua thanh cong')}\n"
            f"{_u('icon_pair')} {sequence}. {pair}\n"
            f"{_u('icon_time')} {_u('Ngay gio')}: {_format_local_time(proposal.created_at)}\n"
            f"{_u('icon_money')} {_u('So tien mua')}: {_format_number(proposal.filled_notional_usd or proposal.amount_usd, 5)} USDT\n"
            f"{_u('icon_price')} {_u('Gia mua trung binh')}: {_format_number(proposal.average_price or proposal.price, 5)} USDT\n"
            f"{_u('icon_coin')} {_u('So coin mua duoc')}: {_format_number(proposal.quantity)} {base_asset}\n"
        f"{_u('icon_order')} {_u('Ma lenh OKX')}: {proposal.exchange_order_id or _u('khong co')}\n"
        f"{_u('icon_mode')} {_u('Che do giao dich')}: spot cash"
    )

def format_buy_history_item(item: dict) -> str:
    pair = _display_pair(str(item.get("symbol") or ""))
    base_asset = pair.split("/")[0] if "/" in pair else pair
    return (
        f"{_u('icon_pair')} {item.get('buy_sequence') or '#?'}. {pair}\n"
        f"{_u('icon_time')} {_u('Ngay gio')}: {_format_local_time(item.get('created_at'))}\n"
        f"{_u('icon_money')} {_u('So tien mua')}: {_format_number(item.get('filled_notional_usd') or item.get('amount_usd'), 5)} USDT\n"
        f"{_u('icon_price')} {_u('Gia mua trung binh')}: {_format_number(item.get('average_price') or item.get('price'), 5)} USDT\n"
        f"{_u('icon_coin')} {_u('So coin mua duoc')}: {_format_number(item.get('quantity'))} {base_asset}\n"
        f"{_u('icon_order')} {_u('Ma lenh OKX')}: {item.get('exchange_order_id') or _u('khong co')}"
    )

def format_portfolio_item(item: dict) -> str:
    pnl = _u("chua co gia von")
    if item.get("pnl_usdt") is not None and item.get("pnl_pct") is not None:
        pnl = f"{_format_signed(item.get('pnl_usdt'), 5)} USDT ({_format_signed(item.get('pnl_pct'), 5)}%)"
    return (
        f"{_u('icon_coin')} {item.get('asset')}\n"
        f"{_u('So luong')}: {_format_number(item.get('quantity'))}\n"
        f"{_u('Ti gia hien tai')}: {_format_number(item.get('price_usdt'), 5)} USDT\n"
        f"{_u('Gia tri')}: {_format_number(item.get('value_usdt'), 5)} USDT\n"
        f"PnL: {pnl}"
    )

def format_position_management_item(proposal: PositionManagementProposal | dict) -> str:
    item = proposal.model_dump(mode="json") if hasattr(proposal, "model_dump") else proposal
    ai = item.get("ai_opinion") or {}
    ai_text = _u("khong goi AI")
    if item.get("ai_called"):
        ai_text = (
            f"{ai.get('suggested_action', '-')}"
            f" ({_format_number(ai.get('confidence'), 5)})"
        )
    pnl = _u("chua co gia von")
    if item.get("pnl_usdt") is not None and item.get("pnl_pct") is not None:
        pnl = f"{_format_signed(item.get('pnl_usdt'), 5)} USDT ({_format_signed(item.get('pnl_pct'), 5)}%)"
    return (
        f"{_u('icon_coin')} {item.get('symbol')}\n"
        f"PnL: {pnl}\n"
        f"{_u('Xu huong')}: {_format_number(item.get('trend_score'), 5)} | "
        f"{_u('Thanh khoan')}: {_format_number(item.get('liquidity_score'), 5)} | "
        f"{_u('Bien dong')}: {_format_number(item.get('volatility_score'), 5)}\n"
        f"{_u('Ho tro')}: {_format_number(item.get('support_usdt'), 5)} | "
        f"{_u('Khang cu')}: {_format_number(item.get('resistance_usdt'), 5)} | "
        f"{_u('Ty trong')}: {_format_number(item.get('position_weight_pct'), 5)}%\n"
        f"{_u('Hanh dong rule')}: {_translate_management_action(item.get('recommended_action'))}\n"
        f"{_u('Y kien AI')}: {ai_text}\n"
        f"{_u('Hanh dong cuoi')}: {_translate_management_action(item.get('final_action'))}\n"
        f"{_u('Ty le de xuat')}: {_format_number(item.get('proposed_size_pct'), 5)}%\n"
        f"{_u('Trang thai phe duyet')}: {item.get('approval_status')}\n"
        f"{_u('Ly do')}: {item.get('rule_reason')}\n"
        f"{_u('Rui ro')}: {', '.join(item.get('risk_notes') or []) if item.get('risk_notes') else _u('on')}"
    )

def _display_pair(symbol: str) -> str:
    normalized = symbol.replace("-", "/").upper()
    if "/" in normalized:
        return normalized
    if normalized.endswith("USDT"):
        return normalized[:-4] + "/USDT"
    return normalized

def _format_local_time(value) -> str:
    local_tz = ZoneInfo("Asia/Ho_Chi_Minh")
    if value is None:
        return "-"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(local_tz).strftime("%d/%m/%Y %H:%M:%S")

def _format_number(value, max_decimals: int = 12) -> str:
    if value is None:
        return "-"
    try:
        decimal_value = Decimal(str(value))
        quant = Decimal("1") if max_decimals <= 0 else Decimal("1").scaleb(-max_decimals)
        text = format(decimal_value.quantize(quant).normalize(), "f")
    except (InvalidOperation, ValueError):
        text = str(value)
    return text or "0"

def _format_signed(value, max_decimals: int = 12) -> str:
    if value is None:
        return "-"
    number = float(value)
    sign = "+" if number > 0 else ""
    return sign + _format_number(number, max_decimals)


def _translate_source(source: str | None) -> str:
    if source == "live":
        return _u("du lieu that")
    if source == "fallback":
        return _u("du lieu du phong")
    if source == "empty":
        return _u("khong co du lieu")
    return source or _u("khong ro")

def _translate_sector(sector: str | None) -> str:
    translations = {
        "layer1": "Layer 1",
        "layer2": "Layer 2",
        "ai": "AI",
        "defi": "DeFi",
        "meme": "Meme",
        "infra": "Infra",
        "stable": "Stable",
        "other": "Other",
    }
    return translations.get(str(sector or "other").lower(), "Other")

def _rank_icon(index: int) -> str:
    return {
        1: "\U0001f947",
        2: "\U0001f948",
        3: "\U0001f949",
        4: "\U0001f4cc",
        5: "\U0001f4cc",
    }.get(index, "\U0001f4cc")


def _translate_action(action: str) -> str:
    if action == "BUY":
        return _u("MUA")
    if action == "SELL":
        return _u("BAN")
    return action

def _translate_management_action(action: str | None) -> str:
    translations = {
        "HOLD": _u("GIU"),
        "WATCH": _u("GIU VA THEO DOI"),
        "CONSIDER_ADD": _u("CAN NHAC MUA THEM"),
        "TAKE_PROFIT_PARTIAL": _u("CHOT LOI MOT PHAN"),
        "TAKE_PROFIT_FULL": _u("CHOT LOI TOAN BO"),
        "HIGH_RISK_ALERT": _u("CANH BAO RUI RO CAO"),
    }
    return translations.get(action or "", action or "-")


def _translate_status(status: str) -> str:
    translations = {
        "pending": _u("dang cho"),
        "paper_filled": _u("da khop lenh mo phong"),
        "live_filled": _u("da khop lenh that"),
        "live_failed": _u("lenh that bi loi"),
        "blocked_live_guard": _u("bi chan boi bao ve live"),
        "rejected_by_risk": _u("bi tu choi boi quan tri rui ro"),
    }
    return translations.get(status, status)


def _translate_strategy_reason(reason: str) -> str:
    if reason == "RuleStrategy: trend_score >= 0.65 and liquidity_score >= 0.70.":
        return _u("RuleStrategy: diem xu huong >= 0.65 va diem thanh khoan >= 0.70.")
    return reason


def _looks_corrupted(text: str) -> bool:
    markers = ("Ä", "áº", "á»", "Ã", "�", "??")
    return any(marker in text for marker in markers)


def _u(text: str) -> str:
    table = str.maketrans(
        {
            "a": "a",
        }
    )
    _ = table
    translations = {
        "De xuat giao dich": "\u0110\u1ec1 xu\u1ea5t giao d\u1ecbch",
        "Hanh dong": "H\u00e0nh \u0111\u1ed9ng",
        "So tien": "S\u1ed1 ti\u1ec1n",
        "Trang thai": "Tr\u1ea1ng th\u00e1i",
        "Chien luoc": "Chi\u1ebfn l\u01b0\u1ee3c",
        "Y kien AI": "\u00dd ki\u1ebfn AI",
        "khong co": "kh\u00f4ng c\u00f3",
        "Rui ro": "R\u1ee7i ro",
        "on": "\u1ed5n",
        "quet thi truong": "qu\u00e9t th\u1ecb tr\u01b0\u1eddng",
        "San": "S\u00e0n",
        "Nguon du lieu": "Ngu\u1ed3n d\u1eef li\u1ec7u",
        "So ma theo doi": "S\u1ed1 m\u00e3 theo d\u00f5i",
        "Bao cao scan dinh ky": "B\u00e1o c\u00e1o scan \u0111\u1ecbnh k\u1ef3",
        "cap diem cao nhat": "c\u1eb7p \u0111i\u1ec3m cao nh\u1ea5t",
        "Gia": "Gi\u00e1",
        "Nhom": "Nh\u00f3m",
        "Ma vao shortlist": "M\u00e3 v\u00e0o shortlist",
        "Khong co ma nao.": "Kh\u00f4ng c\u00f3 m\u00e3 n\u00e0o.",
        "Ly do dung du lieu du phong": "L\u00fd do d\u00f9ng d\u1eef li\u1ec7u d\u1ef1 ph\u00f2ng",
        "canh bao": "c\u1ea3nh b\u00e1o",
        "MongoDB da ket noi thanh cong. Bot da san sang luu du lieu scan thi truong vao database: ": "MongoDB \u0111\u00e3 k\u1ebft n\u1ed1i th\u00e0nh c\u00f4ng. Bot \u0111\u00e3 s\u1eb5n s\u00e0ng l\u01b0u d\u1eef li\u1ec7u scan th\u1ecb tr\u01b0\u1eddng v\u00e0o database: ",
        "Da ket noi OKX.": "\u0110\u00e3 k\u1ebft n\u1ed1i OKX.",
        "OKX da ket noi va bot da lay duoc so du tai khoan.": "OKX \u0111\u00e3 k\u1ebft n\u1ed1i v\u00e0 bot \u0111\u00e3 l\u1ea5y \u0111\u01b0\u1ee3c s\u1ed1 d\u01b0 t\u00e0i kho\u1ea3n.",
        "So loai tai san trong phan hoi": "S\u1ed1 lo\u1ea1i t\u00e0i s\u1ea3n trong ph\u1ea3n h\u1ed3i",
        "So loai tai san co so du khac 0": "S\u1ed1 lo\u1ea1i t\u00e0i s\u1ea3n c\u00f3 s\u1ed1 d\u01b0 kh\u00e1c 0",
        "xu huong": "xu h\u01b0\u1edbng",
        "thanh khoan": "thanh kho\u1ea3n",
        "bien dong": "bi\u1ebfn \u0111\u1ed9ng",
        "thay doi": "thay \u0111\u1ed5i",
        "du lieu that": "d\u1eef li\u1ec7u th\u1eadt",
        "du lieu du phong": "d\u1eef li\u1ec7u d\u1ef1 ph\u00f2ng",
        "khong co du lieu": "kh\u00f4ng c\u00f3 d\u1eef li\u1ec7u",
        "khong ro": "kh\u00f4ng r\u00f5",
        "MUA": "MUA",
        "BAN": "B\u00c1N",
        "dang cho": "\u0111ang ch\u1edd",
        "da khop lenh mo phong": "\u0111\u00e3 kh\u1edbp l\u1ec7nh m\u00f4 ph\u1ecfng",
        "da khop lenh that": "\u0111\u00e3 kh\u1edbp l\u1ec7nh th\u1eadt",
        "lenh that bi loi": "l\u1ec7nh th\u1eadt b\u1ecb l\u1ed7i",
        "bi chan boi bao ve live": "b\u1ecb ch\u1eb7n b\u1edfi b\u1ea3o v\u1ec7 live",
        "bi tu choi boi quan tri rui ro": "b\u1ecb t\u1eeb ch\u1ed1i b\u1edfi qu\u1ea3n tr\u1ecb r\u1ee7i ro",
        "RuleStrategy: diem xu huong >= 0.65 va diem thanh khoan >= 0.70.": "RuleStrategy: \u0111i\u1ec3m xu h\u01b0\u1edbng >= 0.65 v\u00e0 \u0111i\u1ec3m thanh kho\u1ea3n >= 0.70.",
        "Lenh mua thanh cong": "L\u1ec7nh mua th\u00e0nh c\u00f4ng",
        "Ngay gio": "Ng\u00e0y gi\u1edd",
        "So tien mua": "S\u1ed1 ti\u1ec1n mua",
        "Gia mua trung binh": "Gi\u00e1 mua trung b\u00ecnh",
        "So coin mua duoc": "S\u1ed1 coin mua \u0111\u01b0\u1ee3c",
        "Ma lenh OKX": "M\u00e3 l\u1ec7nh OKX",
        "Che do giao dich": "Ch\u1ebf \u0111\u1ed9 giao d\u1ecbch",
        "Mo bang dieu khien": "M\u1edf b\u1ea3ng \u0111i\u1ec1u khi\u1ec3n",
        "Mo menu setup": "M\u1edf menu setup",
        "Lich su lenh mua": "L\u1ecbch s\u1eed l\u1ec7nh mua",
        "Menu dieu khien": "Menu \u0111i\u1ec1u khi\u1ec3n",
        "Chua co lich su mua nao": "Ch\u01b0a c\u00f3 l\u1ecbch s\u1eed mua n\u00e0o",
        "Danh muc tai san": "Danh m\u1ee5c t\u00e0i s\u1ea3n",
        "Quan ly tai san": "Qu\u1ea3n l\u00fd t\u00e0i s\u1ea3n",
        "Chua co coin nao can quan ly": "Ch\u01b0a c\u00f3 coin n\u00e0o c\u1ea7n qu\u1ea3n l\u00fd",
        "So lenh AI da goi": "S\u1ed1 l\u1ea7n AI \u0111\u00e3 g\u1ecdi",
        "Chua co tai san spot nao": "Ch\u01b0a c\u00f3 t\u00e0i s\u1ea3n spot n\u00e0o",
        "Chua co coin nao du nguong hien thi": "Ch\u01b0a c\u00f3 coin n\u00e0o \u0111\u1ee7 ng\u01b0\u1ee1ng hi\u1ec3n th\u1ecb",
        "Chua co shortlist nao": "Ch\u01b0a c\u00f3 shortlist n\u00e0o",
        "Danh sach shortlist": "Danh s\u00e1ch shortlist",
        "Tong gia tri": "T\u1ed5ng gi\u00e1 tr\u1ecb",
        "Tong gia tri quy doi": "T\u1ed5ng gi\u00e1 tr\u1ecb quy \u0111\u1ed5i",
        "Von spot USDT": "V\u1ed1n spot USDT",
        "Nguon": "Ngu\u1ed3n",
        "Du lieu cache": "D\u1eef li\u1ec7u cache",
        "PnL da co gia von": "PnL \u0111\u00e3 c\u00f3 gi\u00e1 v\u1ed1n",
        "So luong": "S\u1ed1 l\u01b0\u1ee3ng",
        "Ti gia hien tai": "T\u1ec9 gi\u00e1 hi\u1ec7n t\u1ea1i",
        "Xu huong": "Xu h\u01b0\u1edbng",
        "Thanh khoan": "Thanh kho\u1ea3n",
        "Bien dong": "Bi\u1ebfn \u0111\u1ed9ng",
        "Ho tro": "H\u1ed7 tr\u1ee3",
        "Khang cu": "Kh\u00e1ng c\u1ef1",
        "Ty trong": "T\u1ef7 tr\u1ecdng",
        "Hanh dong rule": "H\u00e0nh \u0111\u1ed9ng rule",
        "Hanh dong cuoi": "H\u00e0nh \u0111\u1ed9ng cu\u1ed1i",
        "Ty le de xuat": "T\u1ef7 l\u1ec7 \u0111\u1ec1 xu\u1ea5t",
        "Trang thai phe duyet": "Tr\u1ea1ng th\u00e1i ph\u00ea duy\u1ec7t",
        "Ly do": "L\u00fd do",
        "Gia tri": "Gi\u00e1 tr\u1ecb",
        "chua co gia von": "ch\u01b0a c\u00f3 gi\u00e1 v\u1ed1n",
        "khong goi AI": "kh\u00f4ng g\u1ecdi AI",
        "GIU": "GI\u1eee",
        "GIU VA THEO DOI": "GI\u1eee V\u00c0 THEO D\u00d5I",
        "CAN NHAC MUA THEM": "C\u00c2N NH\u1eaeC MUA TH\u00caM",
        "CHOT LOI MOT PHAN": "CH\u1ed0T L\u1edcI M\u1ed8T PH\u1ea6N",
        "CHOT LOI TOAN BO": "CH\u1ed0T L\u1edcI TO\u00c0N B\u1ed8",
        "CANH BAO RUI RO CAO": "C\u1ea2NH B\u00c1O R\u1ee6I RO CAO",
        "icon_success": "\u2705",
        "icon_menu": "\U0001f9ed",
        "icon_history": "\U0001f4da",
        "icon_wallet": "\U0001f4bc",
        "icon_guard": "\U0001f6e1\ufe0f",
        "icon_pair": "\U0001f4cc",
        "icon_time": "\U0001f552",
        "icon_money": "\U0001f4b0",
        "icon_price": "\U0001f4c8",
        "icon_coin": "\U0001fa99",
        "icon_order": "\U0001f9fe",
        "icon_mode": "\U0001f512",
        "Diem": "\u0110i\u1ec3m",
        "Het han": "H\u1ebft h\u1ea1n",
    }
    return translations[text]

def _format_shortlist_item(item: dict) -> str:
    return (
        f"{_u('icon_coin')} {item.get('symbol')}\n"
        f"{_u('Ly do')}: {item.get('reason')}\n"
        f"{_u('Diem')}: {_format_number(item.get('score'), 5)}\n"
        f"{_u('Het han')}: {_format_local_time(item.get('expires_at'))}"
    )
