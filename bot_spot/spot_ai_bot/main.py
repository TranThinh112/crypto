import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import Body, FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from spot_ai_bot.ai import AIAdvisor
from spot_ai_bot.config import get_settings
from spot_ai_bot.db import (
    active_shortlist_entries,
    approved_trade_symbols,
    close_mongo,
    connect_mongo,
    insert_doc,
    latest_docs,
    trade_ready_shortlist_entries,
    upsert_shortlist_entries,
    upsert_doc,
)
from spot_ai_bot.execution import LiveExecution, PaperExecution
from spot_ai_bot.market_data import scan_market
from spot_ai_bot.okx_private import okx_spot_balances, okx_trading_account_balances, verify_okx_private
from spot_ai_bot.position_backtest import backtest_positions
from spot_ai_bot.position_manager import evaluate_positions
from spot_ai_bot.portfolio import spot_portfolio
from spot_ai_bot.risk import RiskEngine
from spot_ai_bot.scheduler import create_scheduler
from spot_ai_bot.strategy import RuleStrategy
from spot_ai_bot.telegram import TelegramNotifier
from spot_ai_bot.trade_thesis import build_trade_thesis
from spot_ai_bot.watchlist_care import run_watchlist_care

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_mongo(settings)
    try:
        await TelegramNotifier(settings).set_commands()
    except Exception:
        pass
    telegram_poll_task = None
    if settings.telegram_bot_token and settings.telegram_chat_id:
        telegram_poll_task = asyncio.create_task(_telegram_poll_loop())
    scheduler = create_scheduler(settings)
    scheduler.start()
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        if telegram_poll_task:
            telegram_poll_task.cancel()
        scheduler.shutdown(wait=False)
        await close_mongo()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="spot_ai_bot/static"), name="static")


@app.get("/", include_in_schema=False)
async def dashboard() -> FileResponse:
    return FileResponse("spot_ai_bot/static/index.html")


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "env": settings.app_env,
        "model": settings.openai_model,
        "paper_trading": settings.paper_trading_enabled,
        "live_trading": settings.live_trading_enabled,
        "exchange": settings.exchange_name,
    }


@app.get("/config/summary")
async def config_summary() -> dict:
    return {
        "budget_usd": settings.user_total_budget_usd,
        "approval_required": settings.telegram_approval_required,
        "mongodb_configured": bool(settings.mongodb_uri),
        "openai_configured": bool(settings.openai_api_key),
        "gpt_5_4_manager_configured": bool(settings.gpt_5_4_manager_api_key or settings.openai_api_key),
        "gpt_crypto_configured": bool(settings.gpt_crypto_api_key or settings.openai_api_key),
        "gpt_fork_configured": bool(settings.gpt_fork_api_key or settings.openai_api_key),
        "gpt_5_4_manager_enabled": settings.gpt_5_4_manager_enabled,
        "gpt_crypto_enabled": settings.gpt_crypto_enabled,
        "gpt_fork_enabled": settings.gpt_fork_enabled,
        "telegram_configured": bool(settings.telegram_bot_token and settings.telegram_chat_id),
        "telegram_notify_scans": settings.telegram_notify_scans,
        "telegram_top_scan_report_enabled": settings.telegram_top_scan_report_enabled,
        "telegram_message_thread_configured": bool(settings.telegram_message_thread_id),
        "exchange_configured": bool(settings.okx_api_key and settings.okx_secret),
        "okx_passphrase_configured": bool(settings.okx_passphrase),
        "market_symbols": settings.market_symbols,
        "max_live_trade_usd": settings.max_live_trade_usd,
        "min_new_trade_capital_usdt": settings.min_new_trade_capital_usdt,
        "spot_only_trading": settings.spot_only_trading,
        "auto_scan_enabled": settings.auto_scan_enabled,
        "scan_interval_seconds": settings.scan_interval_seconds,
        "signal_trend_threshold": settings.signal_trend_threshold,
        "signal_liquidity_threshold": settings.signal_liquidity_threshold,
        "signal_max_volatility": settings.signal_max_volatility,
        "store_all_scans": settings.store_all_scans,
        "scan_heartbeat_store_interval": settings.scan_heartbeat_store_interval,
        "market_scan_ttl_days": settings.market_scan_ttl_days,
        "market_scan_shortlist_ttl_hours": settings.market_scan_shortlist_ttl_hours,
        "shortlist_min_observations_for_trade": settings.shortlist_min_observations_for_trade,
        "shortlist_min_age_minutes_for_trade": settings.shortlist_min_age_minutes_for_trade,
        "watchlist_care_enabled": settings.watchlist_care_enabled,
        "watchlist_care_interval_seconds": settings.watchlist_care_interval_seconds,
        "market_regime_enabled": settings.market_regime_enabled,
        "market_regime_symbols": settings.market_regime_symbols,
        "market_regime_min_trend": settings.market_regime_min_trend,
        "market_regime_min_liquidity": settings.market_regime_min_liquidity,
        "anti_pump_max_24h_change_pct": settings.anti_pump_max_24h_change_pct,
        "anti_pump_near_resistance_pct": settings.anti_pump_near_resistance_pct,
        "buy_zone_support_buffer_pct": settings.buy_zone_support_buffer_pct,
        "buy_zone_breakout_buffer_pct": settings.buy_zone_breakout_buffer_pct,
        "risk_per_trade_pct_of_budget": settings.risk_per_trade_pct_of_budget,
        "min_proposal_amount_usd": settings.min_proposal_amount_usd,
        "held_asset_summary_enabled": settings.held_asset_summary_enabled,
        "held_asset_summary_interval_seconds": settings.held_asset_summary_interval_seconds,
        "held_asset_strong_move_pct": settings.held_asset_strong_move_pct,
        "held_asset_take_profit_partial_pct": settings.held_asset_take_profit_partial_pct,
        "held_asset_take_profit_full_pct": settings.held_asset_take_profit_full_pct,
        "held_asset_high_risk_loss_pct": settings.held_asset_high_risk_loss_pct,
        "held_asset_exit_loss_pct": settings.held_asset_exit_loss_pct,
        "position_ai_min_confidence": settings.position_ai_min_confidence,
        "position_max_asset_weight_pct": settings.position_max_asset_weight_pct,
        "position_add_cooldown_hours": settings.position_add_cooldown_hours,
        "position_partial_take_profit_pct": settings.position_partial_take_profit_pct,
        "position_full_take_profit_pct": settings.position_full_take_profit_pct,
        "position_execution_requires_approval": settings.position_execution_requires_approval,
    }


@app.get("/dashboard/state")
async def dashboard_state() -> dict:
    return {
        "health": await health(),
        "config": await config_summary(),
        "actions": {
            "scan_market": "/market/scan",
            "shortlist": "/market/shortlist",
            "run_once": "/run-once",
            "api_docs": "/docs",
        },
    }

@app.get("/scheduler/jobs")
async def scheduler_jobs() -> dict:
    scheduler = app.state.scheduler
    return {
        "jobs": [
            {
                "id": job.id,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            }
            for job in scheduler.get_jobs()
        ]
    }


@app.get("/market/scan")
async def market_scan() -> dict:
    candidates = await scan_market(settings)
    data_source = candidates[0].metadata.get("data_source", "unknown") if candidates else "empty"
    fallback_reason = candidates[0].metadata.get("fallback_reason") if candidates else None
    latest_scan = await latest_docs("market_scans", limit=1)
    last_scan_at = latest_scan[0].get("created_at").isoformat() if latest_scan else None
    return {
        "candidate_count": len(candidates),
        "data_source": data_source,
        "fallback_reason": fallback_reason,
        "exchange": settings.exchange_name,
        "last_scan_at": last_scan_at,
        "candidates": candidates,
    }

@app.get("/market/shortlist")
async def market_shortlist() -> dict:
    items = await active_shortlist_entries()
    cleaned_items = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for index, item in enumerate(items, start=1):
        created_at = item.get("created_at")
        updated_at = item.get("updated_at")
        expires_at = item.get("expires_at")
        readiness = _watchlist_readiness(settings, item, now)
        cleaned_items.append(
            {
                "priority": index,
                "symbol": item.get("symbol"),
                "exchange_symbol": item.get("exchange_symbol"),
                "score": item.get("score"),
                "reason": item.get("reason"),
                "change_pct": item.get("change_pct"),
                "observation_count": item.get("observation_count", 1),
                "trade_ready": readiness["trade_ready"],
                "readiness_reason": readiness["reason"],
                "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
                "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else updated_at,
                "expires_at": expires_at.isoformat() if hasattr(expires_at, "isoformat") else expires_at,
            }
        )
    return {"count": len(cleaned_items), "items": cleaned_items}

@app.get("/watchlist/theses")
async def watchlist_theses() -> dict:
    from spot_ai_bot.db import mongo

    if mongo.db is None:
        return {"count": 0, "items": []}
    items = await mongo.db["trade_theses"].find({}).sort("updated_at", -1).limit(50).to_list(length=50)
    for item in items:
        item.pop("_id", None)
    return {"count": len(items), "items": items}

@app.post("/watchlist/care")
async def watchlist_care() -> dict:
    return await run_watchlist_care(settings)

@app.get("/reviews/weekly")
async def weekly_review() -> dict:
    from datetime import timedelta
    from spot_ai_bot.db import mongo

    if mongo.db is None:
        return {"ok": False, "reason": "mongodb_not_configured"}
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    proposals = await mongo.db["trade_proposals"].find({"created_at": {"$gte": since}}).to_list(length=500)
    care_events = await mongo.db["watchlist_care_events"].find({"created_at": {"$gte": since}}).to_list(length=1000)
    decisions = await mongo.db["telegram_trade_decisions"].find({"created_at": {"$gte": since}}).to_list(length=500)
    filled = [item for item in proposals if item.get("status") in {"paper_filled", "live_filled"}]
    blocked = [item for item in proposals if str(item.get("status") or "").startswith("rejected") or item.get("risk_notes")]
    return {
        "ok": True,
        "since": since.isoformat(),
        "proposal_count": len(proposals),
        "filled_count": len(filled),
        "blocked_count": len(blocked),
        "watchlist_care_event_count": len(care_events),
        "telegram_decision_count": len(decisions),
        "notes": [
            "Review checks proposal volume, blocked ideas, watchlist care activity, and Telegram decisions.",
            "Use this as weekly audit input before changing thresholds.",
        ],
    }

@app.get("/exchange/private-status")
async def exchange_private_status() -> dict:
    if settings.exchange_name.lower() != "okx":
        return {"connected": False, "code": "unsupported_exchange", "message": settings.exchange_name}
    return await verify_okx_private(settings)

@app.get("/account/spot-balances")
async def account_spot_balances() -> dict:
    if settings.exchange_name.lower() != "okx":
        return {"connected": False, "code": "unsupported_exchange", "message": settings.exchange_name}
    return await okx_spot_balances(settings)

@app.get("/account/trading-balances")
async def account_trading_balances() -> dict:
    if settings.exchange_name.lower() != "okx":
        return {"connected": False, "code": "unsupported_exchange", "message": settings.exchange_name}
    return await okx_trading_account_balances(settings)

@app.post("/telegram/update")
async def telegram_update(request: Request) -> dict:
    update = await request.json()
    await _handle_telegram_update(update)
    return {"ok": True}

@app.post("/telegram/register-menu")
async def telegram_register_menu() -> dict:
    result = await TelegramNotifier(settings).set_commands()
    return {"ok": bool(result and result.get("ok")), "result": result}

async def _handle_telegram_update(update: dict) -> None:
    if update.get("callback_query"):
        await _handle_telegram_callback(update["callback_query"])
        return
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    text = (message.get("text") or "").strip()
    if not _telegram_chat_allowed(str(chat.get("id") or "")):
        return
    if not text:
        return

    notifier = TelegramNotifier(settings)
    command = text.split()[0].split("@")[0].lower()
    if command in {"/menu", "/start"}:
        await notifier.menu()
    elif command in {"/lichsumua", "/lich_su_mua"} or text.split()[0] == "/LichSuMua":
        await notifier.buy_history(await latest_docs("buy_history", limit=10))
    elif command in {"/taisan", "/tai_san"}:
        await notifier.portfolio(await spot_portfolio(settings))
    elif command in {"/quanly", "/quan_ly"}:
        report = await evaluate_positions(settings, force_ai=True)
        await notifier.position_management(report)
    elif command == "/shortlist":
        await notifier.shortlist(await active_shortlist_entries())
    elif command == "/setup":
        await notifier.send_text("\u2699\ufe0f Setup: bot \u0111ang d\u00f9ng c\u1ea5u h\u00ecnh trong file .env.")
    elif command == "/guard":
        await notifier.send_text("\U0001f6e1\ufe0f Market Guard: bot ch\u1ec9 giao d\u1ecbch spot cash v\u00e0 kh\u00f4ng d\u00f9ng t\u00e0i kho\u1ea3n futures/unified l\u00e0m v\u1ed1n spot.")

async def _handle_telegram_callback(callback: dict) -> None:
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    if not _telegram_chat_allowed(str(chat.get("id") or "")):
        return
    data = str(callback.get("data") or "")
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "trade":
        return
    _, action, symbol = parts
    record = {
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
        "symbol": symbol.upper(),
        "action": action,
        "callback_id": callback.get("id"),
        "from_user": callback.get("from") or {},
        "execution_enabled": False,
        "message": "Telegram decision saved. Live execution remains locked.",
    }
    if action == "snooze_1h":
        from datetime import timedelta

        record["snooze_until"] = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
    await insert_doc("telegram_trade_decisions", record)
    await TelegramNotifier(settings).send_text(
        f"Da ghi nhan quyet dinh {action} cho {symbol.upper()}. Execution van dang khoa an toan."
    )

async def _telegram_poll_loop() -> None:
    offset = None
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates"
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            try:
                params = {"timeout": 20}
                if offset is not None:
                    params["offset"] = offset
                response = await client.get(url, params=params)
                payload = response.json()
                for update in payload.get("result", []):
                    offset = int(update["update_id"]) + 1
                    await _handle_telegram_update(update)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(5)


@app.post("/run-once")
async def run_once() -> dict:
    portfolio = await spot_portfolio(settings)
    spot_capital = float(portfolio.get("spot_capital_usdt") or 0)
    if spot_capital < settings.min_new_trade_capital_usdt:
        return {
            "skipped": True,
            "reason": "insufficient_spot_capital_for_new_trade",
            "spot_capital_usdt": spot_capital,
            "min_new_trade_capital_usdt": settings.min_new_trade_capital_usdt,
            "message": "Bot chi quan ly coin dang nam giu; khong scan tim coin moi va khong goi AI mua moi khi von spot khong du.",
        }

    advisor = AIAdvisor(settings)
    risk = RiskEngine()
    strategy = RuleStrategy(risk)
    paper = PaperExecution()
    live = LiveExecution(settings)
    telegram = TelegramNotifier(settings)

    allocation = await advisor.capital_allocation(settings.user_total_budget_usd)
    await insert_doc("allocations", allocation.model_dump(mode="json"))

    scanned_candidates = await scan_market(settings)
    await upsert_shortlist_entries(settings, [candidate.model_dump(mode="json") for candidate in scanned_candidates])
    trade_ready_symbols = {
        _normalize_symbol(item.get("symbol") or item.get("exchange_symbol"))
        for item in await trade_ready_shortlist_entries(settings)
    }
    trade_ready_items = {
        _normalize_symbol(item.get("symbol") or item.get("exchange_symbol")): item
        for item in await trade_ready_shortlist_entries(settings)
    }
    approved_symbols = await approved_trade_symbols()
    market_regime = _market_regime(settings, scanned_candidates)

    proposals = []
    skipped_candidates = []
    for candidate in scanned_candidates:
        if _normalize_symbol(candidate.symbol) not in trade_ready_symbols:
            skipped_candidates.append(
                {
                    "symbol": candidate.symbol,
                    "reason": "not_trade_ready_watchlist",
                    "detail": (
                        "Coin chua nam trong watchlist du so lan/du thoi gian; "
                        "khong goi AI va khong tao proposal mua."
                    ),
                }
            )
            continue
        if candidate.trend_score < settings.signal_trend_threshold or candidate.liquidity_score < settings.signal_liquidity_threshold:
            skipped_candidates.append(
                {
                    "symbol": candidate.symbol,
                    "reason": "signal_threshold_not_met",
                    "detail": (
                        "Coin da trade-ready trong watchlist nhung trend/liquidity "
                        "chua dat nguong mua; khong goi AI va khong tao proposal."
                    ),
                }
            )
            continue
        thesis = build_trade_thesis(settings, candidate, trade_ready_items.get(_normalize_symbol(candidate.symbol)))
        await upsert_doc("trade_theses", {"symbol": candidate.symbol, "status": {"$ne": "closed"}}, thesis)
        if thesis.get("status") != "buy_zone":
            skipped_candidates.append(
                {
                    "symbol": candidate.symbol,
                    "reason": f"not_in_buy_zone:{thesis.get('status')}",
                    "detail": thesis.get("status_reason") or "Trade thesis is not in buy zone.",
                }
            )
            continue
        if _normalize_symbol(candidate.symbol) not in approved_symbols:
            skipped_candidates.append(
                {
                    "symbol": candidate.symbol,
                    "reason": "waiting_for_telegram_approval",
                    "detail": "Coin da vao buy-zone nhung chua co Approve Buy tren Telegram.",
                }
            )
            continue
        opinion = await advisor.group_opinion(candidate)
        await insert_doc("advisor_opinions", opinion.model_dump(mode="json"))
        proposal = strategy.build_proposal(candidate, allocation, opinion, market_regime=market_regime)
        if not proposal:
            continue
        proposal.entry_plan = thesis
        proposal.amount_usd = _risk_based_amount(settings, candidate, allocation, thesis, proposal.amount_usd)
        if proposal.amount_usd < settings.min_proposal_amount_usd:
            skipped_candidates.append(
                {
                    "symbol": candidate.symbol,
                    "reason": "risk_size_too_small",
                    "detail": f"Risk-based size {proposal.amount_usd} below min proposal amount.",
                }
            )
            continue
        if settings.live_trading_enabled:
            proposal = await live.execute(proposal)
        elif settings.paper_trading_enabled:
            proposal = await paper.execute(proposal)
        await insert_doc("trade_proposals", proposal.model_dump(mode="json"))
        if proposal.status == "live_filled":
            await insert_doc("buy_history", proposal.model_dump(mode="json"))
        await telegram.proposal(proposal)
        proposals.append(proposal)

    return {
        "allocation": allocation,
        "market_regime": market_regime,
        "trade_ready_symbols": sorted(trade_ready_symbols),
        "approved_symbols": sorted(approved_symbols),
        "skipped_candidate_count": len(skipped_candidates),
        "skipped_candidates": skipped_candidates[:25],
        "proposal_count": len(proposals),
        "proposals": proposals,
    }

@app.get("/account/spot-portfolio")
async def account_spot_portfolio() -> dict:
    if settings.exchange_name.lower() != "okx":
        return {"connected": False, "code": "unsupported_exchange", "message": settings.exchange_name}
    return await spot_portfolio(settings)

@app.get("/positions/manage")
async def positions_manage(force_ai: bool = False) -> dict:
    report = await evaluate_positions(settings, force_ai=force_ai)
    return {
        **report,
        "proposals": [proposal.model_dump(mode="json") for proposal in report.get("proposals", [])],
    }

@app.get("/positions/backtest")
async def positions_backtest(bar: str = "4H", limit: int = 120) -> dict:
    return await backtest_positions(settings, bar=bar, limit=limit)

@app.post("/positions/approve")
async def positions_approve(payload: dict = Body(...)) -> dict:
    symbol = str(payload.get("symbol") or "").upper()
    action = str(payload.get("action") or "").upper()
    if not symbol or not action:
        return {"ok": False, "message": "symbol va action la bat buoc."}
    record = {
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
        "symbol": symbol,
        "action": action,
        "approved": bool(payload.get("approved")),
        "execution_enabled": False,
        "message": "Approval da duoc ghi nhan, nhung execution quan ly tai san van dang khoa an toan.",
    }
    await insert_doc("position_approvals", record)
    record.pop("_id", None)
    return {**record, "ok": True, "created_at": record["created_at"].isoformat()}

def _telegram_chat_allowed(chat_id: str) -> bool:
    return bool(chat_id and settings.telegram_chat_id and chat_id == settings.telegram_chat_id)

def _normalize_symbol(symbol: str | None) -> str:
    return str(symbol or "").replace("-", "").replace("/", "").upper()

def _market_regime(settings, candidates: list) -> dict:
    if not settings.market_regime_enabled:
        return {"ok": True, "reason": "market_regime_disabled", "items": []}
    regime_symbols = {
        _normalize_symbol(symbol)
        for symbol in settings.market_regime_symbols.split(",")
        if symbol.strip()
    }
    items = [
        {
            "symbol": candidate.symbol,
            "trend_score": candidate.trend_score,
            "liquidity_score": candidate.liquidity_score,
            "volatility_score": candidate.volatility_score,
        }
        for candidate in candidates
        if _normalize_symbol(candidate.symbol) in regime_symbols
    ]
    if not items:
        return {"ok": False, "reason": "missing_regime_symbols", "items": []}
    weak = [
        item
        for item in items
        if item["trend_score"] < settings.market_regime_min_trend
        or item["liquidity_score"] < settings.market_regime_min_liquidity
    ]
    if weak and len(weak) == len(items):
        return {"ok": False, "reason": "all_regime_symbols_weak", "items": items}
    return {"ok": True, "reason": "regime_supportive_or_mixed", "items": items}

def _watchlist_readiness(settings, item: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    created_at = item.get("created_at")
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            created_at = None
    if created_at and created_at.tzinfo is not None:
        created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)
    observation_count = int(item.get("observation_count") or 1)
    age_minutes = ((now - created_at).total_seconds() / 60) if created_at else 0
    enough_observations = observation_count >= max(1, settings.shortlist_min_observations_for_trade)
    enough_age = age_minutes >= max(0, settings.shortlist_min_age_minutes_for_trade)
    if enough_observations or enough_age:
        return {
            "trade_ready": True,
            "reason": f"ready: {observation_count} observations, {age_minutes:.0f} minutes old",
        }
    return {
        "trade_ready": False,
        "reason": (
            f"needs {settings.shortlist_min_observations_for_trade} observations "
            f"or {settings.shortlist_min_age_minutes_for_trade} minutes; "
            f"now {observation_count} observations, {age_minutes:.0f} minutes"
        ),
    }

def _risk_based_amount(settings, candidate, allocation, thesis: dict, default_amount: float) -> float:
    price = float(candidate.price or 0)
    invalidation = thesis.get("invalidation_price_usdt")
    if not price or not invalidation or float(invalidation) >= price:
        return round(min(default_amount, settings.max_live_trade_usd), 2)
    risk_budget = float(settings.user_total_budget_usd) * max(0, settings.risk_per_trade_pct_of_budget) / 100
    risk_per_coin = price - float(invalidation)
    notional = (risk_budget / risk_per_coin) * price if risk_per_coin else default_amount
    group_budget = float(allocation.allocation.get(candidate.group, 0))
    capped = min(notional, default_amount, group_budget * 0.35, settings.max_live_trade_usd)
    return round(max(0, capped), 2)
