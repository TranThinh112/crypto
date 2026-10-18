"""API dependency helpers."""

from fastapi import HTTPException, Request

from app.runtime import Runtime
from app.services.trading_orchestrator import TradingOrchestrator


def runtime_from(request: Request) -> Runtime:
    return request.app.state.runtime


def orchestrator_from(request: Request) -> TradingOrchestrator:
    runtime = runtime_from(request)
    if runtime.orchestrator is None and not runtime.orchestrators:
        raise HTTPException(status_code=503, detail=runtime.initialization_error or "Broker runtime is disabled or BACKTEST mode is active")
    return runtime.orchestrator or next(iter(runtime.orchestrators.values()))
