from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import ccxt.async_support as ccxt

from spot_ai_bot.config import Settings


@dataclass
class ExchangeTicker:
    symbol: str
    last: float
    quote_volume: float
    percentage: float


class ExchangeClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        exchange_cls = getattr(ccxt, settings.exchange_name)
        options = {"defaultType": "spot"}
        if settings.exchange_name.lower() == "okx":
            options["fetchMarkets"] = ["spot"]
        self.exchange = exchange_cls(
            {
                "apiKey": settings.okx_api_key,
                "secret": settings.okx_secret,
                "password": settings.okx_passphrase,
                "enableRateLimit": True,
                "options": options,
            }
        )

    async def close(self) -> None:
        await self.exchange.close()

    async def ticker(self, symbol: str) -> ExchangeTicker:
        ticker = await self.exchange.fetch_ticker(symbol)
        last = float(ticker.get("last") or ticker.get("close") or 0)
        quote_volume = float(ticker.get("quoteVolume") or 0)
        percentage = float(ticker.get("percentage") or 0)
        return ExchangeTicker(symbol=symbol, last=last, quote_volume=quote_volume, percentage=percentage)

    async def ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 72) -> list[list[Any]]:
        return await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    async def market_buy(self, symbol: str, amount_usd: float, price: float | None) -> dict:
        if not price or price <= 0:
            raise ValueError("Cannot place order without a valid market price.")
        amount = amount_usd / price
        params = self.order_params()
        return await self.exchange.create_market_buy_order(symbol, amount, params=params)

    def order_params(self) -> dict:
        if self.settings.exchange_name.lower() == "okx" and self.settings.spot_only_trading:
            return {"tdMode": "cash"}
        return {}
