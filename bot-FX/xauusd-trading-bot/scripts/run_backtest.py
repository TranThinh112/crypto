"""CLI for deterministic CSV backtests with explicit broker symbol metadata."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.backtest.engine import BacktestEngine
from app.backtest.report import write_report
from app.broker.mt5_client import SymbolSpec
from app.config.settings import load_trading_config


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("csv", type=Path)
    value.add_argument("--output", type=Path, default=Path("backtest_output"))
    value.add_argument("--config", type=Path, default=Path("app/config/trading_config.yaml"))
    value.add_argument("--digits", type=int, required=True)
    value.add_argument("--point", type=float, required=True)
    value.add_argument("--tick-size", type=float, required=True)
    value.add_argument("--tick-value", type=float, required=True)
    value.add_argument("--contract-size", type=float, required=True)
    value.add_argument("--volume-min", type=float, required=True)
    value.add_argument("--volume-max", type=float, required=True)
    value.add_argument("--volume-step", type=float, required=True)
    value.add_argument("--stops-level", type=int, default=0)
    return value


def main() -> None:
    args = parser().parse_args()
    config = load_trading_config(args.config)
    spec = SymbolSpec("XAUUSD", args.digits, args.point, args.tick_size, args.tick_value, args.contract_size, args.volume_min, args.volume_max, args.volume_step, 0, args.stops_level, 4, 0, True)
    result = BacktestEngine(config, spec).run(pd.read_csv(args.csv))
    print(json.dumps(write_report(result, args.output), indent=2, default=str))


if __name__ == "__main__":
    main()
