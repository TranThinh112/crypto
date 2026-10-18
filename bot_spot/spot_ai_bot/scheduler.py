from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from spot_ai_bot.config import Settings
from spot_ai_bot.db import insert_doc, upsert_shortlist_entries
from spot_ai_bot.market_data import scan_market
from spot_ai_bot.portfolio import spot_portfolio
from spot_ai_bot.position_manager import evaluate_positions
from spot_ai_bot.telegram import TelegramNotifier
from spot_ai_bot.watchlist_care import run_watchlist_care

LAST_ALERT_KEYS: set[str] = set()
SCAN_COUNTER = 0
VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


async def run_held_asset_summary(settings: Settings) -> dict:
    report = await evaluate_positions(settings)
    snapshot = {
        "created_at": datetime.now(timezone.utc),
        "exchange": settings.exchange_name,
        "portfolio_source": report.get("portfolio_source"),
        "spot_capital_usdt": report.get("spot_capital_usdt"),
        "proposal_count": report.get("proposal_count"),
        "ai_calls": report.get("ai_calls"),
        "proposals": [proposal.model_dump(mode="json") for proposal in report.get("proposals", [])],
    }
    await insert_doc("held_asset_summaries", snapshot)
    for proposal in report.get("proposals", []):
        await insert_doc("position_management_proposals", proposal.model_dump(mode="json"))
    await TelegramNotifier(settings).position_management(report)
    return snapshot


async def run_scheduled_scan(settings: Settings) -> dict:
    global SCAN_COUNTER
    SCAN_COUNTER += 1

    portfolio = await spot_portfolio(settings)
    spot_capital = float(portfolio.get("spot_capital_usdt") or 0)
    if spot_capital < settings.min_new_trade_capital_usdt:
        snapshot = {
            "created_at": datetime.now(timezone.utc),
            "exchange": settings.exchange_name,
            "data_source": "skipped",
            "fallback_reason": "insufficient_spot_capital_for_new_trade",
            "spot_capital_usdt": spot_capital,
            "min_new_trade_capital_usdt": settings.min_new_trade_capital_usdt,
            "candidate_count": 0,
            "candidates": [],
        }
        should_store, stored_reason = _should_store_scan(settings, snapshot, None, SCAN_COUNTER)
        snapshot["stored"] = should_store
        snapshot["stored_reason"] = stored_reason
        if should_store:
            await insert_doc("market_scans", snapshot)
        return snapshot

    candidates = await scan_market(settings)
    data_source = candidates[0].metadata.get("data_source", "unknown") if candidates else "empty"
    fallback_reason = candidates[0].metadata.get("fallback_reason") if candidates else None
    snapshot = {
        "created_at": datetime.now(timezone.utc),
        "exchange": settings.exchange_name,
        "data_source": data_source,
        "fallback_reason": fallback_reason,
        "candidate_count": len(candidates),
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
    }

    alert = _build_scan_alert(settings, snapshot)
    should_store, stored_reason = _should_store_scan(settings, snapshot, alert, SCAN_COUNTER)
    snapshot["stored"] = should_store
    snapshot["stored_reason"] = stored_reason
    if should_store:
        await insert_doc("market_scans", snapshot)
    shortlist_count = await upsert_shortlist_entries(settings, snapshot.get("candidates", []))
    snapshot["shortlist_count"] = shortlist_count

    if settings.telegram_notify_scans and alert and alert["key"] not in LAST_ALERT_KEYS:
        LAST_ALERT_KEYS.add(alert["key"])
        await TelegramNotifier(settings).scan_alert(alert)
    return snapshot

async def run_top_scan_report(settings: Settings) -> dict:
    candidates = await scan_market(settings)
    data_source = candidates[0].metadata.get("data_source", "unknown") if candidates else "empty"
    fallback_reason = candidates[0].metadata.get("fallback_reason") if candidates else None
    snapshot = {
        "created_at": datetime.now(timezone.utc),
        "exchange": settings.exchange_name,
        "data_source": data_source,
        "fallback_reason": fallback_reason,
        "candidate_count": len(candidates),
        "report_type": "telegram_top5_periodic",
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
    }
    snapshot["shortlist_count"] = await upsert_shortlist_entries(settings, snapshot.get("candidates", []))
    await insert_doc("market_scans", snapshot)

    top_candidates = _top_score_candidates(snapshot.get("candidates", []), limit=5)
    await TelegramNotifier(settings).top_scan_report(snapshot, top_candidates, _daily_report_no(snapshot["created_at"]))
    return {**snapshot, "top_candidates": top_candidates}

def _top_score_candidates(candidates: list[dict], limit: int = 5) -> list[dict]:
    ranked = []
    for candidate in candidates:
        item = dict(candidate)
        item["composite_score"] = _composite_score(item)
        ranked.append(item)
    return sorted(ranked, key=lambda item: item["composite_score"], reverse=True)[:limit]

def _composite_score(candidate: dict) -> float:
    return (
        float(candidate.get("trend_score") or 0) * 0.45
        + float(candidate.get("liquidity_score") or 0) * 0.35
        + (1 - float(candidate.get("volatility_score") or 0)) * 0.20
    )

def _daily_report_no(created_at: datetime) -> int:
    local = created_at.astimezone(VIETNAM_TZ)
    return min(6, max(1, (local.hour // 4) + 1))


def _should_store_scan(settings: Settings, snapshot: dict, alert: dict | None, scan_counter: int) -> tuple[bool, str]:
    if settings.store_all_scans:
        return True, "all_scans_enabled"
    if snapshot.get("data_source") == "skipped":
        interval = max(1, settings.scan_heartbeat_store_interval)
        if scan_counter % interval == 0:
            return True, "skipped_heartbeat"
        return False, "skipped_not_significant"
    if snapshot.get("data_source") != "live":
        return True, "data_source_issue"
    if alert:
        return True, "signal_or_alert"
    interval = max(1, settings.scan_heartbeat_store_interval)
    if scan_counter % interval == 0:
        return True, "heartbeat"
    return False, "not_significant"


def _build_scan_alert(settings: Settings, snapshot: dict) -> dict | None:
    if snapshot.get("data_source") != "live":
        return {
            "key": f"fallback:{snapshot.get('fallback_reason')}",
            "title": _u("Bot \\u0111ang d\\u00f9ng d\\u1eef li\\u1ec7u d\\u1ef1 ph\\u00f2ng"),
            "detail": snapshot.get("fallback_reason") or _u("Kh\\u00f4ng l\\u1ea5y \\u0111\\u01b0\\u1ee3c d\\u1eef li\\u1ec7u th\\u1ecb tr\\u01b0\\u1eddng th\\u1eadt."),
            "candidates": [],
        }

    signal_candidates = []
    for candidate in snapshot.get("candidates", []):
        if (
            float(candidate.get("trend_score") or 0) >= settings.signal_trend_threshold
            and float(candidate.get("liquidity_score") or 0) >= settings.signal_liquidity_threshold
            and float(candidate.get("volatility_score") or 0) <= settings.signal_max_volatility
        ):
            signal_candidates.append(candidate)

    if not signal_candidates:
        return None

    symbols = ",".join(sorted(candidate["symbol"] for candidate in signal_candidates))
    return {
        "key": f"signals:{symbols}",
        "title": _u("C\\u00f3 m\\u00e3 \\u0111\\u1ea1t \\u0111i\\u1ec1u ki\\u1ec7n t\\u00edn hi\\u1ec7u"),
        "detail": _u(f"{len(signal_candidates)} m\\u00e3 \\u0111\\u00e3 v\\u01b0\\u1ee3t ng\\u01b0\\u1ee1ng qu\\u00e9t."),
        "candidates": signal_candidates,
    }


def _u(text: str) -> str:
    return text.encode("ascii").decode("unicode_escape")


def create_scheduler(settings: Settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    if settings.auto_scan_enabled:
        scheduler.add_job(
            run_scheduled_scan,
            "interval",
            seconds=max(30, settings.scan_interval_seconds),
            args=[settings],
            id="market_scan",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            next_run_time=datetime.now(timezone.utc),
        )
    if settings.telegram_top_scan_report_enabled:
        scheduler.add_job(
            run_top_scan_report,
            "cron",
            hour="0,4,8,12,16,20",
            minute=0,
            second=0,
            timezone=VIETNAM_TZ,
            args=[settings],
            id="telegram_top5_scan_report",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3 * 60 * 60,
        )
    if settings.held_asset_summary_enabled:
        scheduler.add_job(
            run_held_asset_summary,
            "interval",
            seconds=max(300, settings.held_asset_summary_interval_seconds),
            args=[settings],
            id="held_asset_summary",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
    if settings.watchlist_care_enabled:
        scheduler.add_job(
            run_watchlist_care,
            "interval",
            seconds=max(300, settings.watchlist_care_interval_seconds),
            args=[settings],
            id="watchlist_care",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
    return scheduler
