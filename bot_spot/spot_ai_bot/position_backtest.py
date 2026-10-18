import httpx

from spot_ai_bot.config import Settings
from spot_ai_bot.position_manager import STABLE_ASSETS
from spot_ai_bot.portfolio import spot_portfolio


async def backtest_positions(settings: Settings, bar: str = "4H", limit: int = 120) -> dict:
    portfolio = await spot_portfolio(settings)
    assets = [item for item in portfolio.get("assets", []) if item.get("asset") not in STABLE_ASSETS]
    results = []
    async with httpx.AsyncClient(base_url="https://www.okx.com", timeout=20) as client:
        for asset in assets:
            inst_id = f"{asset['asset']}-USDT"
            response = await client.get("/api/v5/market/candles", params={"instId": inst_id, "bar": bar, "limit": str(limit)})
            response.raise_for_status()
            candles = list(reversed(response.json().get("data") or []))
            closes = [float(candle[4]) for candle in candles if candle[4]]
            if len(closes) < 10:
                continue
            results.append(_simulate_asset(settings, asset["asset"], closes))
    return {
        "bar": bar,
        "limit": limit,
        "asset_count": len(results),
        "results": results,
    }


def _simulate_asset(settings: Settings, asset: str, closes: list[float]) -> dict:
    actions = {"HOLD": 0, "WATCH": 0, "TAKE_PROFIT_PARTIAL": 0, "HIGH_RISK_ALERT": 0}
    start = closes[0]
    peak = start
    max_drawdown_pct = 0.0
    for price in closes:
        peak = max(peak, price)
        pnl_pct = ((price - start) / start * 100) if start else 0
        drawdown_pct = ((price - peak) / peak * 100) if peak else 0
        max_drawdown_pct = min(max_drawdown_pct, drawdown_pct)
        if pnl_pct >= settings.held_asset_take_profit_partial_pct and drawdown_pct <= -3:
            actions["TAKE_PROFIT_PARTIAL"] += 1
        elif pnl_pct <= settings.held_asset_high_risk_loss_pct:
            actions["WATCH"] += 1
        elif pnl_pct <= settings.held_asset_exit_loss_pct and drawdown_pct <= -20:
            actions["HIGH_RISK_ALERT"] += 1
        else:
            actions["HOLD"] += 1
    return {
        "asset": asset,
        "start_price": start,
        "end_price": closes[-1],
        "pnl_pct": ((closes[-1] - start) / start * 100) if start else 0,
        "max_drawdown_pct": max_drawdown_pct,
        "actions": actions,
        "holder_first_note": "Backtest chi danh gia rule; khong thuc thi lenh.",
    }
