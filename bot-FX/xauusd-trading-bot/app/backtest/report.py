"""Backtest statistics and JSON/CSV artifact output."""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from pathlib import Path
from statistics import mean

import pandas as pd

from app.backtest.engine import BacktestResult, BacktestTrade, BasketRecord


def _max_streak(values: list[bool], wanted: bool) -> int:
    best = current = 0
    for value in values:
        current = current + 1 if value is wanted else 0
        best = max(best, current)
    return best


def build_report(result: BacktestResult) -> dict:
    trades = list(result.trades)
    profits = [item.profit for item in trades]
    wins = [value for value in profits if value > 0]
    losses = [value for value in profits if value < 0]
    gross_profit, gross_loss = sum(wins), abs(sum(losses))
    equity = [value for _, value in result.equity_curve]
    peak = equity[0] if equity else 0
    max_drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, peak - value)
    monthly: dict[str, float] = {}
    for trade in trades:
        key = trade.closed_at.strftime("%Y-%m")
        monthly[key] = monthly.get(key, 0) + trade.profit
    baskets = list(result.baskets)
    total = len(trades)
    return {
        "total_trades": total, "winning_trades": len(wins), "losing_trades": len(losses),
        "win_rate": len(wins) / total * 100 if total else 0, "net_profit": sum(profits),
        "gross_profit": gross_profit, "gross_loss": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "maximum_drawdown": max_drawdown, "average_win": mean(wins) if wins else 0,
        "average_loss": mean(losses) if losses else 0,
        "average_risk_reward": mean([item.achieved_r_multiple for item in trades]) if trades else 0,
        "expectancy": mean(profits) if profits else 0,
        "maximum_consecutive_wins": _max_streak([value > 0 for value in profits], True),
        "maximum_consecutive_losses": _max_streak([value < 0 for value in profits], True),
        "average_holding_time_seconds": mean([item.holding_seconds for item in trades]) if trades else 0,
        "basket_statistics": {
            "total": len(baskets), "profitable": sum(item.profit > 0 for item in baskets),
            "losing": sum(item.profit < 0 for item in baskets),
            "net_profit": sum(item.profit for item in baskets),
            "maximum_drawdown": max((item.maximum_drawdown for item in baskets), default=0),
        },
        "monthly_performance": monthly,
        "signal_count": result.signal_count, "rejected_signal_count": result.rejected_signal_count,
    }


def write_report(result: BacktestResult, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(result)
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    pd.DataFrame([asdict(item) for item in result.trades], columns=[item.name for item in fields(BacktestTrade)]).to_csv(output_dir / "trades.csv", index=False)
    pd.DataFrame([asdict(item) for item in result.baskets], columns=[item.name for item in fields(BasketRecord)]).to_csv(output_dir / "baskets.csv", index=False)
    pd.DataFrame([{"month": month, "profit": profit} for month, profit in report["monthly_performance"].items()]).to_csv(output_dir / "monthly_performance.csv", index=False)
    return report
