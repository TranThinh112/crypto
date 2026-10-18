"""Broker symbol alias resolution and metadata validation."""

from __future__ import annotations

from dataclasses import dataclass

from app.broker.mt5_client import BrokerClient, SymbolSpec
from app.config.settings import SymbolConfig
from app.utils.exceptions import SymbolResolutionError


@dataclass(frozen=True, slots=True)
class ResolvedSymbol:
    name: str
    specification: SymbolSpec


class SymbolResolver:
    def __init__(self, client: BrokerClient, config: SymbolConfig) -> None:
        self.client = client
        self.config = config

    def resolve(self) -> ResolvedSymbol:
        broker_symbols = self.client.symbols()
        lookup = {name.casefold(): name for name in broker_symbols}
        matched = next((lookup[alias.casefold()] for alias in self.config.allowed_aliases if alias.casefold() in lookup), None)
        if matched is None:
            raise SymbolResolutionError(f"None of the approved {self.config.base_symbol} aliases exist: {self.config.allowed_aliases}")
        if not self.client.select_symbol(matched):
            raise SymbolResolutionError(f"Broker refused to select {matched}")
        spec = self.client.symbol_spec(matched)
        if spec.trade_mode == 0:
            raise SymbolResolutionError(f"{matched} is disabled for trading")
        numeric = (spec.point, spec.trade_tick_size, spec.trade_tick_value, spec.trade_contract_size, spec.volume_min, spec.volume_step)
        if any(value <= 0 for value in numeric):
            raise SymbolResolutionError(f"{matched} has invalid tick, contract or volume metadata")
        return ResolvedSymbol(matched, spec)
