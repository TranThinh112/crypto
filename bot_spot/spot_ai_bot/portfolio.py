from collections import defaultdict
from datetime import datetime, timezone

from spot_ai_bot.config import Settings
from spot_ai_bot.db import all_docs
from spot_ai_bot.okx_market import okx_spot_last_prices
from spot_ai_bot.okx_private import okx_funding_balances, okx_trading_cash_balances

MIN_DISPLAY_VALUE_USDT = 0.005
PORTFOLIO_CACHE_SECONDS = 15
_CACHE = {"expires_at": 0.0, "data": None}


async def spot_portfolio(settings: Settings) -> dict:
    now = datetime.now(timezone.utc).timestamp()
    if _CACHE["data"] and now < _CACHE["expires_at"]:
        data = dict(_CACHE["data"])
        data["cache_hit"] = True
        return data

    funding = await okx_funding_balances(settings)
    trading = await okx_trading_cash_balances(settings)
    prices = await okx_spot_last_prices()
    quantities = defaultdict(float)

    for item in funding.get("balances", []):
        asset = str(item.get("asset") or "").upper()
        if asset:
            quantities[asset] += float(item.get("balance") or item.get("available_balance") or 0)

    for item in trading.get("balances", []):
        asset = str(item.get("asset") or "").upper()
        if asset:
            quantities[asset] += float(item.get("cash_balance") or item.get("available_balance") or 0)

    costs = _cost_basis(await all_docs("buy_history", limit=1000))
    assets = []
    spot_capital_usdt = quantities.get("USDT", 0.0)
    total_value = 0.0
    total_cost = 0.0
    total_pnl = 0.0

    for asset, quantity in sorted(quantities.items()):
        if quantity <= 0:
            continue
        price = 1.0 if asset in {"USDT", "USD", "USDC"} else prices.get(f"{asset}-USDT")
        value_usdt = quantity * price if price is not None else None
        if value_usdt is None or value_usdt < MIN_DISPLAY_VALUE_USDT:
            continue
        cost = costs.get(asset)
        pnl_usdt = None
        pnl_pct = None
        tracked_quantity = None
        if cost and value_usdt is not None:
            tracked_quantity = min(quantity, cost["quantity"])
            held_cost = cost["avg_price"] * tracked_quantity
            tracked_value = price * tracked_quantity
            pnl_usdt = tracked_value - held_cost
            pnl_pct = (pnl_usdt / held_cost * 100) if held_cost else None
            total_cost += held_cost
            total_pnl += pnl_usdt
        if value_usdt is not None:
            total_value += value_usdt
        assets.append(
            {
                "asset": asset,
                "quantity": quantity,
                "price_usdt": price,
                "value_usdt": value_usdt,
                "avg_cost_usdt": cost["avg_price"] if cost else None,
                "tracked_quantity": tracked_quantity,
                "pnl_usdt": pnl_usdt,
                "pnl_pct": pnl_pct,
            }
        )

    data = {
        "source": "OKX funding + trading cash spot-safe",
        "assets": assets,
        "spot_capital_usdt": spot_capital_usdt,
        "total_value_usdt": total_value,
        "known_cost_usdt": total_cost,
        "known_pnl_usdt": total_pnl,
        "cache_hit": False,
        "cache_seconds": PORTFOLIO_CACHE_SECONDS,
    }
    _CACHE["data"] = data
    _CACHE["expires_at"] = now + PORTFOLIO_CACHE_SECONDS
    return data


def _cost_basis(history: list[dict]) -> dict:
    totals = defaultdict(lambda: {"qty": 0.0, "cost": 0.0})
    for item in history:
        symbol = str(item.get("symbol") or "").replace("-", "").replace("/", "").upper()
        asset = symbol[:-4] if symbol.endswith("USDT") else symbol
        qty = _to_float(item.get("quantity"))
        cost = _to_float(item.get("filled_notional_usd") or item.get("amount_usd"))
        if asset and qty > 0 and cost > 0:
            totals[asset]["qty"] += qty
            totals[asset]["cost"] += cost
    return {
        asset: {
            "avg_price": values["cost"] / values["qty"],
            "quantity": values["qty"],
            "cost": values["cost"],
        }
        for asset, values in totals.items()
        if values["qty"] > 0
    }


def _to_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
