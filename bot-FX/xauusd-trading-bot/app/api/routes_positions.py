"""Read positions/trades/baskets and explicitly confirmed close actions."""

from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.dependencies import runtime_from
from app.models.basket import Basket
from app.models.trade import Trade

router = APIRouter()


class CloseConfirmation(BaseModel):
    confirm: Literal[True]
    reason: str = Field(min_length=3, max_length=120)


@router.get("/positions")
def positions(request: Request) -> list[dict]:
    runtime = runtime_from(request)
    if runtime.broker is None:
        return []
    if runtime.orchestrators:
        return [
            asdict(position)
            for key, orchestrator in runtime.orchestrators.items()
            for position in runtime.broker.positions(runtime.symbols[key], orchestrator.config.broker.magic_number)
        ]
    if runtime.symbol is None:
        return []
    return [asdict(item) for item in runtime.broker.positions(runtime.symbol, runtime.config.broker.magic_number)]


@router.get("/baskets")
def baskets(request: Request) -> list[dict]:
    runtime = runtime_from(request)
    with runtime.database.transaction() as session:
        values = session.scalars(select(Basket).order_by(Basket.id.desc()).limit(200)).all()
        return [{column.name: getattr(value, column.name) for column in value.__table__.columns} for value in values]


@router.get("/trades")
def trades(request: Request) -> list[dict]:
    runtime = runtime_from(request)
    with runtime.database.transaction() as session:
        values = session.scalars(select(Trade).order_by(Trade.id.desc()).limit(500)).all()
        return [{column.name: getattr(value, column.name) for column in value.__table__.columns} for value in values]


@router.post("/positions/close-all")
def close_all(body: CloseConfirmation, request: Request) -> dict:
    runtime = runtime_from(request)
    if not runtime.close_all_manually(body.reason):
        raise HTTPException(status_code=409, detail="One or more bot positions could not be closed")
    return {"closed": True, "reason": body.reason}


@router.post("/baskets/{basket_id}/close")
def close_basket(basket_id: str, body: CloseConfirmation, request: Request) -> dict:
    runtime = runtime_from(request)
    if not runtime.close_basket_manually(basket_id, body.reason):
        raise HTTPException(status_code=409, detail="Basket could not be closed")
    return {"closed": True, "basket_id": basket_id, "reason": body.reason}
