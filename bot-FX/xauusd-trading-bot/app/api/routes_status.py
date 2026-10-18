"""Health, status, signal and daily-statistics endpoints."""

import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from math import isfinite
from statistics import mean

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from app.api.dependencies import runtime_from
from app.models.bot_state import DailyStatistic
from app.models.event_log import SignalDecision
from app.models.trade import Trade

router = APIRouter()

LOG_FILES = ("bot_server_stdout.log", "bot_server_error.log", "error.log", "application.log", "trading.log", "execution.log")


def _tail_lines(path, limit: int) -> list[str]:
    if not path.exists() or not path.is_file():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()
    return [line.strip() for line in lines[-limit:] if line.strip()]


def _parse_log_line(filename: str, line: str) -> dict:
    try:
        payload = json.loads(line)
        return {
            "file": filename,
            "timestamp": payload.get("timestamp"),
            "level": payload.get("level", "INFO"),
            "event_type": payload.get("event_type"),
            "symbol": payload.get("symbol"),
            "message": payload.get("message", line),
            "context": payload.get("context") or {},
        }
    except json.JSONDecodeError:
        return {
            "file": filename,
            "timestamp": None,
            "level": "INFO",
            "event_type": "CONSOLE",
            "symbol": None,
            "message": line,
            "context": {},
        }


def _stale_care_symbols(health_symbols: dict, max_age_seconds: float = 30) -> dict:
    stale_symbols = {}
    for key, snapshot in health_symbols.items():
        ages = snapshot.get("loop_heartbeat_age_seconds") or {}
        position_age = ages.get("position_manager")
        signal_age = ages.get("signal_loop")
        if not snapshot.get("healthy") or (position_age is not None and position_age > max_age_seconds) or (signal_age is not None and signal_age > max_age_seconds):
            stale_symbols[key] = {
                "healthy": snapshot.get("healthy"),
                "position_manager_age_seconds": position_age,
                "signal_loop_age_seconds": signal_age,
            }
    return stale_symbols

@router.get("/health")
def health(request: Request) -> dict:
    runtime = runtime_from(request)
    if runtime.orchestrators:
        symbols = {key: orchestrator.health.snapshot() for key, orchestrator in runtime.orchestrators.items()}
        return {
            "healthy": all(value.get("healthy") for value in symbols.values()),
            "symbols": symbols,
            "checked_at": datetime.now(UTC).isoformat(),
        }
    if runtime.orchestrator:
        return runtime.orchestrator.health.snapshot()
    return {"healthy": runtime.database.healthcheck(), "broker_runtime": False, "initialization_error": runtime.initialization_error, "checked_at": datetime.now(UTC).isoformat()}


@router.get("/status")
def status(request: Request) -> dict:
    runtime = runtime_from(request)
    orchestrator = runtime.orchestrator
    recovery_status = orchestrator.recovery_mode_status() if orchestrator else None
    health_symbols = {key: value.health.snapshot() for key, value in runtime.orchestrators.items()}
    stale_symbols = _stale_care_symbols(health_symbols)
    symbol_states = {
        key: {
            "symbol": runtime.symbols.get(key),
            "state": value.state.value,
            "state_reason": value.state_reason,
        }
        for key, value in runtime.orchestrators.items()
    }
    return {
        "bot_name": runtime.config.bot.name, "mode": runtime.config.bot.mode.value,
        "state": orchestrator.state.value if orchestrator else "STOPPED",
        "state_reason": orchestrator.state_reason if orchestrator else runtime.initialization_error,
        "symbol": runtime.symbol, "symbols": runtime.symbols, "symbol_states": symbol_states,
        "care_warning": bool(stale_symbols),
        "care_warning_symbols": stale_symbols,
        "recovery_mode": recovery_status,
        "magic_number": runtime.config.broker.magic_number,
        "live_trading_enabled": runtime.settings.enable_live_trading,
    }


@router.get("/logs/system")
def system_logs(request: Request, limit: int = Query(default=80, ge=1, le=300)) -> dict:
    runtime = runtime_from(request)
    log_dir = runtime.project_path / "logs"
    per_file_limit = max(20, min(limit, 120))
    entries: list[dict] = []
    for filename in LOG_FILES:
        path = log_dir / filename
        entries.extend(_parse_log_line(filename, line) for line in _tail_lines(path, per_file_limit))
    entries.sort(key=lambda item: item.get("timestamp") or "")
    return {
        "entries": entries[-limit:],
        "files": [filename for filename in LOG_FILES if (log_dir / filename).exists()],
        "checked_at": datetime.now(UTC).isoformat(),
    }


@router.get("/account")
def account(request: Request) -> dict:
    runtime = runtime_from(request)
    if runtime.broker is None:
        raise HTTPException(status_code=503, detail="Broker runtime is not connected")
    return asdict(runtime.broker.account())


@router.get("/symbol-specs")
def symbol_specs(request: Request) -> dict[str, dict]:
    runtime = runtime_from(request)
    return {
        symbol: asdict(spec)
        for symbol, spec in ((runtime.symbols.get(key), value) for key, value in runtime.specs.items())
        if symbol is not None
    }


@router.get("/signals/latest")
def latest_signal(request: Request) -> dict | None:
    runtime = runtime_from(request)
    with runtime.database.transaction() as session:
        value = session.scalar(select(SignalDecision).order_by(SignalDecision.timestamp.desc(), SignalDecision.id.desc()).limit(1))
        if value is None:
            return None
        return {column.name: getattr(value, column.name) for column in value.__table__.columns}


@router.get("/statistics/daily")
def daily_statistics(request: Request) -> list[dict]:
    runtime = runtime_from(request)
    with runtime.database.transaction() as session:
        values = session.scalars(select(DailyStatistic).order_by(DailyStatistic.trading_date.desc()).limit(90)).all()
        return [{column.name: getattr(value, column.name) for column in value.__table__.columns} for value in values]

def _trade_dict(value: Trade) -> dict:
    return {column.name: getattr(value, column.name) for column in value.__table__.columns}

def _timeframe_from_trade(trade: dict) -> str:
    key = str(trade.get("idempotency_key") or "")
    parts = key.split("_")
    for part in parts:
        if part in {"M1", "M5", "M15", "M15Q", "M30", "H1", "H4"}:
            return part
    return "UNKNOWN"

def _session_bucket(value: datetime | None, hours: int) -> str:
    if value is None:
        return "UNKNOWN"
    local = value + timedelta(hours=7)
    start = (local.hour // hours) * hours
    end = min(start + hours, 24)
    return f"{start:02d}:00-{end:02d}:00"

def _wr_bucket(value: float | None, size: float) -> str:
    if value is None or not isfinite(value):
        return "UNKNOWN"
    lower = int(value // size) * size
    upper = min(100.0, lower + size)
    return f"{lower:.0f}-{upper:.0f}%"

def _stats(items: list[dict]) -> dict:
    pnls = [float(item.get("realized_profit") or 0.0) for item in items]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    risk_items = [item for item in items if item.get("initial_risk_amount") not in (None, 0)]
    adverse = [float(item.get("max_adverse_r") or 0.0) for item in risk_items]
    favorable = [float(item.get("max_favorable_r") or 0.0) for item in risk_items]
    return {
        "trades": len(items),
        "wins": len(wins),
        "losses": len(losses),
        "flats": len(items) - len(wins) - len(losses),
        "win_rate": round(len(wins) * 100 / len(items), 2) if items else 0.0,
        "net_pnl": round(sum(pnls), 2),
        "gross_win": round(gross_win, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss > 0 else (None if gross_win <= 0 else 999.0),
        "avg_win": round(mean(wins), 2) if wins else 0.0,
        "avg_loss": round(mean(losses), 2) if losses else 0.0,
        "avg_max_adverse_r": round(mean(adverse), 3) if adverse else 0.0,
        "avg_max_favorable_r": round(mean(favorable), 3) if favorable else 0.0,
        "be_applied": sum(1 for item in items if bool(item.get("break_even_applied"))),
    }

def _recommendation(stats: dict, min_samples: int, block_wr: float, raise_wr: float, min_pf: float | None = None) -> dict:
    trades = int(stats["trades"])
    if trades < min_samples:
        return {"action": "WATCH", "reason": f"Need {min_samples - trades} more samples", "severity": "neutral"}
    pf = stats.get("profit_factor")
    if stats["net_pnl"] < 0 and stats["win_rate"] < block_wr:
        return {"action": "BLOCK", "reason": f"WR {stats['win_rate']:.1f}% below {block_wr:.1f}% and net PnL negative", "severity": "danger"}
    if min_pf is not None and pf is not None and pf < min_pf:
        return {"action": "RAISE_WR", "reason": f"Profit factor {pf:.2f} below {min_pf:.2f}", "severity": "warning"}
    if stats["net_pnl"] < 0 or stats["win_rate"] < raise_wr:
        return {"action": "RAISE_WR", "reason": f"Weak edge: WR {stats['win_rate']:.1f}%, net {stats['net_pnl']:.2f}", "severity": "warning"}
    return {"action": "ALLOW", "reason": "Positive enough for current sample", "severity": "success"}

def _group_report(items: list[dict], key: str, label: str, learning: dict, limit: int = 20) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for item in items:
        groups.setdefault(str(item.get(key) or "UNKNOWN"), []).append(item)
    rows = []
    for name, values in groups.items():
        stats = _stats(values)
        rows.append({
            "label": name,
            "dimension": label,
            "stats": stats,
            "recommendation": _recommendation(
                stats,
                int(learning.get("block_min_samples") or 10),
                float(learning.get("block_win_rate_below") or 40.0),
                float(learning.get("raise_threshold_win_rate_below") or 50.0),
                float(learning.get("block_profit_factor_below") or 0.0) or None,
            ),
        })
    return sorted(rows, key=lambda row: (row["recommendation"]["action"] != "BLOCK", -abs(row["stats"]["net_pnl"]), -row["stats"]["trades"]))[:limit]

@router.get("/statistics/learning")
def learning_statistics(request: Request, lookback_days: int = Query(default=90, ge=1, le=365)) -> dict:
    runtime = runtime_from(request)
    learning = runtime.config.adaptive_learning.model_dump(mode="json")
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=lookback_days)
    with runtime.database.transaction() as session:
        values = session.scalars(
            select(Trade)
            .where(Trade.state == "CLOSED", Trade.closed_at.is_not(None), Trade.closed_at >= cutoff)
            .order_by(Trade.closed_at.desc(), Trade.id.desc())
        ).all()
    trades = [_trade_dict(value) for value in values]
    bucket_hours = int(learning.get("session_bucket_hours") or 4)
    wr_size = float(learning.get("wr_bucket_size") or 5.0)
    for trade in trades:
        trade["setup_timeframe"] = _timeframe_from_trade(trade)
        trade["session_bucket"] = _session_bucket(trade.get("closed_at") or trade.get("opened_at"), bucket_hours)
        trade["wr_bucket"] = _wr_bucket(float(trade["estimated_win_rate"]) if trade.get("estimated_win_rate") is not None else None, wr_size)
        trade["symbol_base"] = str(trade.get("symbol") or "UNKNOWN").upper()
        trade["setup_key"] = f"{trade['symbol_base']}:{trade.get('side') or 'UNKNOWN'}:{trade['setup_timeframe']}:{trade['wr_bucket']}"

    overall = _stats(trades)
    dimensions = {
        "symbols": _group_report(trades, "symbol_base", "Symbol", learning),
        "setups": _group_report(trades, "setup_key", "Setup", learning),
        "sessions": _group_report(trades, "session_bucket", "Session", learning),
        "wr_buckets": _group_report(trades, "wr_bucket", "WR bucket", learning),
        "close_reasons": _group_report(trades, "close_reason", "Close reason", learning),
    }
    management = {
        "break_even": _stats([trade for trade in trades if bool(trade.get("break_even_applied"))]),
        "no_break_even": _stats([trade for trade in trades if not bool(trade.get("break_even_applied"))]),
        "painful_trades": _stats([trade for trade in trades if float(trade.get("max_adverse_r") or 0.0) >= float(learning.get("drawdown_pain_r") or 0.8)]),
        "strong_runups": _stats([trade for trade in trades if float(trade.get("max_favorable_r") or 0.0) >= 0.5]),
    }
    watchlist = sorted(
        [row for rows in dimensions.values() for row in rows if row["recommendation"]["action"] in {"BLOCK", "RAISE_WR"}],
        key=lambda row: (row["recommendation"]["action"] != "BLOCK", row["stats"]["net_pnl"]),
    )[:12]
    return {
        "lookback_days": lookback_days,
        "generated_at": datetime.now(UTC).isoformat(),
        "learning_config": learning,
        "overall": overall,
        "dimensions": dimensions,
        "management": management,
        "watchlist": watchlist,
        "sample_recent": trades[:20],
    }
