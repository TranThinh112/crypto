from __future__ import annotations

from datetime import datetime, timezone

from spot_ai_bot.config import Settings
from spot_ai_bot.db import active_shortlist_entries, insert_doc, is_trade_snoozed, upsert_doc
from spot_ai_bot.okx_market import scan_okx_public
from spot_ai_bot.telegram import TelegramNotifier
from spot_ai_bot.trade_thesis import build_trade_thesis


async def run_watchlist_care(settings: Settings) -> dict:
    items = await active_shortlist_entries()
    if not items:
        return {"created_at": datetime.now(timezone.utc), "count": 0, "events": []}

    symbols = [item.get("exchange_symbol") or item.get("symbol") for item in items if item.get("symbol")]
    candidates = await scan_okx_public(symbols) if symbols else []
    item_map = {_normalize(item.get("symbol")): item for item in items}
    events = []
    notifier = TelegramNotifier(settings)

    for candidate in candidates:
        item = item_map.get(_normalize(candidate.symbol), {})
        thesis = build_trade_thesis(settings, candidate, item)
        previous = await _previous_thesis(candidate.symbol)
        thesis["version"] = int((previous or {}).get("version") or 0) + 1
        await upsert_doc("trade_theses", {"symbol": candidate.symbol, "status": {"$ne": "closed"}}, thesis)
        await insert_doc("trade_thesis_versions", thesis.copy())
        event = _care_event(thesis, previous)
        await insert_doc("watchlist_care_events", event)
        event.pop("_id", None)
        events.append(event)
        if _should_alert(event) and not await is_trade_snoozed(candidate.symbol):
            await notifier.watchlist_care_alert(event)

    return {"created_at": datetime.now(timezone.utc), "count": len(events), "events": events}


async def _previous_thesis(symbol: str) -> dict | None:
    from spot_ai_bot.db import mongo

    if mongo.db is None:
        return None
    return await mongo.db["trade_theses"].find_one({"symbol": symbol, "status": {"$ne": "closed"}})


def _care_event(thesis: dict, previous: dict | None) -> dict:
    previous_status = previous.get("status") if previous else None
    status = thesis.get("status")
    return {
        "created_at": datetime.now(timezone.utc),
        "symbol": thesis.get("symbol"),
        "status": status,
        "previous_status": previous_status,
        "changed": previous_status != status,
        "status_reason": thesis.get("status_reason"),
        "price_usdt": thesis.get("current_price_usdt"),
        "trend_score": thesis.get("trend_score"),
        "liquidity_score": thesis.get("liquidity_score"),
        "volatility_score": thesis.get("volatility_score"),
        "buy_zone": thesis.get("buy_zone"),
        "invalidation_price_usdt": thesis.get("invalidation_price_usdt"),
        "take_profit_zones_usdt": thesis.get("take_profit_zones_usdt"),
    }


def _should_alert(event: dict) -> bool:
    return bool(event.get("changed") and event.get("status") in {"buy_zone", "invalidated"})


def _normalize(symbol: str | None) -> str:
    return str(symbol or "").replace("-", "").replace("/", "").upper()
