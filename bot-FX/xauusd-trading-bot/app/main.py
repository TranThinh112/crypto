"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from app.api import routes_config, routes_control, routes_dashboard, routes_positions, routes_status
from app.config.settings import get_app_settings, load_trading_config
from app.database import Database
from app.logging_config import configure_logging
from app.runtime import Runtime


def create_app(runtime_override: Runtime | None = None) -> FastAPI:
    project_path = Path(__file__).resolve().parents[1]

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if runtime_override is not None:
            runtime = runtime_override
        else:
            load_dotenv(project_path / ".env")
            settings = get_app_settings()
            configure_logging(project_path / "logs", settings.log_level)
            config = load_trading_config(settings.config_path)
            database = Database(settings.database_url)
            database.create_schema()
            runtime = Runtime(settings, config, database, project_path)
            runtime.initialize_broker()
        application.state.runtime = runtime
        yield
        runtime.shutdown()

    application = FastAPI(title="XAUUSD Rule-Based Trading Bot", version="1.0.0", lifespan=lifespan)
    for router in (routes_dashboard.router, routes_status.router, routes_positions.router, routes_config.router, routes_control.router):
        application.include_router(router)
    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    settings = get_app_settings()
    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port, reload=False)
