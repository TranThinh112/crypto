from spot_ai_bot.config import Settings
from spot_ai_bot.db import next_buy_sequence
from spot_ai_bot.exchange import ExchangeClient
from spot_ai_bot.models import TradeProposal
from spot_ai_bot.okx_private import (
    okx_funding_available,
    okx_order_detail,
    okx_transfer_funding_to_trading,
    okx_transfer_trading_to_funding,
)


class PaperExecution:
    async def execute(self, proposal: TradeProposal) -> TradeProposal:
        if proposal.status != "pending":
            return proposal
        proposal.status = "paper_filled"
        if proposal.price:
            proposal.quantity = round(proposal.amount_usd / proposal.price, 10)
        return proposal


class LiveExecution:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def execute(self, proposal: TradeProposal) -> TradeProposal:
        if proposal.status != "pending":
            return proposal
        if self.settings.live_trading_confirm != "I_UNDERSTAND_LIVE_TRADING_RISK":
            proposal.status = "blocked_live_guard"
            proposal.execution_error = "LIVE_TRADING_CONFIRM is not set to the required safety phrase."
            return proposal
        if proposal.amount_usd > self.settings.max_live_trade_usd:
            proposal.status = "blocked_live_guard"
            proposal.execution_error = "Proposal exceeds MAX_LIVE_TRADE_USD."
            return proposal
        if not self.settings.okx_api_key or not self.settings.okx_secret:
            proposal.status = "blocked_live_guard"
            proposal.execution_error = "Exchange API credentials are not configured."
            return proposal
        if self.settings.exchange_name.lower() == "okx" and not self.settings.okx_passphrase:
            proposal.status = "blocked_live_guard"
            proposal.execution_error = "OKX_PASSPHRASE is not configured."
            return proposal
        transferred_amount = 0.0
        if self.settings.exchange_name.lower() == "okx" and self.settings.spot_only_trading:
            available = await okx_funding_available(self.settings, self.settings.quote_currency)
            if available < proposal.amount_usd:
                proposal.status = "blocked_live_guard"
                proposal.execution_error = (
                    f"Funding {self.settings.quote_currency} balance is {available}; "
                    "bot will not use unified/futures account balance for spot trading."
                )
                return proposal
            transfer = await okx_transfer_funding_to_trading(self.settings, self.settings.quote_currency, proposal.amount_usd)
            if transfer.get("code") != "0":
                proposal.status = "blocked_live_guard"
                proposal.execution_error = f"Funding to trading transfer failed: {transfer.get('msg') or transfer}"
                return proposal
            transferred_amount = proposal.amount_usd

        client = ExchangeClient(self.settings)
        try:
            exchange_symbol = proposal.symbol
            if self.settings.quote_currency and "/" not in exchange_symbol:
                exchange_symbol = exchange_symbol.replace(self.settings.quote_currency, f"/{self.settings.quote_currency}")
            order = await client.market_buy(exchange_symbol, proposal.amount_usd, proposal.price)
            proposal.status = "live_filled"
            proposal.exchange_order_id = str(order.get("id") or "")
            proposal.quantity = float(order.get("amount") or proposal.quantity or 0)
            await self._hydrate_filled_buy(proposal, exchange_symbol)
            return proposal
        except Exception as exc:
            proposal.status = "live_failed"
            proposal.execution_error = type(exc).__name__
            if transferred_amount:
                try:
                    await okx_transfer_trading_to_funding(self.settings, self.settings.quote_currency, transferred_amount)
                except Exception:
                    proposal.execution_error += "; transfer_back_failed"
            return proposal
        finally:
            await client.close()

    async def _hydrate_filled_buy(self, proposal: TradeProposal, exchange_symbol: str) -> None:
        pair = _okx_inst_id(exchange_symbol)
        if self.settings.exchange_name.lower() == "okx" and proposal.exchange_order_id:
            try:
                detail = await okx_order_detail(self.settings, pair, proposal.exchange_order_id)
                item = (detail.get("data") or [{}])[0]
                proposal.average_price = _to_float(item.get("avgPx")) or proposal.price
                proposal.quantity = _to_float(item.get("accFillSz")) or proposal.quantity
                proposal.filled_notional_usd = (
                    _to_float(item.get("fillNotionalUsd"))
                    or _to_float(item.get("notionalUsd"))
                    or _to_float(item.get("sz"))
                    or proposal.amount_usd
                )
            except Exception:
                proposal.average_price = proposal.price
                proposal.filled_notional_usd = proposal.amount_usd
        else:
            proposal.average_price = proposal.price
            proposal.filled_notional_usd = proposal.amount_usd

        try:
            sequence = await next_buy_sequence(_base_asset(pair))
            if sequence:
                proposal.buy_sequence = sequence["label"]
        except Exception:
            proposal.buy_sequence = proposal.buy_sequence or "#?"

def _okx_inst_id(symbol: str) -> str:
    return symbol.replace("/", "-").upper()

def _base_asset(inst_id: str) -> str:
    return inst_id.replace("/", "-").split("-")[0].upper()

def _to_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
