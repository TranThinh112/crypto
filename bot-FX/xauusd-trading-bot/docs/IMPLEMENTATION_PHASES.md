# Implementation phases

## Giai đoạn 1 — nền tảng

Config/domain/database/MT5/market data: `app/config`, `app/models`, `app/repositories`, `app/database.py`, `app/broker/mt5_client.py`, `app/broker/symbol_resolver.py`, `app/market_data/candle_provider.py`, `app/market_data/tick_provider.py`.

Kiểm tra: compile toàn package, validate YAML và tổng signal weights bằng 100.

## Giai đoạn 2 — rule engine

`app/market_data/indicator_service.py`, `app/strategy/trend_detector.py`, `signal_engine.py`, `entry_validator.py`, `exit_signal_engine.py`.

Kiểm tra: dữ liệu tổng hợp xác nhận indicator hữu hạn và trend H4/H1 đồng thuận.

## Giai đoạn 3 — risk và execution

`app/risk`, `app/broker/paper_client.py`, `app/broker/execution_service.py`.

Kiểm tra: paper order có SL/TP, lot theo tick metadata và duplicate key chỉ tạo một position.

## Giai đoạn 4 — position và basket

`app/positions`.

Kiểm tra: basket PnL/weighted entry, break-even, ATR trailing, partial volume rounding và TP/SL rules.

## Giai đoạn 5 — runtime và recovery

`app/guards`, `app/services`, `app/logging_config.py`.

Kiểm tra: session, cooldown persistence và paper restart reconciliation.

## Giai đoạn 6 — API/backtest/QA/packaging

`app/api`, `app/backtest`, `app/main.py`, `scripts`, `migrations`, `tests`, Docker và README.

Kiểm tra cuối: `pytest -q`, compile, migration smoke test và route/schema inspection.
