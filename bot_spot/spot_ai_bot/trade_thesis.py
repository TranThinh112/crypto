from __future__ import annotations

from datetime import datetime, timezone

from spot_ai_bot.config import Settings
from spot_ai_bot.models import MarketCandidate


def build_trade_thesis(settings: Settings, candidate: MarketCandidate, watchlist_item: dict | None = None) -> dict:
    metadata = candidate.metadata or {}
    price = float(candidate.price or 0)
    support = _to_float(metadata.get("support_usdt")) or None
    resistance = _to_float(metadata.get("resistance_usdt")) or None
    change_pct = _to_float(metadata.get("change_pct"))
    buy_zone = _buy_zone(settings, price, support, resistance)
    status, status_reason = thesis_status(settings, candidate, buy_zone)
    now = datetime.now(timezone.utc)
    return {
        "symbol": candidate.symbol,
        "exchange_symbol": metadata.get("exchange_symbol") or candidate.symbol,
        "status": status,
        "status_reason": status_reason,
        "created_at": (watchlist_item or {}).get("created_at") or now,
        "updated_at": now,
        "watchlist_reason": (watchlist_item or {}).get("reason") or metadata.get("shortlist_reason"),
        "observation_count": (watchlist_item or {}).get("observation_count", 1),
        "entry_price_reference_usdt": price,
        "current_price_usdt": price,
        "support_usdt": support,
        "resistance_usdt": resistance,
        "buy_zone": buy_zone,
        "invalidation_price_usdt": support if support else round(price * 0.94, 8),
        "take_profit_zones_usdt": _take_profit_zones(price, resistance),
        "change_pct": change_pct,
        "trend_score": candidate.trend_score,
        "liquidity_score": candidate.liquidity_score,
        "volatility_score": candidate.volatility_score,
        "thesis": (
            f"Watch {candidate.symbol}: trend={candidate.trend_score:.2f}, "
            f"liquidity={candidate.liquidity_score:.2f}, volatility={candidate.volatility_score:.2f}, "
            f"24h={change_pct:.2f}%."
        ),
        "rules": [
            "Only consider new buy when watchlist is trade-ready.",
            "Avoid chasing strong 24h pumps or buys too close to resistance.",
            "No automatic sell; position actions require management proposal and approval.",
        ],
    }


def thesis_status(settings: Settings, candidate: MarketCandidate, buy_zone: dict) -> tuple[str, str]:
    metadata = candidate.metadata or {}
    change_pct = _to_float(metadata.get("change_pct"))
    price = float(candidate.price or 0)
    support = _to_float(metadata.get("support_usdt")) or None
    drawdown = metadata.get("drawdown_from_resistance_pct")
    drawdown_pct = _to_float(drawdown) if drawdown is not None else None
    if support and price < support:
        return "invalidated", "price_below_support"
    if candidate.trend_score < settings.signal_trend_threshold or candidate.liquidity_score < settings.signal_liquidity_threshold:
        return "watch", "trend_or_liquidity_below_buy_threshold"
    if change_pct >= settings.anti_pump_max_24h_change_pct:
        return "watch", "anti_pump_wait_for_pullback"
    if drawdown_pct is not None and drawdown_pct >= settings.anti_pump_near_resistance_pct and change_pct > 0:
        return "watch", "near_resistance_wait_for_retest"
    if buy_zone.get("in_zone"):
        return "buy_zone", buy_zone.get("reason", "price_in_buy_zone")
    return "trade_ready", buy_zone.get("reason", "trade_ready_wait_for_zone")


def _buy_zone(settings: Settings, price: float, support: float | None, resistance: float | None) -> dict:
    if price <= 0:
        return {"in_zone": False, "reason": "missing_price"}
    zones = []
    if support:
        upper = support * (1 + settings.buy_zone_support_buffer_pct / 100)
        zones.append({"type": "support_pullback", "low": support, "high": round(upper, 8)})
        if price <= upper:
            return {"in_zone": True, "reason": "near_support_pullback", "zones": zones}
    if resistance:
        retest_low = resistance * (1 - settings.buy_zone_breakout_buffer_pct / 100)
        retest_high = resistance * (1 + settings.buy_zone_breakout_buffer_pct / 100)
        zones.append({"type": "breakout_retest", "low": round(retest_low, 8), "high": round(retest_high, 8)})
        if retest_low <= price <= retest_high:
            return {"in_zone": True, "reason": "breakout_retest_zone", "zones": zones}
    return {"in_zone": False, "reason": "price_outside_buy_zone", "zones": zones}


def _take_profit_zones(price: float, resistance: float | None) -> list[float]:
    first = resistance if resistance and resistance > price else round(price * 1.08, 8)
    return [first, round(price * 1.16, 8)]


def _to_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
