from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ReturnDocument
from datetime import datetime, timezone, timedelta

from spot_ai_bot.config import Settings


class Mongo:
    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None


mongo = Mongo()


async def connect_mongo(settings: Settings) -> None:
    if not settings.mongodb_uri:
        return
    mongo.client = AsyncIOMotorClient(settings.mongodb_uri)
    mongo.db = mongo.client[settings.mongodb_database]
    await mongo.db.command("ping")
    await ensure_indexes(settings)


async def close_mongo() -> None:
    if mongo.client:
        mongo.client.close()


async def insert_doc(collection: str, doc: dict) -> None:
    if mongo.db is not None:
        await mongo.db[collection].insert_one(doc)

async def latest_docs(collection: str, limit: int = 5) -> list[dict]:
    if mongo.db is None:
        return []
    cursor = mongo.db[collection].find({}).sort("created_at", -1).limit(limit)
    return await cursor.to_list(length=limit)

async def all_docs(collection: str, limit: int = 1000) -> list[dict]:
    if mongo.db is None:
        return []
    cursor = mongo.db[collection].find({}).sort("created_at", -1).limit(limit)
    return await cursor.to_list(length=limit)

async def upsert_doc(collection: str, filter_doc: dict, payload: dict) -> None:
    if mongo.db is not None:
        await mongo.db[collection].update_one(filter_doc, {"$set": payload}, upsert=True)

async def next_buy_sequence(symbol: str) -> dict | None:
    if mongo.db is None:
        return None
    symbol = symbol.upper()
    existing = await mongo.db["buy_counters"].find_one({"symbol": symbol})
    if existing:
        result = await mongo.db["buy_counters"].find_one_and_update(
            {"symbol": symbol},
            {"$inc": {"sub_count": 1}},
            return_document=ReturnDocument.AFTER,
        )
        return {
            "main": result["main"],
            "sub": result["sub_count"],
            "label": f"#{result['main']}.{result['sub_count']}",
        }
    counter = await mongo.db["buy_counters"].find_one_and_update(
        {"_id": "global"},
        {"$inc": {"next_main": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    main = counter["next_main"]
    await mongo.db["buy_counters"].insert_one({"symbol": symbol, "main": main, "sub_count": 0})
    return {"main": main, "sub": 0, "label": f"#{main}"}

async def active_shortlist_symbols(limit: int = 1000) -> list[str]:
    if mongo.db is None:
        return []
    now = datetime.now(timezone.utc)
    cursor = (
        mongo.db["market_shortlist"]
        .find({"expires_at": {"$gt": now}})
        .sort([("score", -1), ("created_at", -1)])
        .limit(limit)
    )
    items = await cursor.to_list(length=limit)
    symbols: list[str] = []
    for item in items:
        symbol = str(item.get("symbol") or "").upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols

async def active_shortlist_entries(limit: int = 1000) -> list[dict]:
    if mongo.db is None:
        return []
    now = datetime.now(timezone.utc)
    cursor = (
        mongo.db["market_shortlist"]
        .find({"expires_at": {"$gt": now}})
        .sort([("score", -1), ("updated_at", -1)])
        .limit(limit)
    )
    return await cursor.to_list(length=limit)

async def trade_ready_shortlist_entries(settings: Settings, limit: int = 1000) -> list[dict]:
    if mongo.db is None:
        return []
    now = datetime.now(timezone.utc)
    min_age = now - timedelta(minutes=max(0, settings.shortlist_min_age_minutes_for_trade))
    min_observations = max(1, int(settings.shortlist_min_observations_for_trade))
    cursor = (
        mongo.db["market_shortlist"]
        .find(
            {
                "expires_at": {"$gt": now},
                "$or": [
                    {"observation_count": {"$gte": min_observations}},
                    {"created_at": {"$lte": min_age}},
                ],
            }
        )
        .sort([("score", -1), ("updated_at", -1)])
        .limit(limit)
    )
    return await cursor.to_list(length=limit)

async def latest_trade_decision(symbol: str) -> dict | None:
    if mongo.db is None:
        return None
    return await mongo.db["telegram_trade_decisions"].find_one(
        {"symbol": symbol.upper()},
        sort=[("created_at", -1)],
    )

async def is_trade_snoozed(symbol: str) -> bool:
    decision = await latest_trade_decision(symbol)
    if not decision:
        return False
    snooze_until = decision.get("snooze_until")
    if not snooze_until:
        return False
    if snooze_until.tzinfo is None:
        snooze_until = snooze_until.replace(tzinfo=timezone.utc)
    return snooze_until > datetime.now(timezone.utc)

async def approved_trade_symbols() -> set[str]:
    if mongo.db is None:
        return set()
    cursor = mongo.db["telegram_trade_decisions"].find({"action": "approve_buy"}).sort("created_at", -1).limit(200)
    items = await cursor.to_list(length=200)
    approved: set[str] = set()
    rejected: set[str] = set()
    for item in items:
        symbol = str(item.get("symbol") or "").upper()
        action = str(item.get("action") or "")
        if not symbol or symbol in approved or symbol in rejected:
            continue
        if action == "approve_buy":
            approved.add(symbol)
        elif action in {"reject", "watch_only"}:
            rejected.add(symbol)
    return approved

async def upsert_shortlist_entries(settings: Settings, candidates: list[dict]) -> int:
    if mongo.db is None:
        return 0
    now = datetime.now(timezone.utc)
    ttl_hours = max(1, int(settings.market_scan_shortlist_ttl_hours))
    expires_at = now + timedelta(hours=ttl_hours)
    count = 0
    for candidate in candidates:
        metadata = candidate.get("metadata") or {}
        symbol = str(candidate.get("symbol") or "").upper()
        if not symbol or not metadata.get("shortlist_candidate"):
            continue
        score = float(metadata.get("shortlist_score") or 0)
        existing = await mongo.db["market_shortlist"].find_one(
            {"symbol": symbol, "exchange": str(metadata.get("exchange") or settings.exchange_name)}
        )
        created_at = existing.get("created_at") if existing else now
        first_seen_at = existing.get("first_seen_at") if existing else now
        observation_count = int(existing.get("observation_count") or 0) + 1 if existing else 1
        payload = {
            "created_at": created_at,
            "first_seen_at": first_seen_at,
            "updated_at": now,
            "expires_at": expires_at,
            "observation_count": observation_count,
            "symbol": symbol,
            "exchange": str(metadata.get("exchange") or settings.exchange_name),
            "exchange_symbol": str(metadata.get("exchange_symbol") or symbol),
            "reason": str(metadata.get("shortlist_reason") or "noteworthy_market_move"),
            "score": score,
            "data_source": str(metadata.get("data_source") or "live"),
            "trend_score": candidate.get("trend_score"),
            "liquidity_score": candidate.get("liquidity_score"),
            "volatility_score": candidate.get("volatility_score"),
            "quote_volume": metadata.get("quote_volume"),
            "change_pct": metadata.get("change_pct"),
            "scan_mode": metadata.get("scan_mode"),
        }
        await mongo.db["market_shortlist"].update_one(
            {"symbol": symbol, "exchange": payload["exchange"]},
            {"$set": payload},
            upsert=True,
        )
        count += 1
    return count

async def ensure_indexes(settings: Settings) -> None:
    if mongo.db is None:
        return
    ttl_seconds = max(1, settings.market_scan_ttl_days) * 24 * 60 * 60
    await mongo.db["market_scans"].create_index("created_at", expireAfterSeconds=ttl_seconds)
    await mongo.db["market_scans"].create_index([("stored_reason", 1), ("created_at", -1)])
    await mongo.db["trade_proposals"].create_index("created_at")
    await mongo.db["buy_history"].create_index("created_at")
    await mongo.db["buy_history"].create_index([("symbol", 1), ("created_at", -1)])
    await mongo.db["held_asset_summaries"].create_index("created_at")
    await mongo.db["position_management_proposals"].create_index("created_at")
    await mongo.db["position_management_proposals"].create_index([("symbol", 1), ("created_at", -1)])
    await mongo.db["position_approvals"].create_index("symbol")
    await mongo.db["advisor_opinions"].create_index("symbol")
    await mongo.db["trade_theses"].create_index([("symbol", 1), ("status", 1)])
    await mongo.db["trade_thesis_versions"].create_index([("symbol", 1), ("version", -1)])
    await mongo.db["watchlist_care_events"].create_index("created_at")
    await mongo.db["telegram_trade_decisions"].create_index([("symbol", 1), ("created_at", -1)])
    await mongo.db["telegram_trade_decisions"].create_index("snooze_until")
    await mongo.db["buy_counters"].create_index("symbol", unique=True, sparse=True)
    shortlist_ttl_seconds = max(1, int(settings.market_scan_shortlist_ttl_hours)) * 60 * 60
    await mongo.db["market_shortlist"].create_index("expires_at", expireAfterSeconds=shortlist_ttl_seconds)
    await mongo.db["market_shortlist"].create_index([("score", -1), ("updated_at", -1)])
    await mongo.db["market_shortlist"].create_index([("observation_count", -1), ("created_at", 1)])
