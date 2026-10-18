"""Bot lifecycle controls; trading logic remains in the orchestrator."""

from fastapi import APIRouter, HTTPException, Request

from app.api.dependencies import orchestrator_from, runtime_from

router = APIRouter()


@router.post("/bot/start")
def start(request: Request) -> dict:
    runtime = runtime_from(request)
    if not runtime.orchestrators and runtime.settings.broker_startup_enabled:
        runtime.initialize_broker()
    if not runtime.orchestrators:
        value = orchestrator_from(request)
        value.start()
        return {"state": value.state.value, "reason": value.state_reason}
    runtime.start_all()
    return {"state": "RUNNING", "symbols": {key: value.state.value for key, value in runtime.orchestrators.items()}}


@router.post("/bot/stop")
def stop(request: Request) -> dict:
    runtime = runtime_from(request)
    if runtime.orchestrators:
        runtime.stop_all()
        return {"state": "STOPPED", "symbols": {key: value.state.value for key, value in runtime.orchestrators.items()}}
    value = orchestrator_from(request)
    value.stop()
    return {"state": value.state.value}


@router.post("/bot/pause-entry")
def pause_entry(request: Request) -> dict:
    runtime = runtime_from(request)
    if runtime.orchestrators:
        runtime.pause_all()
        return {"state": "ENTRY_PAUSED", "symbols": {key: value.state.value for key, value in runtime.orchestrators.items()}}
    value = orchestrator_from(request)
    value.pause_entry()
    return {"state": value.state.value}


@router.post("/bot/resume-entry")
def resume_entry(request: Request) -> dict:
    runtime = runtime_from(request)
    if runtime.orchestrators:
        if not runtime.resume_all():
            raise HTTPException(status_code=409, detail="Broker reconciliation is not healthy")
        return {"state": "RUNNING", "symbols": {key: value.state.value for key, value in runtime.orchestrators.items()}}
    value = orchestrator_from(request)
    if not value.resume_entry():
        raise HTTPException(status_code=409, detail="Broker reconciliation is not healthy")
    return {"state": value.state.value}
