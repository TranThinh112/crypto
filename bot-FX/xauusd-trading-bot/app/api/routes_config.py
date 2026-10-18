"""Validated runtime configuration endpoints."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from typing import Literal

from app.api.dependencies import runtime_from
from app.config.settings import FOREX_SYMBOLS, BasketTakeProfitConfig, SupportedSymbol
from app.utils.enums import BasketStopLossMode
from app.utils.enums import BasketProfitMode

router = APIRouter()


class DailyRiskUpdate(BaseModel):
    daily_profit_target_usd: float | None = Field(default=None, gt=0)
    max_daily_loss_usd: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def at_least_one_value(self) -> "DailyRiskUpdate":
        if self.daily_profit_target_usd is None and self.max_daily_loss_usd is None:
            raise ValueError("Provide at least one daily risk value")
        return self


class BasketStopLossUpdate(BaseModel):
    mode: BasketStopLossMode | None = None
    maximum_loss_usd: float | None = Field(default=None, gt=0)
    hard_max_loss_usd: float | None = Field(default=None, gt=0)
    maximum_loss_percent: float | None = Field(default=None, gt=0)
    balanced_daily_loss_ratio: float | None = Field(default=None, gt=0, le=1)
    balanced_minimum_loss_usd: float | None = Field(default=None, gt=0)
    enabled: bool | None = None

    @model_validator(mode="after")
    def at_least_one_value(self) -> "BasketStopLossUpdate":
        if (
            self.mode is None
            and self.maximum_loss_usd is None
            and self.hard_max_loss_usd is None
            and self.maximum_loss_percent is None
            and self.balanced_daily_loss_ratio is None
            and self.balanced_minimum_loss_usd is None
            and self.enabled is None
        ):
            raise ValueError("Provide at least one basket stop loss value")
        return self


class BasketTakeProfitUpdate(BaseModel):
    mode: BasketProfitMode | None = None
    target_r_multiple: float | None = Field(default=None, gt=0)
    target_fixed_usd: float | None = Field(default=None, gt=0)
    fast_target_fixed_usd: float | None = Field(default=None, gt=0)
    target_equity_percent: float | None = Field(default=None, gt=0)
    enabled: bool | None = None

    @model_validator(mode="after")
    def at_least_one_value(self) -> "BasketTakeProfitUpdate":
        if (
            self.mode is None
            and self.target_r_multiple is None
            and self.target_fixed_usd is None
            and self.fast_target_fixed_usd is None
            and self.target_equity_percent is None
            and self.enabled is None
        ):
            raise ValueError("Provide at least one basket take profit value")
        return self

class HardTradeUpdate(BaseModel):
    enabled: bool | None = None
    minimum_setup_win_rate: float | None = Field(default=None, ge=0, le=100)
    m5_minimum_setup_win_rate: float | None = Field(default=None, ge=0, le=100)
    max_lot_per_entry: float | None = Field(default=None, gt=0)
    max_open_positions: int | None = Field(default=None, ge=1)
    max_add_entry_distance_atr: float | None = Field(default=None, gt=0)
    max_losing_basket_add_usd: float | None = Field(default=None, ge=0)
    allow_fast_scalp: bool | None = None
    scan_interval_seconds: float | None = Field(default=None, gt=0)
    position_monitor_interval_seconds: float | None = Field(default=None, ge=1)
    preferred_setup_timeframe: Literal["M15", "M30"] | None = None
    preferred_entry_timeframe: Literal["M5", "M15"] | None = None
    emergency_exit_on_restart: bool | None = None
    emergency_exit_max_loss_usd: float | None = Field(default=None, gt=0)
    emergency_exit_max_adverse_r: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def at_least_one_value(self) -> "HardTradeUpdate":
        if (
            self.enabled is None
            and self.minimum_setup_win_rate is None
            and self.m5_minimum_setup_win_rate is None
            and self.max_lot_per_entry is None
            and self.max_open_positions is None
            and self.max_add_entry_distance_atr is None
            and self.max_losing_basket_add_usd is None
            and self.allow_fast_scalp is None
            and self.scan_interval_seconds is None
            and self.position_monitor_interval_seconds is None
            and self.preferred_setup_timeframe is None
            and self.preferred_entry_timeframe is None
            and self.emergency_exit_on_restart is None
            and self.emergency_exit_max_loss_usd is None
            and self.emergency_exit_max_adverse_r is None
        ):
            raise ValueError("Provide at least one hard trade value")
        return self

class ForexTradingUpdate(BaseModel):
    enabled: bool | None = None
    symbols: tuple[SupportedSymbol, ...] | None = None
    max_open_positions: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def at_least_one_value(self) -> "ForexTradingUpdate":
        if self.enabled is None and self.symbols is None and self.max_open_positions is None:
            raise ValueError("Provide at least one forex trading value")
        if self.symbols is not None:
            invalid = [symbol for symbol in self.symbols if symbol not in FOREX_SYMBOLS]
            if invalid:
                raise ValueError(f"Forex mode only accepts currency pairs: {', '.join(invalid)}")
        return self

class PositionControlUpdate(BaseModel):
    max_open_positions: int | None = Field(default=None, ge=1)
    max_buy_positions: int | None = Field(default=None, ge=1)
    max_sell_positions: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def at_least_one_value(self) -> "PositionControlUpdate":
        if self.max_open_positions is None and self.max_buy_positions is None and self.max_sell_positions is None:
            raise ValueError("Provide at least one position-control value")
        return self


@router.get("/config")
def config(request: Request) -> dict:
    return runtime_from(request).config.model_dump(mode="json")


@router.patch("/config/daily-risk")
def update_daily_risk(body: DailyRiskUpdate, request: Request) -> dict:
    runtime = runtime_from(request)
    config = runtime.update_daily_risk_limits(
        daily_profit_target_usd=body.daily_profit_target_usd,
        max_daily_loss_usd=body.max_daily_loss_usd,
    )
    return config.daily_risk.model_dump(mode="json")


@router.patch("/config/basket-stop-loss")
def update_basket_stop_loss(body: BasketStopLossUpdate, request: Request) -> dict:
    runtime = runtime_from(request)
    current = runtime.config.basket_stop_loss
    updates = body.model_dump(exclude_unset=True)
    basket_stop_loss = current.model_copy(update=updates)
    config = runtime.update_basket_stop_loss(basket_stop_loss)
    return config.basket_stop_loss.model_dump(mode="json")


@router.patch("/config/basket-take-profit")
def update_basket_take_profit(body: BasketTakeProfitUpdate, request: Request) -> dict:
    runtime = runtime_from(request)
    current = runtime.config.basket_take_profit
    updates = body.model_dump(exclude_unset=True)
    basket_take_profit = current.model_copy(update=updates)
    config = runtime.update_basket_take_profit(basket_take_profit)
    return config.basket_take_profit.model_dump(mode="json")

@router.patch("/config/hard-trade")
def update_hard_trade(body: HardTradeUpdate, request: Request) -> dict:
    runtime = runtime_from(request)
    current = runtime.config.hard_trade
    updates = body.model_dump(exclude_unset=True)
    hard_trade = current.model_copy(update=updates)
    config = runtime.update_hard_trade(hard_trade)
    return config.hard_trade.model_dump(mode="json")

@router.patch("/config/position-control")
def update_position_control(body: PositionControlUpdate, request: Request) -> dict:
    runtime = runtime_from(request)
    current = runtime.config.position_control
    updates = body.model_dump(exclude_unset=True)
    position_control = current.model_copy(update=updates)
    config = runtime.update_position_control(position_control)
    return config.position_control.model_dump(mode="json")

@router.patch("/config/forex-trading")
def update_forex_trading(body: ForexTradingUpdate, request: Request) -> dict:
    runtime = runtime_from(request)
    current = runtime.config.forex_trading
    updates = body.model_dump(exclude_unset=True)
    forex_trading = current.model_copy(update=updates)
    try:
        config = runtime.apply_forex_trading(forex_trading)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        **config.forex_trading.model_dump(mode="json"),
        "applied": True,
        "restart_required": False,
        "runtime_symbols": runtime.symbols,
    }
