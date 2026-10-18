import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone

import httpx

from spot_ai_bot.config import Settings


async def verify_okx_private(settings: Settings) -> dict:
    if not settings.okx_api_key or not settings.okx_secret or not settings.okx_passphrase:
        return {"connected": False, "code": "missing_config", "message": "OKX private credentials are incomplete."}

    payload = await okx_private_get(settings, "/api/v5/account/balance")
    code = payload.get("code")
    return {
        "connected": code == "0",
        "code": code,
        "message": payload.get("msg") or "",
        "data_items": len(payload.get("data") or []),
    }


async def okx_spot_balances(settings: Settings) -> dict:
    return await okx_funding_balances(settings)

async def okx_trading_cash_balances(settings: Settings) -> dict:
    payload = await okx_private_get(settings, "/api/v5/account/balance")
    code = payload.get("code")
    data = payload.get("data") or []
    details = data[0].get("details", []) if data else []
    balances = []
    for item in details:
        cash_balance = _to_float(item.get("cashBal"))
        available = _to_float(item.get("availBal") or item.get("availEq"))
        usd_value = _to_float(item.get("eqUsd"))
        if cash_balance or available:
            balances.append(
                {
                    "asset": item.get("ccy"),
                    "cash_balance": cash_balance,
                    "available_balance": available,
                    "usd_value": usd_value,
                }
            )
    return {
        "connected": code == "0",
        "code": code,
        "message": payload.get("msg") or "",
        "account_scope": "okx_trading_account_cash_balances_for_spot",
        "uses_positions": False,
        "uses_funding": False,
        "uses_unified_equity_as_capital": False,
        "safe_for_spot_capital": True,
        "order_mode": "tdMode=cash",
        "balances": balances,
    }

async def okx_trading_account_balances(settings: Settings) -> dict:
    payload = await okx_private_get(settings, "/api/v5/account/balance")
    code = payload.get("code")
    data = payload.get("data") or []
    details = data[0].get("details", []) if data else []
    balances = []
    for item in details:
        cash_balance = _to_float(item.get("cashBal"))
        available = _to_float(item.get("availBal") or item.get("availEq"))
        equity = _to_float(item.get("eq"))
        usd_value = _to_float(item.get("eqUsd"))
        if cash_balance or available or equity:
            balances.append(
                {
                    "asset": item.get("ccy"),
                    "cash_balance": cash_balance,
                    "available_balance": available,
                    "equity": equity,
                    "usd_value": usd_value,
                }
            )
    return {
        "connected": code == "0",
        "code": code,
        "message": payload.get("msg") or "",
        "account_scope": "okx_trading_unified_account_debug_only",
        "uses_positions": False,
        "uses_funding": False,
        "safe_for_spot_capital": False,
        "balances": balances,
    }

async def okx_funding_balances(settings: Settings) -> dict:
    payload = await okx_private_get(settings, "/api/v5/asset/balances")
    code = payload.get("code")
    data = payload.get("data") or []
    balances = []
    for item in data:
        balance = _to_float(item.get("bal"))
        available = _to_float(item.get("availBal") or item.get("bal"))
        frozen = _to_float(item.get("frozenBal"))
        if balance or available or frozen:
            balances.append(
                {
                    "asset": item.get("ccy"),
                    "balance": balance,
                    "available_balance": available,
                    "frozen_balance": frozen,
                }
            )
    return {
        "connected": code == "0",
        "code": code,
        "message": payload.get("msg") or "",
        "account_scope": "okx_funding_account_spot_wallet",
        "uses_positions": False,
        "uses_trading_unified_equity": False,
        "safe_for_spot_capital": True,
        "tradable_without_transfer": False,
        "balances": balances,
    }

async def okx_funding_available(settings: Settings, asset: str) -> float:
    balances = await okx_funding_balances(settings)
    for item in balances.get("balances", []):
        if item.get("asset") == asset:
            return float(item.get("available_balance") or 0)
    return 0.0


async def okx_private_get(settings: Settings, path: str) -> dict:
    return await okx_private_request(settings, "GET", path)

async def okx_private_post(settings: Settings, path: str, body: dict) -> dict:
    return await okx_private_request(settings, "POST", path, body)

async def okx_private_request(settings: Settings, method: str, path: str, body: dict | None = None) -> dict:
    if not settings.okx_api_key or not settings.okx_secret or not settings.okx_passphrase:
        return {"code": "missing_config", "msg": "OKX private credentials are incomplete.", "data": []}

    body_text = json.dumps(body, separators=(",", ":")) if body else ""
    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    message = f"{timestamp}{method}{path}{body_text}"
    signature = base64.b64encode(
        hmac.new(settings.okx_secret.encode(), message.encode(), hashlib.sha256).digest()
    ).decode()
    headers = {
        "OK-ACCESS-KEY": settings.okx_api_key,
        "OK-ACCESS-SIGN": signature,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": settings.okx_passphrase,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        if method == "POST":
            response = await client.post(f"https://www.okx.com{path}", headers=headers, content=body_text)
        else:
            response = await client.get(f"https://www.okx.com{path}", headers=headers)
    response.raise_for_status()
    return response.json()

async def okx_transfer_funding_to_trading(settings: Settings, asset: str, amount: float) -> dict:
    return await okx_transfer(settings, asset, amount, "6", "18")

async def okx_transfer_trading_to_funding(settings: Settings, asset: str, amount: float) -> dict:
    return await okx_transfer(settings, asset, amount, "18", "6")

async def okx_transfer(settings: Settings, asset: str, amount: float, from_account: str, to_account: str) -> dict:
    return await okx_private_post(
        settings,
        "/api/v5/asset/transfer",
        {
            "ccy": asset,
            "amt": _format_decimal(amount),
            "from": from_account,
            "to": to_account,
        },
    )

async def okx_spot_market_buy_quote(settings: Settings, inst_id: str, quote_amount: float) -> dict:
    return await okx_private_post(
        settings,
        "/api/v5/trade/order",
        {
            "instId": inst_id,
            "tdMode": "cash",
            "side": "buy",
            "ordType": "market",
            "sz": _format_decimal(quote_amount),
            "tgtCcy": "quote_ccy",
        },
    )

async def okx_order_detail(settings: Settings, inst_id: str, order_id: str) -> dict:
    return await okx_private_get(settings, f"/api/v5/trade/order?instId={inst_id}&ordId={order_id}")


def _to_float(value: str | None) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0

def _format_decimal(value: float) -> str:
    return f"{value:.12f}".rstrip("0").rstrip(".")
